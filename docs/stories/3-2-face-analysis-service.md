---
id: "3-2-face-analysis-service"
status: complete
created: 2026-03-16
---

# Story: Face Analysis Service — MediaPipe, Classification & Recommendations

## User Story

As a registered user, I want my selfie analyzed to receive a face shape classification, symmetry score, and top 5 improvement suggestions, so that I understand my unique features and get personalized style advice.

## Acceptance Criteria

- Given an image with a clearly visible single face, When `FaceAnalysisService.analyze()` is called, Then it returns a `face_shape` from `{oval, round, square, heart, oblong}` and a `symmetry_score` in `[0.0, 1.0]`; no attractiveness score or rank is present in the response (AC-FR10).
- Given the MediaPipe FaceMesh model, When the ECS container starts, Then the model is pre-loaded in the FastAPI `lifespan` handler; `GET /health` returns HTTP 200 only after model load; the first analysis request after scale-out does not trigger a cold-load delay.
- Given a standard analysis request, When the full pipeline (validate -> extract landmarks -> classify -> score -> recommend) runs on 4-core hardware with pre-loaded model, Then total latency is <=3s at P95 (AC-NFR1).
- Given two identical images, When analyzed, Then landmark vectors are NOT stored -- only `face_shape`, `symmetry_score`, and `recommendations` are written to the `analyses` table (ADR-1 enforcement).
- Given the `recommendations` output, When reviewed, Then no suggestion text contains attractiveness-rating language; all 5 suggestions are tied to the classified face shape and measured proportions.

## Architecture Guardrails

### Technology Stack

- **Backend:** Python 3.12 + FastAPI
- **Face analysis:** MediaPipe FaceMesh (468 3D landmarks) via mediapipe 0.10.32 (verified 2026-03-16 via PyPI)
- **Numerical computation:** numpy 2.4.3 (verified 2026-03-16 via PyPI)
- **Image loading:** Pillow 12.1.1 (already pinned in requirements.txt)
- **Config:** pydantic-settings 2.9.1 (pinned in requirements.txt)
- **No automated tests** -- per QA skill decision; zero test code written during development

### Non-Negotiable Boundaries

- **C-2 LOCKED:** No attractiveness score or ranking in any API response, UI element, or data model field.
- **ADR-1:** Facial landmark vectors are ephemeral -- computed in-request, never persisted. Only derived values (`face_shape`, `symmetry_score`, `recommendations`) are written to the `analyses` table. Landmark coordinates are discarded after the handler returns.

### File Structure for This Story

```
app/
  face_analysis/
    __init__.py
    service.py            # FaceAnalysisService -- orchestrates the full analysis pipeline
    landmark_extractor.py # LandmarkExtractor -- MediaPipe FaceMesh 468 3D landmarks (ephemeral)
    classifier.py         # FaceShapeClassifier -- jaw/forehead/cheekbone width ratios -> FaceShape enum
    symmetry_scorer.py    # SymmetryScorer -- bilateral landmark pair distance variance -> float [0.0, 1.0]
    recommendation.py     # RecommendationEngine -- rule-based: face_shape x measurements -> top 5 Suggestions
    models.py             # FaceShape enum, AnalysisResult, Suggestion dataclasses
```

### Port/Adapter Pattern (Amended by A-3)

This story uses the port/adapter pattern for MediaPipe, consistent with the pattern established in story 3-1. The adapter is selected at startup based on `ADAPTER__FACE_ANALYSIS_ADAPTER` config value (already present in `app/config.py` at line 32, default: `"mock"`).

**FaceAnalysisPort:**

```python
from typing import Protocol

class FaceAnalysisPort(Protocol):
    def analyze(self, image_bytes: bytes) -> AnalysisResult: ...

@dataclass(frozen=True)
class AnalysisResult:
    face_shape: FaceShape       # enum: oval, round, square, heart, oblong
    symmetry_score: float       # [0.0, 1.0]
    recommendations: list[Suggestion]  # exactly 5 items

@dataclass(frozen=True)
class Suggestion:
    rank: int                   # 1-5
    category: str               # e.g., "eyebrows", "hair", "skincare", "accessories", "grooming"
    suggestion_text: str        # actionable advice -- no attractiveness language
    rationale: str              # ties suggestion to face shape and proportions
```

- **MediaPipeAdapter** -- loads FaceMesh model, extracts landmarks, delegates to classifier/scorer/recommender
- **MockFaceAnalysisAdapter** -- returns deterministic `AnalysisResult` for local dev (when `ADAPTER__FACE_ANALYSIS_ADAPTER=mock`)

**Adapter resolution (lazy import, consistent with story 3-1 pattern):**

```python
# app/face_analysis/service.py
from app.config import settings

def _get_face_analysis_adapter() -> FaceAnalysisPort:
    if settings.ADAPTER__FACE_ANALYSIS_ADAPTER == "mediapipe":
        from app.face_analysis.landmark_extractor import MediaPipeAdapter
        return MediaPipeAdapter()
    from app.face_analysis.service import MockFaceAnalysisAdapter
    return MockFaceAnalysisAdapter()
```

### FaceAnalysisService Interface Contract

```python
class FaceAnalysisService:
    """Orchestrates face analysis: validate -> extract -> classify -> score -> recommend.

    Called synchronously from POST /analyses handler (story 3-3).
    """

    def __init__(self, supabase: Client) -> None:
        self._supabase = supabase
        self._adapter = _get_face_analysis_adapter()

    async def analyze(self, image_storage_key: str) -> AnalysisResult:
        """Analyze a face image and return classification, symmetry, and recommendations.

        Args:
            image_storage_key: Storage key in the 'raw-selfies' bucket.

        Returns:
            AnalysisResult with face_shape, symmetry_score, and 5 recommendations.

        Raises:
            HTTPException 422: FACE_NOT_DETECTED, MULTIPLE_FACES, FACE_OBSTRUCTED, IMAGE_TOO_BLURRY.
        """
        ...
```

**Internal pipeline steps (all synchronous, run sequentially):**

1. **Fetch image bytes** from Supabase Storage using `image_storage_key` (via `StoragePort.create_signed_url()` or direct download using service-role client)
2. **Load image** with Pillow (`Image.open(BytesIO(image_bytes))`) and convert to RGB numpy array
3. **LandmarkExtractor** -- `mediapipe.solutions.face_mesh.FaceMesh` processes the image, returns 468 3D landmarks. If no face detected: raise `FACE_NOT_DETECTED`. If multiple faces: raise `MULTIPLE_FACES`. Landmark coordinates are held in-memory only -- never written to DB (ADR-1).
4. **FaceShapeClassifier** -- computes jaw width, forehead width, face length, cheekbone width from landmark coordinates. Ratios determine face shape:
   - Oval: face length > cheekbone width, forehead slightly wider than jaw
   - Round: face length approximately equal to cheekbone width, rounded jawline
   - Square: face length approximately equal to cheekbone width, angular jaw
   - Heart: forehead wider than jaw, pointed chin
   - Oblong: face length significantly > cheekbone width, straight sides
5. **SymmetryScorer** -- computes bilateral landmark pair distances (left vs right side). Score = 1.0 - normalized variance of pair distance ratios. Perfect symmetry = 1.0, maximum asymmetry = 0.0.
6. **RecommendationEngine** -- rule-based lookup: `face_shape` x measured proportions -> ranked list of 5 `Suggestion` objects. Each suggestion includes `category`, `suggestion_text`, and `rationale`. No attractiveness-rating language permitted (C-2 LOCKED).
7. Landmark vectors discarded (garbage collected) -- only `AnalysisResult` returned.

### MediaPipe Model Preload (AC-2: Health Check Gate)

The MediaPipe FaceMesh model must be pre-loaded during FastAPI startup via the `lifespan` handler in `app/main.py`. The current `lifespan` handler initializes Supabase and Redis. This story adds MediaPipe model loading before `yield`.

**Modified lifespan (conceptual):**

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting NXME API (%s)", settings.APP_ENV)

    app.state.supabase = get_supabase_service()
    app.state.redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True, encoding="utf-8")

    # Pre-load MediaPipe FaceMesh model (AC-2)
    if settings.ADAPTER__FACE_ANALYSIS_ADAPTER == "mediapipe":
        from app.face_analysis.landmark_extractor import preload_model
        preload_model()  # blocks until model is in memory
        logger.info("MediaPipe FaceMesh model pre-loaded")
    else:
        logger.info("Face analysis adapter is '%s' -- skipping MediaPipe model load",
                     settings.ADAPTER__FACE_ANALYSIS_ADAPTER)

    logger.info("Supabase and Redis clients initialised")

    yield

    await app.state.redis.aclose()
    logger.info("NXME API shutdown complete")
```

**Health check behavior:** The existing `GET /health` endpoint (in `app/api/health.py`) already returns 200 if the process is up. Since model loading occurs before `yield` in the lifespan handler, FastAPI will not start accepting requests until the model is loaded. The ECS health check probes `GET /health` -- it will only succeed after startup completes. No code change to the health endpoint is needed.

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
-- NOTE: landmark_vectors are NOT stored -- ephemeral per ADR-1
CREATE INDEX idx_analyses_user_id ON analyses (user_id, created_at DESC);
```

The `analyses` table already exists from migration `0001_initial.sql`. No schema changes needed for this story. Story 3-3 handles the actual INSERT into this table when orchestrating the full endpoint flow.

### FaceShape Enum Values

```python
from enum import StrEnum

class FaceShape(StrEnum):
    OVAL = "oval"
    ROUND = "round"
    SQUARE = "square"
    HEART = "heart"
    OBLONG = "oblong"
```

These map directly to the `analyses.face_shape` CHECK constraint values in the database.

### Error Codes for Face Validation

From the architecture error taxonomy (Section 5):

| Code | HTTP | When | Credit Impact |
|------|------|------|--------------|
| `FACE_NOT_DETECTED` | 422 | No face found in image | None |
| `MULTIPLE_FACES` | 422 | More than one face detected | None |
| `FACE_OBSTRUCTED` | 422 | Face partially covered | None |
| `IMAGE_TOO_BLURRY` | 422 | Blur threshold exceeded | None |

Error response format (consistent with story 3-1):

```json
{
  "error": {
    "code": "FACE_NOT_DETECTED",
    "message": "No face was detected. Please upload a clear, front-facing selfie.",
    "retry_eligible": true
  }
}
```

### POST /analyses API Contract

```json
// Response 201
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

Note: The `POST /analyses` endpoint itself is created in story 3-3. This story creates only the `FaceAnalysisService` internal module that story 3-3's handler will call.

### MediaPipe FaceMesh Usage

MediaPipe FaceMesh provides 468 3D facial landmarks. Key landmark indices for face shape classification:

- **Jaw line:** landmarks 0-16 (outer jaw contour)
- **Forehead:** landmarks around 10, 338, 297, 332, 284
- **Cheekbones:** landmarks 234, 454 (widest points)
- **Chin:** landmark 152 (bottom of chin)
- **Nose bridge:** landmark 6 (top of nose bridge)

**Symmetry pairs** -- the 468 landmarks have mirrored pairs (left/right). Key pairs for symmetry scoring:
- Eye corners: (33, 263), (133, 362)
- Cheekbones: (234, 454)
- Mouth corners: (61, 291)
- Eyebrow ends: (70, 300)
- Jaw corners: (172, 397)

MediaPipe `process()` is a synchronous call. Since it is a CPU-bound operation, it must run in the main thread (MediaPipe is not thread-safe with the same `FaceMesh` instance). For async handlers, wrap in `asyncio.get_event_loop().run_in_executor(None, ...)` to avoid blocking the event loop.

### Amendment Integration

**A-3 (Adapter Pattern):** This story uses port/adapter for face analysis. `FaceAnalysisPort` protocol, `MediaPipeAdapter` as default, `MockFaceAnalysisAdapter` for local dev. Config key `ADAPTER__FACE_ANALYSIS_ADAPTER` already exists in `app/config.py` (line 32, default: `"mock"`). Note: A-3 prescribes `app/adapters/mediapipe/face_analysis.py` directory structure, but story 3-1 established the convention of keeping port/adapter within the feature module (`app/image_pipeline/`). This story follows the 3-1 convention (codebase convention overrides A-3 aspirational structure).

**A-6 (DB Transaction Convention):** This story does NOT write to the database. The `analyses` table INSERT happens in story 3-3's endpoint handler. `FaceAnalysisService.analyze()` only returns an `AnalysisResult` -- it is a pure computation module.

**A-3 user_memories snapshot:** A-3 scope extension mentions `FaceAnalysisService` writing a snapshot to `user_memories` after analysis. However, the `user_memories` table does not exist yet (it is part of Epic 7 -- Advisor). The story 3-2 ACs do not mention this write. This story will NOT implement the `user_memories` write. It can be added in a later story when the table and advisor infrastructure exist.

## Verified Interfaces

### Settings -- ADAPTER__FACE_ANALYSIS_ADAPTER (app/config.py)

- **Source:** `app/config.py:32`
- **Signature:** `ADAPTER__FACE_ANALYSIS_ADAPTER: str = "mock"`
- **Plan match:** Matches

### StoragePort.create_signed_url (app/image_pipeline/storage.py)

- **Source:** `app/image_pipeline/storage.py:35`
- **Signature:** `async def create_signed_url(self, bucket: str, key: str, expires_in: int) -> str: ...`
- **Plan match:** Matches -- used to fetch image bytes for analysis

### SupabaseStorageAdapter.upload (app/image_pipeline/storage.py)

- **Source:** `app/image_pipeline/storage.py:53`
- **Signature:** `async def upload(self, bucket: str, key: str, data: bytes, content_type: str) -> str`
- **Plan match:** Matches -- not directly used by this story, but confirms storage adapter interface

### ImagePipeline.process (app/image_pipeline/pipeline.py)

- **Source:** `app/image_pipeline/pipeline.py:74-79`
- **Signature:** `async def process(self, file_bytes: bytes, content_type: str, user_id: str) -> ProcessedImage`
- **Plan match:** Matches -- story 3-3 calls this before calling FaceAnalysisService.analyze()

### ProcessedImage (app/image_pipeline/models.py)

- **Source:** `app/image_pipeline/models.py:23-29`
- **Signature:** `@dataclass(frozen=True) class ProcessedImage: storage_key: str | None; image_id: UUID; status: Literal["cleared", "quarantined"]`
- **Plan match:** Matches -- `storage_key` from ProcessedImage is passed to FaceAnalysisService.analyze()

### get_supabase_service (app/db/client.py)

- **Source:** `app/db/client.py:10`
- **Signature:** `def get_supabase_service() -> Client`
- **Plan match:** Matches

### get_current_user (app/api/deps.py)

- **Source:** `app/api/deps.py:40-43`
- **Signature:** `def get_current_user(authorization: Annotated[str | None, Header()] = None, supabase: Client = Depends(get_supabase)) -> UserClaims`
- **Plan match:** Matches -- Amended by A-8 (sub: Required[str])

### lifespan (app/main.py)

- **Source:** `app/main.py:22-41`
- **Signature:** `async def lifespan(app: FastAPI) -> AsyncIterator[None]`
- **Plan match:** Matches -- this story modifies this function to add MediaPipe model preloading

### FaceAnalysisService.analyze (interface contract -- this story defines it)

- **Source:** Not yet implemented -- this story creates it
- **Signature:** `async def analyze(self, image_storage_key: str) -> AnalysisResult`
- **Plan match:** UNVERIFIED -- source not yet implemented, using plan contract

## Tasks

- [x] Task 1: Create `app/face_analysis/models.py` and `app/face_analysis/__init__.py`
  - Maps to: AC-1 (FaceShape enum, AnalysisResult, Suggestion dataclasses), AC-5 (no attractiveness language in model types)
  - Files: `app/face_analysis/__init__.py`, `app/face_analysis/models.py`

- [x] Task 2: Create `app/face_analysis/landmark_extractor.py` -- MediaPipe FaceMesh wrapper + preload function + MockFaceAnalysisAdapter
  - Maps to: AC-1 (landmark extraction), AC-2 (preload_model function), AC-4 (landmarks ephemeral)
  - Files: `app/face_analysis/landmark_extractor.py`

- [x] Task 3: Create `app/face_analysis/classifier.py` -- FaceShapeClassifier
  - Maps to: AC-1 (face_shape classification from {oval, round, square, heart, oblong})
  - Files: `app/face_analysis/classifier.py`

- [x] Task 4: Create `app/face_analysis/symmetry_scorer.py` -- SymmetryScorer
  - Maps to: AC-1 (symmetry_score in [0.0, 1.0])
  - Files: `app/face_analysis/symmetry_scorer.py`

- [x] Task 5: Create `app/face_analysis/recommendation.py` -- RecommendationEngine
  - Maps to: AC-1 (top 5 recommendations), AC-5 (no attractiveness language, tied to face shape + proportions)
  - Files: `app/face_analysis/recommendation.py`

- [x] Task 6: Create `app/face_analysis/service.py` -- FaceAnalysisService orchestrator + adapter resolution
  - Maps to: AC-1 (full pipeline), AC-3 (<=3s latency), AC-4 (landmarks not stored)
  - Files: `app/face_analysis/service.py`

- [x] Task 7: Modify `app/main.py` lifespan -- add MediaPipe model preload + update `requirements.txt`
  - Maps to: AC-2 (model pre-loaded at startup, health check gate)
  - Files: `app/main.py`, `requirements.txt`

## must_haves

truths:
  - "FaceAnalysisService.analyze() given an image with a single face returns AnalysisResult with face_shape from {oval, round, square, heart, oblong}"
  - "FaceAnalysisService.analyze() given an image with a single face returns symmetry_score in [0.0, 1.0]"
  - "FaceAnalysisService.analyze() returns exactly 5 recommendations, each with rank, category, suggestion_text, and rationale"
  - "No recommendation suggestion_text contains the words 'attractive', 'attractiveness', 'beauty score', 'ranking', or 'rated'"
  - "MediaPipe FaceMesh model is loaded during FastAPI lifespan startup before yield -- not on first request"
  - "GET /health returns HTTP 200 only after lifespan startup completes (model preloaded)"
  - "Landmark vectors (468 3D coordinates) are never written to the analyses table or any other database table"
  - "Only face_shape, symmetry_score, and recommendations are persisted in the analyses table"
  - "MockFaceAnalysisAdapter returns a deterministic AnalysisResult when ADAPTER__FACE_ANALYSIS_ADAPTER=mock"

artifacts:
  - path: "app/face_analysis/__init__.py"
  - path: "app/face_analysis/models.py"
    contains: ["FaceShape", "AnalysisResult", "Suggestion", "oval", "round", "square", "heart", "oblong", "symmetry_score", "recommendations"]
  - path: "app/face_analysis/landmark_extractor.py"
    contains: ["LandmarkExtractor", "preload_model", "FaceMesh", "MediaPipeAdapter", "MockFaceAnalysisAdapter"]
  - path: "app/face_analysis/classifier.py"
    contains: ["FaceShapeClassifier", "classify", "FaceShape"]
  - path: "app/face_analysis/symmetry_scorer.py"
    contains: ["SymmetryScorer", "score", "symmetry"]
  - path: "app/face_analysis/recommendation.py"
    contains: ["RecommendationEngine", "recommend", "Suggestion"]
  - path: "app/face_analysis/service.py"
    contains: ["FaceAnalysisService", "analyze", "image_storage_key", "AnalysisResult", "_get_face_analysis_adapter"]

key_links:
  - pattern: "from app.config import settings"
    in: ["app/face_analysis/service.py", "app/face_analysis/landmark_extractor.py"]
  - pattern: "from app.face_analysis.models import"
    in: ["app/face_analysis/service.py", "app/face_analysis/classifier.py", "app/face_analysis/symmetry_scorer.py", "app/face_analysis/recommendation.py", "app/face_analysis/landmark_extractor.py"]
  - pattern: "from app.face_analysis.service import FaceAnalysisService"
    in: ["app/api/analyses.py"]
  - pattern: "ADAPTER__FACE_ANALYSIS_ADAPTER"
    in: ["app/face_analysis/service.py", "app/main.py"]
  - pattern: "preload_model"
    in: ["app/face_analysis/landmark_extractor.py", "app/main.py"]
  - pattern: "run_in_executor"
    in: ["app/face_analysis/service.py"]

## Dev Notes

### Testing Approach

Zero automated tests per QA skill decision. All verification is via manual testing against local Supabase:
- Upload a test selfie via `POST /analyses` (story 3-3 endpoint, or direct FaceAnalysisService call via Python REPL)
- Verify returned `face_shape` is one of the 5 valid values
- Verify `symmetry_score` is between 0.0 and 1.0
- Verify exactly 5 recommendations returned, each with rank, category, suggestion_text, rationale
- Grep all recommendation text for prohibited words: "attractive", "beauty score", "ranking", "rated"
- Query `analyses` table: verify NO landmark data stored, only `face_shape`, `symmetry_score`, `recommendations` JSONB
- `ADAPTER__FACE_ANALYSIS_ADAPTER=mock` for testing non-analysis features; set to `mediapipe` for real analysis testing

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
- F4: UserClaims Required fields -- fixed via A-8 (use `Required[str]` for always-present fields)
- Code review caught missing explicit type annotations in service helpers -- always annotate return types

**Story 3-1 established:**
- Port/adapter pattern with lazy imports inside feature module (NOT in a separate `app/adapters/` directory)
- `_get_*_adapter()` factory functions with lazy imports based on config adapter selection
- `ProcessedImage` dataclass with `frozen=True`
- `datetime.now(tz=timezone.utc).isoformat()` for timestamps (not bare `now()`)
- Error response format: `{"error": {"code": "...", "message": "...", "retry_eligible": true/false}}`
- Pillow DecompressionBomb guard: set `PIL.Image.MAX_IMAGE_PIXELS` aligned with config
- Storage key format: `"{user_id}/{uuid}.{ext}"`
- Module docstrings with interface contract reference

**Story 3-1 review finding:**
- Port/adapter pattern with lazy imports was validated as the correct approach
- Supabase `Client` is synchronous -- async wrappers (`async def`) are fine but the underlying calls are sync

### Async + Sync Considerations

MediaPipe's `FaceMesh.process()` is a CPU-bound synchronous call. In an async FastAPI handler, this MUST be wrapped with `run_in_executor` to avoid blocking the event loop:

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

_executor = ThreadPoolExecutor(max_workers=4)

async def _run_sync(func, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, func, *args)
```

However, MediaPipe `FaceMesh` instances are NOT thread-safe when shared across threads. Options:
1. Create a new `FaceMesh` instance per request (lightweight after model is pre-loaded)
2. Use a pool of `FaceMesh` instances
3. Run in default executor with instance creation inside the executor call

Option 1 is simplest and sufficient for <=3s P95 latency target. The model weights are loaded once at startup; creating a new `FaceMesh` session reuses the pre-loaded weights.

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

Adapter configuration for face analysis:
- `ADAPTER__FACE_ANALYSIS_ADAPTER=mock` (default) -- no MediaPipe dependency needed, returns deterministic results
- `ADAPTER__FACE_ANALYSIS_ADAPTER=mediapipe` -- requires `mediapipe` in virtualenv, loads real model at startup

Environment variables relevant to this story:
- `SUPABASE_URL` -- local Supabase URL (from `supabase status`, typically `http://127.0.0.1:54321`)
- `SUPABASE_SERVICE_ROLE_KEY` -- local service role key (from `supabase status`)
- `ADAPTER__FACE_ANALYSIS_ADAPTER` -- `"mock"` (default) or `"mediapipe"` (real face analysis)
- `SIGNED_URL_EXPIRY_SECONDS` -- `3600` (default) -- used when fetching image from storage for analysis

### Library Versions

- **mediapipe:** 0.10.32 (verified 2026-03-16 via PyPI)
- **numpy:** 2.4.3 (verified 2026-03-16 via PyPI) -- mediapipe depends on numpy; pin explicitly
- **Pillow:** 12.1.1 (already pinned in requirements.txt)
- **supabase-py:** 2.15.1 (pinned in requirements.txt)

### MediaPipe FaceMesh Configuration

```python
import mediapipe as mp

mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    static_image_mode=True,      # single image (not video stream)
    max_num_faces=2,             # detect up to 2 to enforce single-face requirement
    refine_landmarks=True,       # iris landmarks for enhanced accuracy
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
)
```

- `max_num_faces=2` is set to detect multiple faces -- if `results.multi_face_landmarks` has >1 entry, raise `MULTIPLE_FACES` error.
- `static_image_mode=True` -- required for single-image analysis (disables temporal smoothing).
- `refine_landmarks=True` -- enables iris landmarks (478 total with iris) for more precise measurements.

### Face Shape Classification Ratios

The classifier uses these landmark-derived measurements:

| Measurement | Landmarks | Formula |
|-------------|-----------|---------|
| Face length | Forehead top (10) to chin (152) | Euclidean distance |
| Forehead width | Left temple (70) to right temple (300) | Euclidean distance |
| Cheekbone width | Left cheek (234) to right cheek (454) | Euclidean distance |
| Jaw width | Left jaw (172) to right jaw (397) | Euclidean distance |
| Jaw angle | Jaw corners relative to chin | Angle computation |

Classification rules (applied in order, first match wins):

1. **Oblong:** face_length / cheekbone_width > 1.3
2. **Round:** face_length / cheekbone_width < 1.1 AND jaw_width / cheekbone_width > 0.85
3. **Square:** face_length / cheekbone_width < 1.1 AND jaw_angle > 140 degrees
4. **Heart:** forehead_width / jaw_width > 1.2
5. **Oval:** (default) none of the above

### Recommendation Categories

Each face shape maps to a set of improvement suggestions drawn from these categories:

| Category | Example Suggestions |
|----------|-------------------|
| `hair` | Hairstyle changes to balance proportions |
| `eyebrows` | Eyebrow shaping relative to face shape |
| `skincare` | Contouring and highlighting zones for face shape |
| `accessories` | Eyeglass frame shape, earring style |
| `grooming` | Facial hair shaping (if applicable) |

All suggestions are phrased as positive style advice. Prohibited language: "attractive", "beauty score", "unattractive", "ugly", "ranking", "rated", "improve your looks". Every suggestion text must reference the user's specific face shape and measurements.

## Wave Structure

Wave 1: [Task 1, Task 2, Task 3, Task 4, Task 5] -- independent, no shared output files
  - Task 1: models.py (dataclasses/enums only -- no deps on other tasks)
  - Task 2: landmark_extractor.py (imports from models.py but models.py has no deps on extractor)
  - Task 3: classifier.py (imports FaceShape from models.py only)
  - Task 4: symmetry_scorer.py (standalone computation, imports models.py)
  - Task 5: recommendation.py (imports Suggestion from models.py, FaceShape)

Wave 2: [Task 6] -- depends on all Wave 1 outputs (service orchestrator imports all modules)

Wave 3: [Task 7] -- depends on Task 6 (lifespan modification + requirements.txt after service code is complete)
