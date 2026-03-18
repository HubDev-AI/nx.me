---
id: "3-1-image-pipeline-service"
status: complete
created: 2026-03-16
---

# Story: Image Pipeline Service — NSFW Screening, EXIF Strip & Storage

## User Story

As the platform, I need every uploaded selfie to pass safety screening and have all metadata removed before storage, so that NSFW content is never stored and user PII (EXIF) is never exposed.

## Acceptance Criteria

- Given an uploaded image with magic bytes not matching JPEG/PNG/HEIF, When `ImagePipeline.process()` is called, Then HTTP 422 `IMAGE_FORMAT_REJECTED` is returned and no file is written to storage (AC-A10).
- Given an image exceeding `MAX_UPLOAD_SIZE_MB` or `MAX_IMAGE_DIMENSION_PX × MAX_IMAGE_DIMENSION_PX`, When processed, Then HTTP 422 `IMAGE_TOO_LARGE` is returned with no storage write.
- Given an image that AWS Rekognition scores ≥80% confidence for explicit content, When processed, Then an `images` row is created with `status = 'quarantined'`, `storage_key = NULL`; no file is written to the `raw-selfies` bucket; HTTP 422 `IMAGE_QUARANTINED` is returned within ≤5s (AC-A3, AC-NFR14).
- Given an accepted image, When the full pipeline runs (validate → NSFW screen → strip EXIF → re-encode), Then the stored file has zero EXIF/IPTC/XMP metadata — uploading a JPEG with GPS coordinates results in zero location metadata in the stored file (AC-FR3).
- Given the `raw-selfies` bucket, When an unsigned request attempts to read any object, Then HTTP 403 is returned (AC-NFR10).

## Architecture Guardrails

### Technology Stack

- **Backend:** Python 3.12 + FastAPI
- **Image processing:** Pillow 12.1.1 (verified 2026-03-16 via PyPI) — EXIF/IPTC/XMP stripping and clean re-encode
- **NSFW screening:** AWS Rekognition via boto3 1.42.68 (verified 2026-03-16 via PyPI) — synchronous `detect_moderation_labels`, $0.001/image, ≤3s typical
- **Storage:** Supabase Storage via supabase-py 2.15.1 (pinned in requirements.txt) — `raw-selfies` bucket (private, signed URLs only)
- **Config:** pydantic-settings 2.9.1 (pinned in requirements.txt)
- **No automated tests** — per QA skill decision; zero test code written during development

### File Structure for This Story

```
app/
  image_pipeline/
    __init__.py
    pipeline.py           # ImagePipeline class — orchestrates the full processing pipeline
    validators.py         # MagicBytesValidator, DimensionValidator
    nsfw_screener.py      # NSFWScreener — port/adapter for NSFW detection
    metadata_stripper.py  # MetadataStripper — Pillow-based EXIF/IPTC/XMP removal + re-encode
    storage.py            # StorageAdapter — port/adapter for Supabase Storage writes
    models.py             # ProcessedImage dataclass, error codes
```

### Port/Adapter Pattern

This story uses the port/adapter pattern for two external dependencies. The adapter is selected at startup based on `ADAPTER__NSFW_ADAPTER` and `ADAPTER__STORAGE_ADAPTER` config values.

**NSFWScreener Port:**

```python
from typing import Protocol

class NSFWScreenerPort(Protocol):
    async def screen(self, image_bytes: bytes) -> NSFWResult: ...

@dataclass(frozen=True)
class NSFWResult:
    is_explicit: bool
    confidence: float      # 0.0 – 100.0
    labels: list[str]      # e.g. ["Explicit Nudity"]
```

- **RekognitionAdapter** — calls `boto3` Rekognition `detect_moderation_labels`; checks if any label has `Confidence >= 80.0`
- **MockNSFWAdapter** — always returns `NSFWResult(is_explicit=False, confidence=0.0, labels=[])` for local dev

**StorageAdapter Port:**

```python
class StoragePort(Protocol):
    async def upload(self, bucket: str, key: str, data: bytes, content_type: str) -> str: ...
    async def create_signed_url(self, bucket: str, key: str, expires_in: int) -> str: ...
```

- **SupabaseStorageAdapter** — uses `supabase.storage.from_(bucket).upload(key, data, {"content-type": content_type})`
- **LocalStorageAdapter** — writes to local filesystem for dev (when `ADAPTER__STORAGE_ADAPTER=local`)

### Processing Pipeline (synchronous, every upload)

```
Upload received (file_bytes, content_type)
      |
1. MagicBytesValidator   — reject if first bytes do not match JPEG (FFD8FF), PNG (89504E47), HEIF (66747970)
      |
2. DimensionValidator    — reject if len(file_bytes) > MAX_UPLOAD_SIZE_MB * 1024 * 1024
                         — reject if either dimension > MAX_IMAGE_DIMENSION_PX
                         — dimension check uses Pillow Image.open() with DecompressionBombWarning guard
      |
3. NSFWScreener          — call adapter.screen(image_bytes)
                         — if is_explicit (confidence >= 80%): write images row with status='quarantined',
                           storage_key=NULL; return ProcessedImage with status='quarantined'; halt
      |  (if rejected: write images row, return HTTP 422 IMAGE_QUARANTINED; halt pipeline)
4. MetadataStripper      — Pillow: open image, extract pixel data, create new image from pixels only
                         — re-encode as same format (JPEG quality 95, PNG lossless)
                         — output bytes have zero EXIF, IPTC, XMP metadata
      |
5. Write to storage      — StorageAdapter.upload("raw-selfies", key, clean_bytes, content_type)
                         — key format: "{user_id}/{uuid}.{ext}"
      |
6. Write images row      — INSERT into images: user_id, storage_key, bucket='raw-selfies',
                           image_type='selfie', status='cleared', screened_at=NOW()
      |
Return ProcessedImage(storage_key, image_id, status='cleared')
```

### NSFW Quarantine Behavior

A quarantined upload writes an `images` row with `status = 'quarantined'` and `storage_key = NULL` (the column is nullable per the schema). No file is written to storage. This satisfies:
- AC-A3: NSFW content never written to storage
- AC-D7: queryable status field per image for audit/moderation

Quarantined rows are excluded from all feed, card, and history endpoints via status filter.

### `images` Table Schema

```sql
CREATE TABLE images (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID NOT NULL REFERENCES users(id),
    storage_key    TEXT UNIQUE,          -- NULLABLE: NULL for quarantined images
    bucket         TEXT,                 -- 'raw-selfies' (private) | 'generated-images' (public)
    image_type     TEXT NOT NULL
                   CHECK (image_type IN ('selfie','generated_before','generated_after','avatar')),
    status         TEXT NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending','cleared','quarantined')),
    screened_at    TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_images_user_status ON images (user_id, status);
CREATE INDEX idx_images_moderation ON images (status) WHERE status IN ('pending', 'quarantined');
```

### Error Response Format

All pipeline errors follow the architecture error taxonomy:

```json
{
  "error": {
    "code": "IMAGE_FORMAT_REJECTED",
    "message": "Uploaded file is not a supported image format (JPEG, PNG, HEIF).",
    "retry_eligible": true
  }
}
```

| Code | HTTP | When | Credit Impact |
|------|------|------|--------------|
| `IMAGE_FORMAT_REJECTED` | 422 | Magic bytes not JPEG/PNG/HEIF | None |
| `IMAGE_TOO_LARGE` | 422 | File exceeds MAX_UPLOAD_SIZE_MB or dimensions | None |
| `IMAGE_QUARANTINED` | 422 | NSFW screening rejected (>=80% confidence) | None |

### Supabase Storage Bucket Policy (AC-NFR10)

The `raw-selfies` bucket must be configured as **private** in Supabase Storage settings:
- No public access — all reads require a signed URL
- Signed URLs expire after `SIGNED_URL_EXPIRY_SECONDS` (default 3600 = 1 hour)
- Unsigned requests return HTTP 403
- This is a Supabase dashboard configuration, not application code — but the story must verify it

### Config Constants Used

All read from `app/config.py` via `from app.config import settings`:

| Setting | Default | Purpose |
|---------|---------|---------|
| `MAX_UPLOAD_SIZE_MB` | 20 | File size cap before processing |
| `MAX_IMAGE_DIMENSION_PX` | 8192 | Maximum width or height |
| `SIGNED_URL_EXPIRY_SECONDS` | 3600 | Supabase signed URL TTL |
| `ADAPTER__NSFW_ADAPTER` | "mock" | NSFW screener adapter selection (`mock` or `rekognition`) |
| `ADAPTER__STORAGE_ADAPTER` | "supabase" | Storage adapter selection (`supabase` or `local`) |
| `AWS_ACCESS_KEY_ID` | "" | AWS Rekognition credentials |
| `AWS_SECRET_ACCESS_KEY` | "" | AWS Rekognition credentials |
| `AWS_REGION` | "us-east-1" | AWS region for Rekognition |
| `SUPABASE_URL` | (required) | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | (required) | Service-role key for storage |

### NSFW Confidence Threshold

The 80% confidence threshold for NSFW screening is a business rule from the acceptance criteria (AC-A3). It is defined as a named constant within the `NSFWScreener` module — not in `app/config.py` — because it is not environment-variable-configurable (changing it requires a deliberate code change, not an env swap):

```python
# image_pipeline/nsfw_screener.py
NSFW_CONFIDENCE_THRESHOLD: float = 80.0  # percent — AC-A3
```

### Image Security (AC-A10, Section 9.3)

- Magic bytes validation before any processing — prevents polyglot file attacks
- Dimension + size check before full decode — prevents image bomb / DoS
- Pillow clean re-encode — original byte stream discarded entirely; no preserved metadata
- Processing runs in the API handler (synchronous) — the ECS task running image processing should have IAM policy with no outbound internet except to Rekognition endpoint
- EXIF/IPTC/XMP stripped from all stored images (AC-FR3, AC-NFR10)

### Amendment Integration

**A-6 (DB Transaction Convention):** The quarantine path writes a single `images` row INSERT — does not require explicit transaction management (single-row INSERT, auto-commit is fine). The cleared path also writes a single `images` row after a successful storage upload. If the storage upload fails, no row is written.

**A-8 (UserClaims Required Fields):** Not directly applicable to this story's pipeline code, but the `user_id` passed into the pipeline comes from `claims["sub"]` via `get_current_user` — which is guaranteed present per A-8.

## Verified Interfaces

### Settings (app/config.py)

- **Source:** `app/config.py:47-49`
- **Signature:** `MAX_UPLOAD_SIZE_MB: int = 20`, `MAX_IMAGE_DIMENSION_PX: int = 8192`, `SIGNED_URL_EXPIRY_SECONDS: int = 3600`
- **Plan match:** Matches

### Settings — Adapter Selection (app/config.py)

- **Source:** `app/config.py:31,36`
- **Signature:** `ADAPTER__NSFW_ADAPTER: str = "mock"`, `ADAPTER__STORAGE_ADAPTER: str = "local"`
- **Plan match:** Matches

### Settings — AWS Credentials (app/config.py)

- **Source:** `app/config.py:23-25`
- **Signature:** `AWS_ACCESS_KEY_ID: str = ""`, `AWS_SECRET_ACCESS_KEY: str = ""`, `AWS_REGION: str = "us-east-1"`
- **Plan match:** Matches

### get_supabase_service (app/db/client.py)

- **Source:** `app/db/client.py:10`
- **Signature:** `def get_supabase_service() -> Client`
- **Plan match:** Matches — returns a Supabase client authenticated with the service-role key

### get_current_user (app/api/deps.py)

- **Source:** `app/api/deps.py:40`
- **Signature:** `def get_current_user(authorization: Annotated[str | None, Header()] = None, supabase: Client = Depends(get_supabase)) -> UserClaims`
- **Plan match:** Matches — delegates to validate_jwt, returns UserClaims with sub: Required[str]

### UserClaims (app/api/middleware/auth.py)

- **Source:** `app/api/middleware/auth.py:22`
- **Signature:** `class UserClaims(TypedDict, total=False)` with `sub: Required[str]`, `exp: Required[int]`
- **Plan match:** Matches — Amended by A-8

### ImagePipeline.process (interface contract — this story defines it)

- **Source:** Not yet implemented — this story creates it
- **Signature:** `ImagePipeline.process(file_bytes: bytes, content_type: str, user_id: str, supabase: Client) -> ProcessedImage`
- **Plan match:** UNVERIFIED — source not yet implemented, using plan contract. Note: `user_id` and `supabase` parameters added beyond the plan contract signature because the pipeline needs to write the `images` row and set `user_id` on storage keys. The consumer (Story 3-3) will pass these.

## Tasks

- [x] Task 1: Create `app/image_pipeline/models.py` and `app/image_pipeline/__init__.py`
  - Maps to: AC-1, AC-2, AC-3 (error codes + ProcessedImage dataclass)
  - Files: `app/image_pipeline/__init__.py`, `app/image_pipeline/models.py`

- [x] Task 2: Create `app/image_pipeline/validators.py` — MagicBytesValidator + DimensionValidator
  - Maps to: AC-1 (magic bytes), AC-2 (size/dimension)
  - Files: `app/image_pipeline/validators.py`

- [x] Task 3: Create `app/image_pipeline/nsfw_screener.py` — NSFWScreenerPort, RekognitionAdapter, MockNSFWAdapter
  - Maps to: AC-3 (NSFW screening, quarantine, <=5s)
  - Files: `app/image_pipeline/nsfw_screener.py`

- [x] Task 4: Create `app/image_pipeline/metadata_stripper.py` — Pillow-based EXIF/IPTC/XMP removal + re-encode
  - Maps to: AC-4 (zero metadata in stored file)
  - Files: `app/image_pipeline/metadata_stripper.py`

- [x] Task 5: Create `app/image_pipeline/storage.py` — StoragePort, SupabaseStorageAdapter, LocalStorageAdapter
  - Maps to: AC-4 (storage write), AC-5 (bucket policy)
  - Files: `app/image_pipeline/storage.py`

- [x] Task 6: Create `app/image_pipeline/pipeline.py` — ImagePipeline orchestrator class
  - Maps to: AC-1, AC-2, AC-3, AC-4 (full pipeline orchestration)
  - Files: `app/image_pipeline/pipeline.py`

- [x] Task 7: Verify `raw-selfies` Supabase bucket is private + update `requirements.txt` with Pillow and boto3
  - Maps to: AC-5 (unsigned request returns 403)
  - Files: `requirements.txt` (add Pillow, boto3)

## must_haves

truths:
  - "ImagePipeline.process() called with JPEG magic bytes FFD8FF returns ProcessedImage with status='cleared'"
  - "ImagePipeline.process() called with file_bytes whose first 4 bytes are 0x00000000 raises HTTP 422 with code IMAGE_FORMAT_REJECTED"
  - "ImagePipeline.process() called with file_bytes exceeding MAX_UPLOAD_SIZE_MB * 1024 * 1024 raises HTTP 422 with code IMAGE_TOO_LARGE"
  - "ImagePipeline.process() called with image where Rekognition returns Confidence >= 80 writes images row with status='quarantined' and storage_key=NULL and raises HTTP 422 with code IMAGE_QUARANTINED"
  - "MetadataStripper.strip() given a JPEG with GPS EXIF data returns bytes with zero EXIF/IPTC/XMP metadata"
  - "SupabaseStorageAdapter.upload() writes to the 'raw-selfies' bucket with key format '{user_id}/{uuid}.{ext}'"
  - "The raw-selfies Supabase bucket is configured as private — unsigned GET returns HTTP 403"

artifacts:
  - path: "app/image_pipeline/__init__.py"
  - path: "app/image_pipeline/models.py"
    contains: ["ProcessedImage", "storage_key", "image_id", "status", "IMAGE_FORMAT_REJECTED", "IMAGE_TOO_LARGE", "IMAGE_QUARANTINED"]
  - path: "app/image_pipeline/validators.py"
    contains: ["MagicBytesValidator", "DimensionValidator", "MAX_UPLOAD_SIZE_MB", "MAX_IMAGE_DIMENSION_PX"]
  - path: "app/image_pipeline/nsfw_screener.py"
    contains: ["NSFWScreenerPort", "NSFWResult", "RekognitionAdapter", "MockNSFWAdapter", "NSFW_CONFIDENCE_THRESHOLD", "detect_moderation_labels"]
  - path: "app/image_pipeline/metadata_stripper.py"
    contains: ["MetadataStripper", "strip", "Image.open", "Image.new"]
  - path: "app/image_pipeline/storage.py"
    contains: ["StoragePort", "SupabaseStorageAdapter", "LocalStorageAdapter", "upload", "raw-selfies"]
  - path: "app/image_pipeline/pipeline.py"
    contains: ["ImagePipeline", "process", "MagicBytesValidator", "DimensionValidator", "NSFWScreenerPort", "MetadataStripper", "StoragePort", "ProcessedImage"]

key_links:
  - pattern: "from app.config import settings"
    in: ["app/image_pipeline/validators.py", "app/image_pipeline/nsfw_screener.py", "app/image_pipeline/storage.py", "app/image_pipeline/pipeline.py"]
  - pattern: "from app.image_pipeline.models import ProcessedImage"
    in: ["app/image_pipeline/pipeline.py"]
  - pattern: "from app.image_pipeline.pipeline import ImagePipeline"
    in: ["app/api/analyses.py"]
  - pattern: "NSFW_CONFIDENCE_THRESHOLD"
    in: ["app/image_pipeline/nsfw_screener.py"]
  - pattern: "detect_moderation_labels"
    in: ["app/image_pipeline/nsfw_screener.py"]
  - pattern: "raw-selfies"
    in: ["app/image_pipeline/storage.py", "app/image_pipeline/pipeline.py"]

## Dev Notes

### Testing Approach

Zero automated tests per QA skill decision. All verification is via manual testing against local Supabase:
- Upload test images (clean JPEG, JPEG with GPS EXIF, PNG, unsupported format) via Swagger UI (`/docs`)
- Verify stored images in local Supabase Storage dashboard (`http://127.0.0.1:54323` → Storage)
- Run ExifTool on downloaded stored images to verify zero metadata
- Attempt unsigned access to `raw-selfies` bucket — expect 403
- NSFW: `ADAPTER__NSFW_ADAPTER=mock` when testing non-NSFW features; set `=rekognition` with AWS creds for real NSFW screening

### Conventions from Prior Stories

**Story 1-1 established:**
- `from app.config import settings` is the canonical config import pattern
- `app/migrations/NNNN_name.sql` is the migration file convention
- pydantic-settings `Settings` class with `SettingsConfigDict(env_file=".env", extra="ignore")`
- All SQL: `snake_case` table and column names; `TIMESTAMPTZ` for all timestamps
- `LimitType` StrEnum at `app/services/limits.py`

**Story 2-2 established:**
- `from app.api.deps import get_current_user, get_supabase` is the canonical dependency import
- `UserClaims` TypedDict with `sub: Required[str]` (Amended by A-8)
- Error responses use `raise HTTPException(status_code=..., detail=...)` pattern
- Supabase client obtained from `request.app.state.supabase` via `get_supabase` dependency
- Logging pattern: `logger = logging.getLogger(__name__)` at module top
- Router pattern: `router = APIRouter(tags=["..."])`
- Request/Response models as Pydantic `BaseModel` subclasses

**Story 2-2 review findings:**
- F4: UserClaims Required fields — fixed via A-8 (use `Required[str]` for always-present fields)
- Code review caught missing explicit type annotations in service helpers — always annotate return types

### Local Dev Environment

Local Supabase CLI provides real DB, Auth, and Storage locally. Redis via Docker Compose.

```bash
# Start local Supabase (DB + Auth + Storage):
supabase start

# Start Redis:
docker compose up -d

# Start the API (hot-reload):
./scripts/dev-start.sh
```

The default adapter configuration points at local Supabase — real end-to-end testing out of the box:
- `ADAPTER__STORAGE_ADAPTER=supabase` — uploads go to local Supabase Storage (real behavior)
- `ADAPTER__NSFW_ADAPTER=mock` — Rekognition can't run locally; use mock when testing non-NSFW features, or set to `rekognition` with AWS creds for real NSFW testing

Environment variables required for this story:
- `SUPABASE_URL` — local Supabase URL (from `supabase status`, typically `http://127.0.0.1:54321`)
- `SUPABASE_SERVICE_ROLE_KEY` — local service role key (from `supabase status`)
- `ADAPTER__NSFW_ADAPTER` — `"mock"` (default, no AWS calls) or `"rekognition"` (real NSFW screening)
- `ADAPTER__STORAGE_ADAPTER` — `"supabase"` (default, real local storage) or `"local"` (filesystem fallback)
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` — required only when `ADAPTER__NSFW_ADAPTER=rekognition`

### Library Versions

- **Pillow:** 12.1.1 (verified 2026-03-16 via PyPI)
- **boto3:** 1.42.68 (verified 2026-03-16 via AWS docs)
- **supabase-py:** 2.15.1 (pinned in requirements.txt — project uses this version, not latest 2.28.2)
- **Pillow EXIF stripping approach:** Open image with `Image.open()`, create new image from `.getdata()`, save to bytes buffer — this discards all metadata chunks. Do NOT use `image.save()` on the original object as some metadata may persist.
- **boto3 Rekognition API:** `client.detect_moderation_labels(Image={"Bytes": image_bytes})` — returns `{"ModerationLabels": [{"Name": str, "Confidence": float, "ParentName": str}]}`

### Magic Bytes Reference

| Format | Magic Bytes (hex) | Offset |
|--------|-------------------|--------|
| JPEG | `FF D8 FF` | 0 |
| PNG | `89 50 4E 47 0D 0A 1A 0A` | 0 |
| HEIF | `66 74 79 70` (`ftyp`) | 4 (preceded by 4-byte box size) |

HEIF detection: read bytes 4-8; if they match `ftyp`, then check bytes 8-12 for `heic`, `heix`, `hevc`, `hevx`, or `mif1`.

### Adapter Registration Pattern

The pipeline must resolve adapters at initialization based on config values. Suggested pattern:

```python
# app/image_pipeline/pipeline.py
from app.config import settings

def _get_nsfw_screener() -> NSFWScreenerPort:
    if settings.ADAPTER__NSFW_ADAPTER == "rekognition":
        from app.image_pipeline.nsfw_screener import RekognitionAdapter
        return RekognitionAdapter()
    from app.image_pipeline.nsfw_screener import MockNSFWAdapter
    return MockNSFWAdapter()

def _get_storage_adapter(supabase: Client) -> StoragePort:
    if settings.ADAPTER__STORAGE_ADAPTER == "supabase":
        from app.image_pipeline.storage import SupabaseStorageAdapter
        return SupabaseStorageAdapter(supabase)
    from app.image_pipeline.storage import LocalStorageAdapter
    return LocalStorageAdapter()
```

### Pillow DecompressionBomb Guard

Pillow raises `DecompressionBombWarning` for images with more than `PIL.Image.MAX_IMAGE_PIXELS` pixels (default ~178 million). Set `PIL.Image.MAX_IMAGE_PIXELS = MAX_IMAGE_DIMENSION_PX * MAX_IMAGE_DIMENSION_PX` to align with our config, and catch `DecompressionBombError` as an `IMAGE_TOO_LARGE` rejection.

## Wave Structure

Wave 1: [Task 1, Task 2, Task 3, Task 4, Task 5] — independent, no shared files
  - Task 1: models.py (dataclasses/error codes only)
  - Task 2: validators.py (imports from models.py but models.py has no deps on validators)
  - Task 3: nsfw_screener.py (standalone port/adapter, imports config only)
  - Task 4: metadata_stripper.py (standalone Pillow logic)
  - Task 5: storage.py (standalone port/adapter, imports config only)

Wave 2: [Task 6] — depends on all Wave 1 outputs (pipeline orchestrator imports all modules)

Wave 3: [Task 7] — depends on Task 6 (requirements.txt update + bucket verification after pipeline code is complete)
