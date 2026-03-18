---
id: "3-3-analysis-api-endpoint"
status: complete
created: 2026-03-16
---

# Story: Analysis API Endpoint — POST /analyses

## User Story

As a registered user, I want to submit a selfie for face analysis via the API, so that I receive an analysis ID and can retrieve results.

## Acceptance Criteria

- Given `POST /analyses` with a valid selfie, When the handler runs, Then `ImagePipeline.process()` runs first (NSFW gate), then `FaceAnalysisService.analyze()` runs; an `analyses` row is created with `status = 'completed'`; HTTP 201 is returned with `{ analysis_id, face_shape, symmetry_score, recommendations }`.
- Given a quarantined image, When `POST /analyses` is called, Then `FaceAnalysisService.analyze()` is never called; HTTP 422 `IMAGE_QUARANTINED` is returned; no trial or credit is consumed.
- Given `GET /analyses/{id}`, When called by the owning user, Then the full analysis result is returned; when called by a different user, HTTP 403 is returned.
- Given a face validation failure (no face detected, multiple faces, obstructed), When `POST /analyses` is processed, Then a distinct `IMAGE_FORMAT_REJECTED` or appropriate error code is returned; no trial is consumed (AC-U4).

## Architecture Guardrails

### Technology Stack

- **Backend:** Python 3.12 + FastAPI 0.115.12 (pinned in requirements.txt)
- **Database:** Supabase PostgreSQL via supabase-py 2.15.1 (pinned in requirements.txt)
- **Auth:** JWT validation via PyJWT 2.10.1 (pinned in requirements.txt)
- **File upload:** FastAPI `UploadFile` (requires `python-multipart`, transitive dependency of FastAPI)
- **No automated tests** -- per QA skill decision; zero test code written during development

### Non-Negotiable Boundaries

- **C-2 LOCKED:** No attractiveness score or ranking in any API response, UI element, or data model field.
- **ADR-1:** Facial landmark vectors are ephemeral -- computed in-request, never persisted. Only derived values (`face_shape`, `symmetry_score`, `recommendations`) are written to the `analyses` table.

### File Structure for This Story

```
app/
  api/
    analyses.py         # NEW: POST /analyses, GET /analyses/{id} — thin wiring layer
  main.py               # MODIFY: register analyses router
```

### Router Registration Pattern

Routers are registered in `app/main.py` via `create_app()`. The analyses router should follow the existing pattern:

```python
from app.api import auth, entitlement, health, analyses  # add analyses

app.include_router(analyses.router)  # no prefix — routes define /analyses paths directly
```

The existing routers registered in `app/main.py`:
- `health.router` — no prefix
- `auth.router` — prefix="/auth"
- `entitlement.router` — no prefix

### `analyses` Table Schema

```sql
CREATE TABLE analyses (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status              TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    original_image_id   UUID REFERENCES images(id),
    face_shape          TEXT CHECK (face_shape IN ('oval', 'round', 'square', 'heart', 'oblong')),
    symmetry_score      FLOAT CHECK (symmetry_score BETWEEN 0.0 AND 1.0),
    recommendations     JSONB,      -- List[{rank, category, suggestion_text, rationale}]
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- NOTE: landmark_vectors are NOT stored — ephemeral per ADR-1
CREATE INDEX idx_analyses_user_id ON analyses (user_id, created_at DESC);
```

This table already exists from migration `0001_initial.sql`. No schema changes needed.

### `images` Table Schema (relevant columns)

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
```

### POST /analyses API Contract

**Request:** `multipart/form-data` with a `file` field (the selfie image).

**Response 201:**
```json
{
  "analysis_id": "uuid",
  "face_shape": "oval",
  "symmetry_score": 0.82,
  "recommendations": [
    { "rank": 1, "category": "eyebrows", "suggestion": "Arch your brows slightly higher to elongate your face" },
    { "rank": 2, "category": "hair", "suggestion": "Try layers that add volume at the crown" }
  ],
  "status": "completed"
}
```

**Response 422 (pipeline errors):**
```json
{
  "error": {
    "code": "IMAGE_FORMAT_REJECTED",
    "message": "Uploaded file is not a supported image format (JPEG, PNG, HEIF).",
    "retry_eligible": true
  }
}
```

**Response 422 (face analysis errors):**
```json
{
  "error": {
    "code": "FACE_NOT_DETECTED",
    "message": "No face was detected. Please upload a clear, front-facing selfie.",
    "retry_eligible": true
  }
}
```

### GET /analyses/{id} API Contract

**Response 200 (owning user):**
```json
{
  "analysis_id": "uuid",
  "face_shape": "oval",
  "symmetry_score": 0.82,
  "recommendations": [
    { "rank": 1, "category": "eyebrows", "suggestion": "Arch your brows slightly higher to elongate your face" },
    { "rank": 2, "category": "hair", "suggestion": "Try layers that add volume at the crown" }
  ],
  "status": "completed",
  "created_at": "2026-03-16T14:00:00Z"
}
```

**Response 403 (different user):**
```json
{
  "detail": "Not authorized to view this analysis"
}
```

**Response 404:**
```json
{
  "detail": "Analysis not found"
}
```

### Error Codes and HTTP Responses

Errors from `ImagePipeline.process()` (raised as `HTTPException` inside the pipeline):

| Code | HTTP | When | Credit Impact |
|------|------|------|--------------|
| `IMAGE_FORMAT_REJECTED` | 422 | Magic bytes not JPEG/PNG/HEIF | None |
| `IMAGE_TOO_LARGE` | 422 | File exceeds MAX_UPLOAD_SIZE_MB or dimensions | None |
| `IMAGE_QUARANTINED` | 422 | NSFW screening rejected (>=80% confidence) | None |

Errors from `FaceAnalysisService.analyze()` (raised as `HTTPException` inside the service):

| Code | HTTP | When | Credit Impact |
|------|------|------|--------------|
| `FACE_NOT_DETECTED` | 422 | No face found in image | None |
| `MULTIPLE_FACES` | 422 | More than one face detected | None |
| `FACE_OBSTRUCTED` | 422 | Face partially covered | None |
| `IMAGE_TOO_BLURRY` | 422 | Blur threshold exceeded | None |
| `IMAGE_NOT_FOUND` | 422 | Could not retrieve image from storage | None |

Error response format (consistent with stories 3-1 and 3-2):
```json
{
  "error": {
    "code": "...",
    "message": "...",
    "retry_eligible": true
  }
}
```

### Endpoint Handler Flow

**POST /analyses:**

```
1. Auth: get_current_user -> UserClaims (claims["sub"] = user_id)
2. Read file bytes from UploadFile
3. ImagePipeline.process(file_bytes, content_type, user_id)
   - On quarantine: raises HTTPException 422 IMAGE_QUARANTINED (AC-2: analyze() never called)
   - On format/size error: raises HTTPException 422 (AC-4: no trial consumed)
   - On success: returns ProcessedImage(storage_key, image_id, status="cleared")
4. FaceAnalysisService.analyze(processed.storage_key)
   - On face error: raises HTTPException 422 FACE_NOT_DETECTED / MULTIPLE_FACES / etc.
   - On success: returns AnalysisResult(face_shape, symmetry_score, recommendations)
5. INSERT into analyses table:
   - id: generated UUID
   - user_id: from claims["sub"]
   - original_image_id: processed.image_id
   - face_shape: result.face_shape
   - symmetry_score: result.symmetry_score
   - recommendations: JSONB serialization of result.recommendations
   - status: "completed"
   - created_at, updated_at: NOW()
6. Return HTTP 201 with analysis_id, face_shape, symmetry_score, recommendations, status
```

**GET /analyses/{id}:**

```
1. Auth: get_current_user -> UserClaims
2. SELECT from analyses WHERE id = {analysis_id}
3. If not found: HTTP 404
4. If analyses.user_id != claims["sub"]: HTTP 403 (AC-3)
5. Return analysis data
```

### Entitlement Note

`POST /analyses` does NOT require an entitlement pre-check. The architecture workflow (Section 4.1) shows that the entitlement gate (`require_entitlement("generation")`) is on `POST /analyses/{id}/generate` (Story 4-3), not on `POST /analyses`. The analysis itself is free -- the ACs state "no trial or credit is consumed" on failure paths defensively, confirming that analyses do not have a separate entitlement cost.

### Pydantic Response Models

Define as `BaseModel` subclasses in `app/api/analyses.py` (consistent with Story 2-2 pattern):

```python
class SuggestionResponse(BaseModel):
    rank: int
    category: str
    suggestion: str  # maps from Suggestion.suggestion_text

class AnalysisResponse(BaseModel):
    analysis_id: str
    face_shape: str
    symmetry_score: float
    recommendations: list[SuggestionResponse]
    status: str

class AnalysisDetailResponse(AnalysisResponse):
    created_at: str
```

Note: The architecture API contract uses `suggestion` (not `suggestion_text`) in the response JSON. The handler must map `Suggestion.suggestion_text` -> `suggestion` in the response.

### Amendment Integration

**A-8 (UserClaims Required Fields):** `claims["sub"]` is always present per A-8 (`sub: Required[str]`). No guard needed when accessing user_id from claims.

**A-5 (Entitlement):** Does not apply to POST /analyses directly. The entitlement gate is on POST /analyses/{id}/generate. However, the `require_entitlement` and `get_entitlement_service` dependencies exist in `app/api/deps.py` and are available if future stories add entitlement gating to analyses.

**A-6 (DB Transaction Convention):** The analyses INSERT is a single-row INSERT after both pipeline and analysis succeed. Auto-commit is fine (consistent with A-6 guidance for single-row INSERTs). If the INSERT fails after processing, the image is already stored but no analysis row exists -- the user can retry.

## Verified Interfaces

### ImagePipeline.process (app/image_pipeline/pipeline.py)

- **Source:** `app/image_pipeline/pipeline.py:74-79`
- **Signature:** `async def process(self, file_bytes: bytes, content_type: str, user_id: str) -> ProcessedImage`
- **Plan match:** The plan's Interface Contracts section lists `process(file_bytes: bytes, content_type: str) -> ProcessedImage` (no `user_id`). Actual source includes `user_id: str` as a third parameter. This is expected -- Story 3-1 added `user_id` for storage key generation and DB writes. Use ACTUAL source signature.

### ProcessedImage (app/image_pipeline/models.py)

- **Source:** `app/image_pipeline/models.py:23-29`
- **Signature:** `@dataclass(frozen=True) class ProcessedImage: storage_key: str | None; image_id: UUID; status: Literal["cleared", "quarantined"]`
- **Plan match:** Matches

### FaceAnalysisService.__init__ (app/face_analysis/service.py)

- **Source:** `app/face_analysis/service.py:92-94`
- **Signature:** `def __init__(self, supabase: Client) -> None`
- **Plan match:** Matches

### FaceAnalysisService.analyze (app/face_analysis/service.py)

- **Source:** `app/face_analysis/service.py:96-138`
- **Signature:** `async def analyze(self, image_storage_key: str) -> AnalysisResult`
- **Plan match:** Matches plan contract signature `analyze(image_storage_key: str) -> AnalysisResult`

### AnalysisResult (app/face_analysis/models.py)

- **Source:** `app/face_analysis/models.py:43-48`
- **Signature:** `@dataclass(frozen=True) class AnalysisResult: face_shape: FaceShape; symmetry_score: float; recommendations: list[Suggestion]`
- **Plan match:** Matches

### Suggestion (app/face_analysis/models.py)

- **Source:** `app/face_analysis/models.py:33-39`
- **Signature:** `@dataclass(frozen=True) class Suggestion: rank: int; category: str; suggestion_text: str; rationale: str`
- **Plan match:** Matches

### FaceShape (app/face_analysis/models.py)

- **Source:** `app/face_analysis/models.py:17-24`
- **Signature:** `class FaceShape(StrEnum): OVAL = "oval"; ROUND = "round"; SQUARE = "square"; HEART = "heart"; OBLONG = "oblong"`
- **Plan match:** Matches

### get_current_user (app/api/deps.py)

- **Source:** `app/api/deps.py:41-58`
- **Signature:** `def get_current_user(authorization: Annotated[str | None, Header()] = None, supabase: Client = Depends(get_supabase)) -> UserClaims`
- **Plan match:** Matches -- Amended by A-8 (sub: Required[str])

### get_supabase (app/api/deps.py)

- **Source:** `app/api/deps.py:26-28`
- **Signature:** `def get_supabase(request: Request) -> Client`
- **Plan match:** Matches

### UserClaims (app/api/middleware/auth.py)

- **Source:** `app/api/middleware/auth.py:22-35`
- **Signature:** `class UserClaims(TypedDict, total=False)` with `sub: Required[str]`, `exp: Required[int]`
- **Plan match:** Matches -- Amended by A-8

### ImagePipeline.__init__ (app/image_pipeline/pipeline.py)

- **Source:** `app/image_pipeline/pipeline.py:66-72`
- **Signature:** `def __init__(self, supabase: Client) -> None`
- **Plan match:** Matches

### create_app / router registration (app/main.py)

- **Source:** `app/main.py:55-75`
- **Signature:** `def create_app() -> FastAPI` -- uses `app.include_router()` for each router
- **Plan match:** Matches -- story adds `analyses.router` to the existing pattern

## Tasks

- [x] Task 1: Create `app/api/analyses.py` -- POST /analyses and GET /analyses/{id} endpoints with Pydantic response models
  - Maps to: AC-1 (POST /analyses happy path), AC-2 (quarantined image), AC-3 (GET with ownership check), AC-4 (face validation errors)
  - Files: `app/api/analyses.py`

- [x] Task 2: Register analyses router in `app/main.py`
  - Maps to: AC-1 (endpoint must be reachable)
  - Files: `app/main.py`

## must_haves

truths:
  - "POST /analyses with a valid JPEG selfie returns HTTP 201 with JSON containing analysis_id, face_shape, symmetry_score, recommendations, and status='completed'"
  - "POST /analyses with a valid selfie creates an analyses row with status='completed', user_id matching the JWT sub, and original_image_id matching the ProcessedImage.image_id"
  - "POST /analyses with a quarantined image returns HTTP 422 with error code IMAGE_QUARANTINED and FaceAnalysisService.analyze() is never called"
  - "POST /analyses with an image where no face is detected returns HTTP 422 with error code FACE_NOT_DETECTED"
  - "POST /analyses with an image where multiple faces are detected returns HTTP 422 with error code MULTIPLE_FACES"
  - "GET /analyses/{id} called by the owning user returns the full analysis result with analysis_id, face_shape, symmetry_score, recommendations"
  - "GET /analyses/{id} called by a different user returns HTTP 403"
  - "GET /analyses/{id} for a non-existent analysis returns HTTP 404"

artifacts:
  - path: "app/api/analyses.py"
    contains: ["router", "APIRouter", "POST", "GET", "ImagePipeline", "FaceAnalysisService", "AnalysisResponse", "get_current_user", "get_supabase", "analyses"]
  - path: "app/main.py"
    contains: ["analyses"]

key_links:
  - pattern: "from app.image_pipeline.pipeline import ImagePipeline"
    in: ["app/api/analyses.py"]
  - pattern: "from app.face_analysis.service import FaceAnalysisService"
    in: ["app/api/analyses.py"]
  - pattern: "from app.api.deps import get_current_user, get_supabase"
    in: ["app/api/analyses.py"]
  - pattern: "from app.api.middleware.auth import UserClaims"
    in: ["app/api/analyses.py"]
  - pattern: "from app.api import"
    in: ["app/main.py"]
  - pattern: "analyses.router"
    in: ["app/main.py"]

## Dev Notes

### Testing Approach

Zero automated tests per QA skill decision. All verification is via manual testing against local Supabase:
- Upload a valid JPEG selfie via Swagger UI (`/docs`) -- expect HTTP 201 with analysis result
- Upload an unsupported file format -- expect HTTP 422 `IMAGE_FORMAT_REJECTED`
- Upload with `ADAPTER__NSFW_ADAPTER=rekognition` and an explicit image -- expect HTTP 422 `IMAGE_QUARANTINED`
- Upload with `ADAPTER__FACE_ANALYSIS_ADAPTER=mock` -- expect deterministic analysis result
- Upload with `ADAPTER__FACE_ANALYSIS_ADAPTER=mediapipe` and a no-face image -- expect HTTP 422 `FACE_NOT_DETECTED`
- Call `GET /analyses/{id}` with the owning user's JWT -- expect 200
- Call `GET /analyses/{id}` with a different user's JWT -- expect 403
- Call `GET /analyses/{nonexistent-uuid}` -- expect 404
- Query `analyses` table in Supabase Studio (`http://127.0.0.1:54323`) to verify row was inserted correctly

### Conventions from Prior Stories

**Story 1-1 established:**
- `from app.config import settings` is the canonical config import pattern
- All SQL: `snake_case` table and column names; `TIMESTAMPTZ` for all timestamps

**Story 2-2 established:**
- `from app.api.deps import get_current_user, get_supabase` is the canonical dependency import
- `UserClaims` TypedDict with `sub: Required[str]` (Amended by A-8)
- Error responses use `raise HTTPException(status_code=..., detail=...)` pattern
- Supabase client obtained from `request.app.state.supabase` via `get_supabase` dependency
- Logging pattern: `logger = logging.getLogger(__name__)` at module top
- Router pattern: `router = APIRouter(tags=["..."])`
- Request/Response models as Pydantic `BaseModel` subclasses
- Code review caught missing explicit type annotations in service helpers -- always annotate return types

**Story 3-1 established:**
- `ImagePipeline(supabase)` constructor takes a Supabase client
- `ImagePipeline.process()` raises `HTTPException` on failure -- the handler does NOT need to catch and re-raise pipeline errors; they propagate automatically through FastAPI
- `ProcessedImage.status` is `"cleared"` or `"quarantined"` -- but quarantine raises HTTPException before returning, so the handler only sees `"cleared"` results
- `datetime.now(tz=timezone.utc).isoformat()` for timestamps
- Error response format: `{"error": {"code": "...", "message": "...", "retry_eligible": true/false}}`

**Story 3-2 established:**
- `FaceAnalysisService(supabase)` constructor takes a Supabase client
- `FaceAnalysisService.analyze(image_storage_key)` raises `HTTPException` on face validation failures -- same propagation pattern as ImagePipeline
- The service fetches image bytes from storage internally using the storage_key
- `AnalysisResult.recommendations` is `list[Suggestion]` with exactly 5 items

**Story 4-1 established:**
- `EntitlementService` uses `supabase` + `redis` -- but not needed for this story since analyses are not entitlement-gated

### Key Implementation Detail: Error Propagation

Both `ImagePipeline.process()` and `FaceAnalysisService.analyze()` raise `HTTPException` on error paths. The handler does NOT need try/except around these calls for the error cases in AC-2 and AC-4. FastAPI's exception handling will return the correct error response automatically. The handler only needs to handle the success path (pipeline returns ProcessedImage, analysis returns AnalysisResult, then INSERT into analyses table).

### UploadFile Usage

FastAPI's `UploadFile` for multipart file uploads:

```python
from fastapi import UploadFile

@router.post("/analyses", status_code=201)
async def create_analysis(
    file: UploadFile,
    claims: UserClaims = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
) -> AnalysisResponse:
    file_bytes = await file.read()
    content_type = file.content_type or "application/octet-stream"
    ...
```

`python-multipart` is required for `UploadFile` parsing. It is a transitive dependency of FastAPI (auto-installed). The project does not pin it explicitly in `requirements.txt`, and no change is needed.

### Recommendation Serialization

The `Suggestion` dataclass has `suggestion_text` as the field name, but the architecture API contract uses `suggestion` in the response JSON. The Pydantic response model must map:
- `Suggestion.suggestion_text` -> `SuggestionResponse.suggestion`
- `Suggestion.rationale` is NOT included in the API response per the architecture contract

### JSONB Serialization for analyses.recommendations

The `recommendations` column is JSONB. When inserting, serialize the list of Suggestion dataclasses to a list of dicts. Use the DB-facing format (with `suggestion_text` and `rationale` for full data preservation):

```python
import json

recs_json = [
    {
        "rank": s.rank,
        "category": s.category,
        "suggestion_text": s.suggestion_text,
        "rationale": s.rationale,
    }
    for s in result.recommendations
]
```

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

Adapter configuration for testing:
- `ADAPTER__NSFW_ADAPTER=mock` (default) -- pipeline passes all images
- `ADAPTER__FACE_ANALYSIS_ADAPTER=mock` (default) -- returns deterministic analysis result
- `ADAPTER__STORAGE_ADAPTER=supabase` (default) -- uploads go to local Supabase Storage

Environment variables relevant to this story:
- `SUPABASE_URL` -- local Supabase URL (from `supabase status`, typically `http://127.0.0.1:54321`)
- `SUPABASE_SERVICE_ROLE_KEY` -- local service role key (from `supabase status`)
- `SUPABASE_JWT_SECRET` -- JWT secret for auth validation
- `ADAPTER__NSFW_ADAPTER` -- `"mock"` (default) or `"rekognition"`
- `ADAPTER__FACE_ANALYSIS_ADAPTER` -- `"mock"` (default) or `"mediapipe"`
- `ADAPTER__STORAGE_ADAPTER` -- `"supabase"` (default) or `"local"`

### Library Versions

- **FastAPI:** 0.115.12 (pinned in requirements.txt; latest is 0.135.1 but project pins 0.115.12)
- **supabase-py:** 2.15.1 (pinned in requirements.txt)
- **python-multipart:** transitive dependency of FastAPI, auto-installed, not explicitly pinned

## Wave Structure

Wave 1: [Task 1, Task 2] -- Task 2 modifies `app/main.py` (router registration) and depends on Task 1 creating the router module. However, these can be implemented sequentially within a single wave since Task 2 is a one-line change.

Alternative: Task 1 and Task 2 could be a single task given the [S] size. Keeping them separate for clear AC mapping but they share no output file conflicts (Task 1 creates `app/api/analyses.py`, Task 2 modifies `app/main.py`).

Wave 1: [Task 1, Task 2] -- no shared files (analyses.py vs main.py)
