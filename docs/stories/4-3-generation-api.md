---
id: "4-3-generation-api"
status: ready
created: 2026-03-17
---

# Story: Generation API — POST /generate, Job Polling & Cancel

## User Story

As a registered user, I want to trigger glow-up generation, poll for job status, and cancel in-flight jobs, so that I see my result within 30 seconds and never lose a credit to a failure.

## Acceptance Criteria

- Given `POST /analyses/{id}/generate` by a user with `can_generate = True`, When handled, Then: (1) `SELECT FOR UPDATE` checks in-flight count ≤ `MAX_CONCURRENT_GENERATIONS_PER_USER`; (2) `CreditLedger.reserve()` is called; (3) job is enqueued into the user's tier lane; HTTP 202 `{ job_id }` is returned.
- Given a second concurrent generation request from the same user while one is in-flight, When submitted, Then HTTP 409 `CONCURRENT_LIMIT` is returned; credit is not reserved (AC-A11).
- Given any generation failure (timeout, provider error, identity preservation failed), When the worker fails, Then `CreditLedger.release()` is called before the error response; `GET /jobs/{id}` reflects the failure reason; the credit balance is unchanged compared to before the job started (AC-U3, AC-D2).
- Given `POST /jobs/{id}/cancel` called before completion, When handled, Then `CreditLedger.release()` is called; the job transitions to `status='cancelled'`; trial count and credit balance are unchanged (AC-U1).
- Given `GET /jobs/{id}` with `status='queued'`, When responded, Then `{ status: 'queued', estimated_wait_seconds: <int> }` is returned within ≤2s (AC-NFR2 progress indicator).

## Architecture Guardrails

### Technology Stack

- **Backend:** Python 3.12 + FastAPI 0.115.12 (pinned in requirements.txt)
- **Database:** Supabase PostgreSQL via supabase-py 2.15.1 (pinned in requirements.txt)
- **Cache/Queue:** Redis 7.x via redis-py 5.2.1 (pinned in requirements.txt)
- **Job Queue:** ARQ 0.27.0 (async Redis-based job queue with priority lanes)
- **Auth:** JWT validation via PyJWT 2.10.1 (pinned in requirements.txt)
- **Config:** pydantic-settings 2.9.1 (pinned in requirements.txt)
- **No automated tests** -- per QA skill decision; zero test code written during development

### Non-Negotiable Boundaries

- **C-2 LOCKED:** No attractiveness score or ranking in any API response, UI element, or data model field.
- **AC-A1:** Reserve-before-enqueue for all credit and trial consumption.
- **AC-D1:** All entitlement checks route through `EntitlementService`; no handler reads subscription or credit fields directly.

### This is a Thin API Layer Story

This story creates three endpoints that wire together existing services. No generation logic lives here -- the ARQ worker (Story 4-2) handles all generation processing. This story:

1. **POST /analyses/{id}/generate** -- Entitlement check, concurrent guard, credit reserve, create glow_up_jobs row, enqueue ARQ job, return 202 with job_id.
2. **GET /jobs/{id}** -- Read glow_up_jobs row, compute estimated_wait_seconds, return status.
3. **POST /jobs/{id}/cancel** -- Transition to cancelled, release credit if reserved.

### `glow_up_jobs` Table Schema

Migration files are the canonical schema source (see `docs/plan.md` Story 1-1). For the exact `glow_up_jobs` columns, constraints, and indexes, refer to **migration 0006** (`app/migrations/0006_glow_up_jobs.sql`). architecture.md provides the conceptual model but may use different column names or omit columns added during implementation.

### `analyses` Table Schema (Relevant Columns)

```sql
CREATE TABLE analyses (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status              TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    original_image_id   UUID REFERENCES images(id),
    face_shape          TEXT CHECK (face_shape IN ('oval', 'round', 'square', 'heart', 'oblong')),
    symmetry_score      FLOAT CHECK (symmetry_score BETWEEN 0.0 AND 1.0),
    recommendations     JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### `usage_events` Table Schema (Amended by A-5)

```sql
CREATE TABLE usage_events (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    action     TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'committed',
    job_id     TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX idx_usage_events_job_id ON usage_events(job_id) WHERE job_id IS NOT NULL;
CREATE INDEX idx_usage_events_user_action_time ON usage_events(user_id, action, created_at DESC);
```

`status` lifecycle for generation:
- `reserved` -- set when ARQ job is enqueued (credit deducted from balance)
- `committed` -- set when generation completes successfully
- `released` -- set when generation fails (credit restored)

For non-credit tiers (daily/weekly/monthly), events are `committed` immediately at enqueue time. Counting only includes `committed` events.

### Queue Lane Selection

Map the user's tier slug to the correct queue lane at enqueue time:

```python
from app.generation.models import LANE_PREMIUM, LANE_CREDIT, LANE_TRIAL

_SLUG_TO_LANE: dict[str, str] = {
    "free": LANE_TRIAL,        # generation:trial
    "credits": LANE_CREDIT,    # generation:credit
    "premium": LANE_PREMIUM,   # generation:premium
}
```

The tier slug comes from `tier_record.slug` (fetched via `EntitlementService._get_tier(user_id)`). The `user_tier_at_enqueue` column on `glow_up_jobs` stores the public tier name (e.g., `"TRIAL"`, `"CREDIT_HOLDER"`, `"PREMIUM"`) for analytics -- use the `_SLUG_TO_TIER_NAME` mapping from `app/api/entitlement.py` or inline the equivalent.

### Concurrent Generation Guard (Atomic Redis INCR)

The corrections document (item 15) specifies: replace the read-only check with atomic INCR at the API layer. The pattern:

```python
concurrent_key = f"concurrent:{user_id}"
current = await redis.incr(concurrent_key)
await redis.expire(concurrent_key, settings.GENERATION_TIMEOUT_SECONDS + 60)

if current > tier.max_concurrent_generations:
    await redis.decr(concurrent_key)  # Undo the increment
    # Return HTTP 409 CONCURRENT_LIMIT
    ...
```

This replaces the read-only GET check that EntitlementService._check_generation currently does. The API handler owns the atomic INCR; the worker also INCRs at job start (see worker.py:101) and DECRs at job end (worker.py:311). To avoid double-counting, the API handler should NOT INCR if the entitlement pre-check via `require_entitlement("generation")` already passed (which does a read-only check). Instead:

1. `require_entitlement("generation")` runs first as a FastAPI dependency -- performs the read-only concurrent check + credits/window check.
2. Inside the handler, do the atomic INCR + check + conditional DECR. This is the actual guard.
3. If the INCR check fails (concurrent limit exceeded), return 409.
4. The worker INCRs again at job start and DECRs at job end.

IMPORTANT: Since both the API handler (INCR) and the worker (INCR) increment, the counter may temporarily show `current_count + 1` higher than expected. The `max_concurrent_generations` check should account for this by checking `current > max_concurrent` (not `>=`) at the API layer, because the worker will also INCR. Alternatively, skip the handler INCR entirely and rely on `require_entitlement("generation")` read-only check (race window is acceptable per the EntitlementService comment at line 192-195). Choose the simpler approach: use `require_entitlement("generation")` as the sole concurrent guard. It performs a read-only Redis GET, which is sufficient given the worker also guards.

**Decision: Use `require_entitlement("generation")` as the concurrent guard.** It checks Redis GET for concurrent count AND credits/window limits. If it passes, proceed to reserve + enqueue. The worker also checks and will reject if over-limit. The small race window is documented as acceptable.

### Idempotency Key

The `idempotency_key` column on `glow_up_jobs` prevents double-enqueue. The client sends it in the request body. Format: a client-generated UUID. The handler attempts INSERT with the idempotency_key; if it violates the UNIQUE constraint, return the existing job's status (idempotent response).

### ARQ Enqueue Pattern

ARQ uses `ArqRedis.enqueue_job()` to put a job on a specific queue lane:

```python
from arq import create_pool
from arq.connections import RedisSettings

# Create an ARQ pool from the existing Redis connection
# In practice, use the same Redis URL as app.state.redis
pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))

job = await pool.enqueue_job(
    "process_generation_job",       # function name registered in WorkerSettings
    str(job_id),                     # positional arg: job_id as string
    _queue_name=queue_lane,          # e.g., "generation:premium"
)
```

Alternatively, since `app.state.redis` is already an `aioredis.Redis` instance, and ARQ uses Redis under the hood, you can create the pool once at app startup (in lifespan) and store it on `app.state.arq_pool`. This avoids creating a new pool per request.

### Cost Tracker Pre-Flight Checks

Before enqueue, check:
1. **Emergency stop:** `CostTracker.is_emergency_stopped()` -- if True, return 503 immediately.
2. **Queue depth:** `CostTracker.check_queue_depth()` -- if exceeds MAX_QUEUE_DEPTH, return 503.
3. **User daily cap:** `CostTracker.check_user_daily_cap(user_id)` -- if exceeded, return 429.
4. **Trial throttle:** If user is on trial lane, `CostTracker.should_throttle_trial()` -- if True, return 503.

### POST /analyses/{analysis_id}/generate -- API Contract

**Request:**
```json
{ "idempotency_key": "client-generated-uuid" }
```

**Response 202 (Accepted):**
```json
{
  "job_id": "uuid",
  "status": "queued",
  "estimated_wait_seconds": 15,
  "queue_position": 3
}
```

**Response 402 (Entitlement blocked -- from `require_entitlement`):**
```json
{
  "error": {
    "code": "TIER_LIMIT_CREDITS",
    "message": "No credits remaining",
    "detail": {
      "limit": null,
      "used": null,
      "retry_after": null,
      "reset_in_seconds": null,
      "upgrade_available": true
    }
  }
}
```

**Response 409 (Concurrent limit):**
```json
{ "error": { "code": "CONCURRENT_LIMIT", "message": "You already have a generation in progress." } }
```

**Response 404 (Analysis not found or not owned by user):**
```json
{ "detail": "Analysis not found" }
```

**Response 422 (Analysis not completed):**
```json
{ "error": { "code": "ANALYSIS_NOT_COMPLETED", "message": "Analysis must be completed before generating." } }
```

**Response 503 (Emergency stop / queue full):**
```json
{ "error": { "code": "SERVICE_UNAVAILABLE", "message": "Generation service temporarily unavailable. Please try again." } }
```

### GET /jobs/{job_id} -- API Contract

**Response 200 (Queued):**
```json
{
  "job_id": "uuid",
  "status": "queued",
  "estimated_wait_seconds": 15
}
```

**Response 200 (Processing):**
```json
{
  "job_id": "uuid",
  "status": "processing",
  "elapsed_seconds": 8,
  "estimated_wait_seconds": 12
}
```

**Response 200 (Completed):**
```json
{
  "job_id": "uuid",
  "status": "completed",
  "before_image_url": "https://...",
  "after_image_url": "https://...",
  "identity_preserved": true
}
```

**Response 200 (Failed):**
```json
{
  "job_id": "uuid",
  "status": "failed",
  "failure_reason": "GENERATION_TIMEOUT",
  "credit_refunded": true,
  "retry_eligible": true
}
```

For `IDENTITY_PRESERVATION_FAILED` failures, include `retry_eligible: true` with guidance (corrections.md item for Story 4-3):
```json
{
  "job_id": "uuid",
  "status": "failed",
  "failure_reason": "IDENTITY_PRESERVATION_FAILED",
  "credit_refunded": true,
  "retry_eligible": true,
  "user_guidance": "Try a clearer photo or a less dramatic style."
}
```

**Response 200 (Cancelled):**
```json
{
  "job_id": "uuid",
  "status": "cancelled",
  "credit_refunded": true
}
```

**Response 404:**
```json
{ "detail": "Job not found" }
```

### POST /jobs/{job_id}/cancel -- API Contract

**Response 200 (Cancelled):**
```json
{ "job_id": "uuid", "status": "cancelled", "credit_refunded": true }
```

**Response 409 (Already completed/failed/cancelled):**
```json
{ "error": { "code": "JOB_NOT_CANCELLABLE", "message": "Job is already completed." } }
```

**Response 404:**
```json
{ "detail": "Job not found" }
```

### Error Codes and HTTP Status Mapping

| Code | HTTP | When | Credit Impact |
|------|------|------|--------------|
| `TIER_LIMIT_DAILY` | 429 | Daily limit hit (from `require_entitlement`) | None |
| `TIER_LIMIT_CREDITS` | 402 | No credits remaining | None |
| `TIER_CONCURRENT_LIMIT` | 429 | In-flight count at max | None |
| `CONCURRENT_LIMIT` | 409 | Concurrent guard in handler (plan AC says 409) | None |
| `ANALYSIS_NOT_COMPLETED` | 422 | Analysis not in `completed` status | None |
| `SERVICE_UNAVAILABLE` | 503 | Emergency stop / queue full | None |
| `JOB_NOT_CANCELLABLE` | 409 | Job already in terminal state | None |

Note: The plan's AC-2 specifies HTTP 409 for concurrent limit. The `require_entitlement("generation")` dependency returns 429 for `TIER_CONCURRENT_LIMIT`. To satisfy the AC verbatim, the handler should catch the 429 from `require_entitlement` when the error code is `TIER_CONCURRENT_LIMIT` and re-raise as 409, OR perform the concurrent check in the handler itself after `require_entitlement` passes. Choose the simpler approach: let `require_entitlement` handle it as 429, but document that the AC says 409. The implement agent should use 409 for concurrent limit to match the AC.

**Resolution:** Use 409 for concurrent limit to match the AC verbatim. Do NOT rely on `require_entitlement` for the concurrent check. Instead, perform the concurrent check in the handler after `require_entitlement` passes (which still checks credits/window limits). The handler reads Redis `concurrent:{user_id}` and compares against `tier.max_concurrent_generations`. If over limit, return 409 with `CONCURRENT_LIMIT`.

### Estimated Wait Seconds Calculation

For `GET /jobs/{id}` when status is `queued` or `processing`:

```python
# Rough estimate: count jobs ahead in the same lane + average processing time
queued_ahead = await redis.llen(f"arq:queue:{job.queue_lane}")
avg_seconds_per_job = 15  # Approximate based on generation pipeline (~10-20s)
estimated_wait = queued_ahead * avg_seconds_per_job

# For processing jobs, subtract elapsed time
if job.status == "processing":
    elapsed = (now - job.updated_at).total_seconds()
    estimated_wait = max(0, avg_seconds_per_job - int(elapsed))
```

### Image URL Generation for Completed Jobs

For completed jobs, generate signed URLs for before/after images:

```python
before_url = supabase.storage.from_("raw-selfies").create_signed_url(
    source_image.storage_key, settings.SIGNED_URL_EXPIRY_SECONDS
)["signedURL"]

after_url = supabase.storage.from_("generated-images").create_signed_url(
    generated_image.storage_key, settings.SIGNED_URL_EXPIRY_SECONDS
)["signedURL"]
```

### File Structure for This Story

```
app/
  api/
    generation.py       # NEW: POST /analyses/{id}/generate, GET /jobs/{id}, POST /jobs/{id}/cancel
  main.py               # MODIFY: register generation router under v1
```

### Router Registration Pattern

From `app/main.py`, routers are registered under the `/v1` prefix:

```python
from app.api import analyses, auth, entitlement, generation, health

v1 = APIRouter(prefix="/v1")
v1.include_router(auth.router, prefix="/auth")
v1.include_router(entitlement.router)
v1.include_router(analyses.router)
v1.include_router(generation.router)  # NEW
app.include_router(v1)
```

The generation router defines routes at:
- `POST /analyses/{analysis_id}/generate` (under the analyses namespace per architecture router table)
- `GET /jobs/{job_id}`
- `POST /jobs/{job_id}/cancel`

### ARQ Pool Initialization in Lifespan

Add ARQ pool creation to the lifespan in `app/main.py`:

```python
from arq import create_pool
from arq.connections import RedisSettings

# In lifespan startup:
app.state.arq_pool = await create_pool(
    RedisSettings.from_dsn(settings.REDIS_URL)
)

# In lifespan shutdown:
await app.state.arq_pool.aclose()
```

This allows handlers to call `request.app.state.arq_pool.enqueue_job(...)`.

### Entitlement Dependency Pattern (Amended by A-5)

`require_entitlement("generation")` is used as a FastAPI Depends on the generate endpoint. It checks:
1. Concurrent guard (Redis read-only GET of `concurrent:{user_id}`)
2. Credits check (if credits-based tier)
3. Time-window/total limit check

If it fails, it raises HTTPException with the structured error response. The handler does NOT need to re-check credits/window limits -- only the concurrent 409 override and pre-flight cost checks.

```python
from app.api.deps import get_current_user, get_supabase, get_redis, require_entitlement, get_entitlement_service
```

### Credit Reserve + Usage Event Flow (AC-1)

For credit-based tiers:
1. `CreditLedger.reserve(user_id)` -- creates reservation + ledger entry atomically via RPC
2. Insert `usage_events` row with `status='reserved'`, `job_id=str(job_id)`
3. Insert `glow_up_jobs` row with `credit_reservation_id=reservation_id`
4. Enqueue ARQ job

For non-credit tiers (daily/monthly):
1. Insert `usage_events` row with `status='committed'` immediately (no reserve needed)
2. Insert `glow_up_jobs` row with `credit_reservation_id=NULL`
3. Enqueue ARQ job

### Cancel Flow

1. Fetch job from `glow_up_jobs` WHERE `id = job_id` AND `user_id = claims["sub"]`
2. If not found: 404
3. If status in (`completed`, `failed`, `cancelled`): 409 `JOB_NOT_CANCELLABLE`
4. Update job: `status = 'cancelled'`, `failure_reason = 'CANCELLED'`
5. If `credit_reservation_id` is not None: `CreditLedger.release(reservation_id)`
6. Update `usage_events` WHERE `job_id = str(job_id)`: `status = 'released'`
7. Return 200 with cancelled confirmation

### JobStatus Enum (from app/generation/models.py)

```python
class JobStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

### Failure Reason Constants (from app/generation/models.py)

```python
FAILURE_IDENTITY = "IDENTITY_PRESERVATION_FAILED"
FAILURE_NSFW = "NSFW_CONTENT_DETECTED"
FAILURE_TIMEOUT = "GENERATION_TIMEOUT"
FAILURE_PROVIDER = "PROVIDER_ERROR"
FAILURE_CANCELLED = "CANCELLED"
```

### Queue Lane Constants (from app/generation/models.py)

```python
LANE_PREMIUM = "generation:premium"
LANE_CREDIT = "generation:credit"
LANE_TRIAL = "generation:trial"
QUEUE_LANES = [LANE_PREMIUM, LANE_CREDIT, LANE_TRIAL]
```

### DB-Driven Tier System (Amended by A-4)

Tiers are rows in the `tiers` table. The `TierRecord` dataclass:

```python
@dataclass(frozen=True)
class TierRecord:
    id: UUID
    slug: str                            # "free", "credits", "premium"
    display_name: str
    is_default: bool
    is_active: bool
    generation_type: str                 # LimitType value
    generation_limit: int | None
    generation_period_seconds: int | None
    advisor_nudges_type: str
    advisor_nudges_limit: int | None
    advisor_nudges_period_seconds: int | None
    max_concurrent_generations: int       # 1 (free), 2 (credits), 3 (premium)
    identity_similarity_threshold: float
    feature_advisor_chat: bool
    feature_visual_comparison: bool
    credits_based: bool                  # True for "credits" tier
```

Tier seed data:

| slug | generation_type | generation_limit | credits_based | max_concurrent |
|------|-----------------|-----------------|---------------|----------------|
| `free` | daily | 1 | false | 1 |
| `credits` | credits | NULL | true | 2 |
| `premium` | monthly | 100 | false | 3 |

### Correction: Identity Failure Response (from corrections.md)

For Story 4-3, include `retry_eligible: true` with user-facing guidance on identity failure. The GET /jobs/{id} response for `IDENTITY_PRESERVATION_FAILED` must include:
```json
{
  "retry_eligible": true,
  "user_guidance": "Try a clearer photo or a less dramatic style."
}
```

## Verified Interfaces

### EntitlementService.check (app/entitlement/service.py)

- **Source:** `app/entitlement/service.py:171-187`
- **Signature:** `async def check(self, user_id: UUID, action: str) -> EntitlementResult`
- **Plan match:** Matches plan contract

### EntitlementService._get_tier (app/entitlement/service.py)

- **Source:** `app/entitlement/service.py:295-308`
- **Signature:** `async def _get_tier(self, user_id: UUID) -> TierRecord`
- **Plan match:** Matches -- returns TierRecord from DB via Redis cache

### CreditLedger.reserve (app/entitlement/ledger.py)

- **Source:** `app/entitlement/ledger.py:52-74`
- **Signature:** `def reserve(self, user_id: UUID) -> UUID`
- **Plan match:** Matches plan contract `reserve(user_id: UUID) -> UUID`

### CreditLedger.release (app/entitlement/ledger.py)

- **Source:** `app/entitlement/ledger.py:76-96`
- **Signature:** `def release(self, reservation_id: UUID) -> None`
- **Plan match:** Matches plan contract

### CreditLedger.commit (app/entitlement/ledger.py)

- **Source:** `app/entitlement/ledger.py:98-116`
- **Signature:** `def commit(self, reservation_id: UUID) -> None`
- **Plan match:** Matches plan contract

### CostTracker (app/generation/cost_tracker.py)

- **Source:** `app/generation/cost_tracker.py:24-157`
- **Signatures:**
  - `def __init__(self, redis_client: aioredis.Redis) -> None`
  - `async def is_emergency_stopped(self) -> bool` (line 86)
  - `async def check_queue_depth(self, max_depth: int = 15000) -> bool` (line 91)
  - `async def check_user_daily_cap(self, user_id: str, max_per_day: int = 50) -> bool` (line 108)
  - `async def should_throttle_trial(self) -> bool` (line 72)
- **Plan match:** Matches

### get_current_user (app/api/deps.py)

- **Source:** `app/api/deps.py:41-58`
- **Signature:** `def get_current_user(authorization: Annotated[str | None, Header()] = None, supabase: Client = Depends(get_supabase)) -> UserClaims`
- **Plan match:** Matches -- Amended by A-8 (sub: Required[str])

### get_supabase (app/api/deps.py)

- **Source:** `app/api/deps.py:26-28`
- **Signature:** `def get_supabase(request: Request) -> Client`
- **Plan match:** Matches

### get_redis (app/api/deps.py)

- **Source:** `app/api/deps.py:31-33`
- **Signature:** `def get_redis(request: Request) -> aioredis.Redis`
- **Plan match:** Matches

### require_entitlement (app/api/deps.py)

- **Source:** `app/api/deps.py:89-126`
- **Signature:** `def require_entitlement(action: str)` -- returns an async dependency function
- **Plan match:** Matches -- Amended by A-5

### get_entitlement_service (app/api/deps.py)

- **Source:** `app/api/deps.py:66-75`
- **Signature:** `def get_entitlement_service(request: Request) -> EntitlementService`
- **Plan match:** Matches

### UserClaims (app/api/middleware/auth.py)

- **Source:** `app/api/middleware/auth.py:22-35`
- **Signature:** `class UserClaims(TypedDict, total=False)` with `sub: Required[str]`, `exp: Required[int]`
- **Plan match:** Matches -- Amended by A-8

### process_generation_job (app/generation/worker.py)

- **Source:** `app/generation/worker.py:44`
- **Signature:** `async def process_generation_job(ctx: dict, job_id: str) -> None`
- **Plan match:** Matches plan contract. Note: `job_id` parameter is `str`, not `UUID`.

### JobStatus (app/generation/models.py)

- **Source:** `app/generation/models.py:15-21`
- **Signature:** `class JobStatus(StrEnum)` with values PENDING, QUEUED, PROCESSING, COMPLETED, FAILED, CANCELLED
- **Plan match:** Matches

### WorkerSettings (app/generation/worker_settings.py)

- **Source:** `app/generation/worker_settings.py:51-73`
- **Signature:** `class WorkerSettings` with `functions = [process_generation_job]`, `queues = QUEUE_LANES`
- **Plan match:** Matches -- ARQ worker processes from the three priority lanes

### create_app (app/main.py)

- **Source:** `app/main.py:66-93`
- **Signature:** `def create_app() -> FastAPI`
- **Plan match:** Matches -- v1 APIRouter prefix pattern established

### lifespan (app/main.py)

- **Source:** `app/main.py:22-63`
- **Signature:** `async def lifespan(app: FastAPI) -> AsyncIterator[None]`
- **Plan match:** Matches -- this story adds ARQ pool to startup

### Settings (app/config.py)

- **Source:** `app/config.py:1-84`
- **Relevant fields:**
  - `REDIS_URL: str = "redis://localhost:6379/0"` (line 19)
  - `MAX_CONCURRENT_GENERATIONS_PER_USER: int = 3` (line 47)
  - `GENERATION_TIMEOUT_SECONDS: int = 60` (line 56)
  - `SIGNED_URL_EXPIRY_SECONDS: int = 3600` (line 52)
  - `GENERATION_EMERGENCY_STOP: bool = False` (line 62)
  - `MAX_GENERATIONS_PER_USER_PER_DAY: int = 50` (line 63)
  - `MAX_QUEUE_DEPTH: int = 15000` (line 64)
- **Plan match:** Matches

## Tasks

- [ ] Task 1: Add ARQ pool initialization to `app/main.py` lifespan
  - Maps to: AC-1 (job must be enqueued)
  - Files: `app/main.py`

- [ ] Task 2: Create `app/api/generation.py` -- POST /analyses/{analysis_id}/generate endpoint
  - Maps to: AC-1 (entitlement check, concurrent guard, credit reserve, enqueue, return 202), AC-2 (concurrent limit returns 409)
  - Files: `app/api/generation.py`

- [ ] Task 3: Add GET /jobs/{job_id} endpoint to `app/api/generation.py`
  - Maps to: AC-3 (failure reason reflected in job status), AC-5 (estimated_wait_seconds returned)
  - Files: `app/api/generation.py`

- [ ] Task 4: Add POST /jobs/{job_id}/cancel endpoint to `app/api/generation.py`
  - Maps to: AC-4 (cancel releases credit, transitions to cancelled)
  - Files: `app/api/generation.py`

- [ ] Task 5: Register generation router in `app/main.py`
  - Maps to: AC-1, AC-3, AC-4, AC-5 (endpoints must be reachable)
  - Files: `app/main.py`

## must_haves

truths:
  - "POST /v1/analyses/{id}/generate with a user who has can_generate=True returns HTTP 202 with JSON containing job_id and status='queued'"
  - "POST /v1/analyses/{id}/generate creates a glow_up_jobs row with status='queued', user_id matching JWT sub, analysis_id matching the path parameter, and idempotency_key matching the request body"
  - "POST /v1/analyses/{id}/generate for a credit-based tier calls CreditLedger.reserve(user_id) and stores credit_reservation_id on the glow_up_jobs row"
  - "POST /v1/analyses/{id}/generate enqueues an ARQ job on the correct lane based on user tier slug (free->generation:trial, credits->generation:credit, premium->generation:premium)"
  - "POST /v1/analyses/{id}/generate with a concurrent generation in-flight returns HTTP 409 with error code CONCURRENT_LIMIT and does not reserve credit"
  - "POST /v1/analyses/{id}/generate with the same idempotency_key returns the existing job instead of creating a duplicate"
  - "GET /v1/jobs/{id} for a queued job returns HTTP 200 with status='queued' and estimated_wait_seconds as an integer"
  - "GET /v1/jobs/{id} for a completed job returns HTTP 200 with status='completed', before_image_url and after_image_url as signed URLs"
  - "GET /v1/jobs/{id} for a failed job with IDENTITY_PRESERVATION_FAILED includes retry_eligible=true and user_guidance string"
  - "GET /v1/jobs/{id} for a failed job includes credit_refunded=true"
  - "POST /v1/jobs/{id}/cancel on a queued or processing job returns HTTP 200 with status='cancelled' and credit_refunded=true"
  - "POST /v1/jobs/{id}/cancel calls CreditLedger.release(reservation_id) when credit_reservation_id exists"
  - "POST /v1/jobs/{id}/cancel on a completed job returns HTTP 409 with error code JOB_NOT_CANCELLABLE"
  - "POST /v1/jobs/{id}/cancel updates the usage_events row for this job to status='released'"
  - "GET /v1/jobs/{id} called by a user who does not own the job returns HTTP 404"

artifacts:
  - path: "app/api/generation.py"
    contains: ["router", "APIRouter", "generate", "get_job", "cancel_job", "require_entitlement", "CreditLedger", "JobStatus", "glow_up_jobs", "arq_pool", "enqueue_job", "estimated_wait_seconds"]
  - path: "app/main.py"
    contains: ["generation", "arq_pool", "create_pool"]

key_links:
  - pattern: "from app.api.deps import get_current_user, get_supabase, get_redis"
    in: ["app/api/generation.py"]
  - pattern: "from app.api.deps import require_entitlement"
    in: ["app/api/generation.py"]
  - pattern: "from app.api.deps import get_entitlement_service"
    in: ["app/api/generation.py"]
  - pattern: "from app.entitlement.ledger import CreditLedger"
    in: ["app/api/generation.py"]
  - pattern: "from app.generation.models import JobStatus"
    in: ["app/api/generation.py"]
  - pattern: "from app.generation.models import LANE_PREMIUM, LANE_CREDIT, LANE_TRIAL"
    in: ["app/api/generation.py"]
  - pattern: "from app.generation.cost_tracker import CostTracker"
    in: ["app/api/generation.py"]
  - pattern: "from app.api import"
    in: ["app/main.py"]
  - pattern: "generation.router"
    in: ["app/main.py"]
  - pattern: "create_pool"
    in: ["app/main.py"]

## Dev Notes

### Testing Approach

Zero automated tests per QA skill decision. All verification is via manual testing against local Supabase + Redis + ARQ worker:

- Start local Supabase: `supabase start`
- Start Redis: `docker compose up -d`
- Start API: `./scripts/dev-start.sh`
- Start ARQ worker: `arq app.generation.worker_settings.WorkerSettings` (from project root)
- Create an analysis first via `POST /v1/analyses` with a selfie
- Call `POST /v1/analyses/{analysis_id}/generate` with `{"idempotency_key": "test-uuid"}` -- expect 202
- Poll `GET /v1/jobs/{job_id}` -- expect status progression: queued -> processing -> completed/failed
- Test cancel: enqueue a job, immediately call `POST /v1/jobs/{job_id}/cancel` -- expect 200 cancelled
- Test concurrent: enqueue one job, immediately try to enqueue another -- expect 409 (for free tier with max_concurrent=1)
- Test idempotency: re-send same idempotency_key -- expect same job_id returned
- Verify credit balance unchanged after failed/cancelled jobs via `GET /v1/entitlement`

### Conventions from Prior Stories

**Story 1-1 established:**
- `from app.config import settings` is the canonical config import pattern
- All SQL: `snake_case` table and column names; `TIMESTAMPTZ` for all timestamps
- Tier constants at `app/constants/tiers.py` with fixed UUIDs

**Story 2-2 established:**
- `from app.api.deps import get_current_user, get_supabase` is the canonical dependency import
- `UserClaims` TypedDict with `sub: Required[str]` (Amended by A-8)
- Error responses use `raise HTTPException(status_code=..., detail=...)` pattern
- Supabase client from `request.app.state.supabase` via `get_supabase` dependency
- Logging: `logger = logging.getLogger(__name__)` at module top
- Router: `router = APIRouter(tags=["..."])`
- Request/Response models as Pydantic `BaseModel` subclasses

**Story 3-1 established:**
- Error response format: `{"error": {"code": "...", "message": "...", "retry_eligible": true/false}}`
- `datetime.now(tz=timezone.utc).isoformat()` for timestamps

**Story 3-3 established:**
- `POST /analyses` endpoint pattern: thin wiring layer, services raise HTTPException on failure
- Analysis row accessed via `supabase.table("analyses").select("*").eq("id", str(analysis_id)).maybe_single().execute()`
- Ownership check: `result.data["user_id"] != claims["sub"]` -> 403

**Story 4-1 established:**
- `EntitlementService(supabase, redis_client)` constructor
- `CreditLedger(supabase)` constructor
- `require_entitlement("generation")` and `get_entitlement_service` in `app/api/deps.py`
- Supabase `Client` methods are synchronous; `async def` handlers are fine
- Redis calls via `redis.asyncio` are truly async

**Story 4-2 established:**
- `process_generation_job(ctx, job_id: str)` -- ARQ worker function takes job_id as string
- Worker INCR/DECR on `concurrent:{user_id}` key at job start/end
- `JobStatus`, `LANE_*`, `FAILURE_*` constants in `app/generation/models.py`
- `CostTracker(redis)` for circuit breaker and cost tracking
- Job data written to `glow_up_jobs` table with columns from migration 0006

### Local Dev Environment

```bash
supabase start           # Local Supabase (DB + Auth + Storage)
docker compose up -d     # Redis
./scripts/dev-start.sh   # API (hot-reload)
arq app.generation.worker_settings.WorkerSettings  # ARQ worker
```

Environment variables:
- `SUPABASE_URL` -- from `supabase status` (typically `http://127.0.0.1:54321`)
- `SUPABASE_SERVICE_ROLE_KEY` -- from `supabase status`
- `SUPABASE_JWT_SECRET` -- JWT secret for auth validation
- `REDIS_URL` -- `redis://localhost:6379/0` (default)
- `ADAPTER__IMAGE_GENERATION_ADAPTER` -- `"mock"` (default) for local testing

### Library Versions

- **FastAPI:** 0.115.12 (pinned in requirements.txt; latest is 0.135.1 but project pins 0.115.12)
- **supabase-py:** 2.15.1 (pinned in requirements.txt)
- **redis-py:** 5.2.1 (pinned in requirements.txt)
- **ARQ:** 0.27.0 (verified 2026-03-17 via PyPI -- latest stable)
- **pydantic-settings:** 2.9.1 (pinned in requirements.txt)

## Wave Structure

Wave 1: [Task 1, Task 2, Task 3, Task 4] -- Task 1 modifies `app/main.py` (lifespan only). Tasks 2-4 all write to `app/api/generation.py` (same file, sequential dependency).

Revised: Tasks 2, 3, 4 share output file `app/api/generation.py` -- they CANNOT be in the same wave.

Wave 1: [Task 1] -- modifies `app/main.py` lifespan (ARQ pool init)
Wave 2: [Task 2] -- creates `app/api/generation.py` with POST /generate
Wave 3: [Task 3, Task 4] -- adds GET /jobs and POST /cancel to the same file. These two are independent sections of the file but since they share the same output file, they should be sequential. However, they don't depend on each other's output.

Revised for true independence:

Wave 1: [Task 1] -- `app/main.py` lifespan changes only
Wave 2: [Task 2, Task 3, Task 4] -- all three endpoints in `app/api/generation.py` (single file, implement together)
Wave 3: [Task 5] -- register router in `app/main.py` (depends on Task 2 creating the module)

Note: Tasks 2-4 share the same output file. They can be implemented as a single pass since the file is new and all three endpoints are defined together. The implement agent should create the full file in Task 2 and add the remaining endpoints in Tasks 3-4, or implement all three in Task 2 if treating as a single task.
