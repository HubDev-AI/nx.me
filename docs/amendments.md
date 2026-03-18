# Architecture Amendments

Amendments capture deviations from `docs/architecture.md` discovered during implementation or pre-implementation planning. Story-creator agent reads both files, using amended values where they conflict.

---

## A-9: Trending Feed — HN-Style Time-Decay Formula (Pre-Story 5-1)

- **Date**: 2026-03-16
- **Trigger**: Architecture specified `trending` sort as "reaction_count DESC + time factor" without defining the exact formula. Needed a concrete, proven ranking algorithm before Story 5-1 implementation.
- **Decision**: Adopted Hacker News-style time-decay ranking:
  ```
  score = reaction_count / (hours_since_post + 2) ^ 1.5
  ```
- **Gravity exponent**: `1.5` (lower than HN's `1.8`) — NXME has lower post volume than HN, so posts need to stay relevant longer.
- **Offset**: `+ 2` prevents division-by-zero and gives fresh posts a small initial boost.
- **Computation**: Calculated at query time in SQL. No background job needed at <100K posts. At scale, add a materialized `trending_score` column updated by a periodic ARQ job (every 5-10 min).
- **No package dependency**: Pure SQL expression — no external ranking library needed.
- **Affected stories**: 5-1 (Social Feed API)
- **Architecture.md updated**: Section 2.8 (Social Service) and Section 8 (Social Feed API contract)

---

## A-8: UserClaims Required Fields (Story 2-2)

- **Date**: 2026-03-16
- **Trigger**: Code review F4 — `UserClaims(TypedDict, total=False)` made `sub` and `exp` optional at the type level, but PyJWT's `options={"require": ["sub", "exp"]}` guarantees they are always present. Callers access `claims["sub"]` without guards.
- **Applies to**: `app/api/middleware/auth.py`

### Change

`sub` and `exp` are now typed as `Required[str]` and `Required[int]` respectively, while remaining fields stay optional (`total=False`):

```python
from typing import Required, TypedDict

class UserClaims(TypedDict, total=False):
    sub: Required[str]   # always present
    exp: Required[int]   # always present
    email: str
    iat: int
    role: str
    aud: str
```

This aligns the static type with the runtime guarantee and removes the need for callers to guard against `KeyError` on `sub`/`exp`.

---

## A-6: DB Transaction Convention (Cross-Cutting)

- **Date**: 2026-03-16
- **Trigger**: Pre-implementation requirement — all multi-step database writes must be atomic. If any step fails, no partial state should be stored.
- **Applies to**: All stories that write to the database.

### Rule

**Always use explicit transactions for any DB operation involving 2+ writes or where partial failure is unacceptable.**

Single-row INSERTs or pure SELECT queries do not require explicit transaction management (auto-commit is fine). All other cases use explicit `BEGIN`/`COMMIT`/`ROLLBACK`.

### Migration Runner

Each migration file runs as a single transaction. The `_schema_migrations` tracking record is inserted in the same transaction as the migration SQL:

```python
conn.autocommit = False
try:
    cur.execute(migration_sql)
    cur.execute(
        "INSERT INTO _schema_migrations (migration_id, applied_at) VALUES (%s, NOW())",
        (migration_id,)
    )
    conn.commit()
except Exception:
    conn.rollback()
    raise
```

### Service Layer

Use `psycopg2` transaction blocks or Supabase RPC for multi-step writes. Examples of operations requiring transactions:

| Operation | Why |
|-----------|-----|
| Register user + grant trial credits | Both rows must exist together |
| Reserve credit + create job | Reservation meaningless without job |
| Commit credit + update job status | Must be atomic — no committed credit without status update |
| Release credit + update job status | Must be atomic |
| Process webhook + update subscription | Idempotency record + state change together |
| Stripe payment confirmed + tier upgrade | Payment recorded AND tier changed, or neither |

### psycopg2 Pattern

```python
conn.autocommit = False
try:
    # all writes
    conn.commit()
except Exception:
    conn.rollback()
    raise
```

Or using context manager:
```python
with conn.cursor() as cur:
    # psycopg2 wraps in transaction automatically when autocommit=False
    cur.execute(...)
    cur.execute(...)
conn.commit()  # or conn.rollback() on except
```

---

## A-5: Usage Tracking, Entitlement Error Protocol & Tier Middleware

- **Date**: 2026-03-16
- **Trigger**: Pre-implementation requirement — API must return structured error codes when tier limits are hit so the client can show the right UI (upgrade dialog, countdown, credits purchase). Usage must be tracked to enable rolling-window limits and `retry_after` responses.
- **Stories**: 1-1 (DB migration), 4-1 (EntitlementService), 3-1 (image pipeline), 4-2 (generation worker), 7-2 (advisor)

---

### 1. Usage Events Table

Append-only log of every consumed action. Source of truth for rolling-window limit checks.

```sql
CREATE TABLE usage_events (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  action     TEXT NOT NULL,           -- 'generation', 'advisor_nudge', 'advisor_message'
  status     TEXT NOT NULL DEFAULT 'committed',  -- 'reserved' | 'committed' | 'released'
  job_id     TEXT,                    -- ARQ job ID — prevents double-counting replayed jobs
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_usage_events_job_id ON usage_events(job_id) WHERE job_id IS NOT NULL;
CREATE INDEX idx_usage_events_user_action_time ON usage_events(user_id, action, created_at DESC);
```

`status` lifecycle (generation only):
- `reserved` → set when ARQ job is enqueued (credit deducted from balance)
- `committed` → set when generation completes successfully
- `released` → set when generation fails (credit restored)

For non-credit tiers (daily/weekly/monthly), events are always `committed` immediately at enqueue time. Counting only includes `committed` events.

---

### 2. EntitlementResult

```python
# services/entitlement.py

from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class EntitlementResult:
    allowed: bool
    error_code: str | None = None         # see error code table below
    limit: int | None = None              # configured limit for this action
    used: int | None = None               # how many used in current window
    retry_after: datetime | None = None   # rolling-window reset (when oldest event expires)
    reset_in_seconds: int | None = None   # convenience — seconds until retry_after
    upgrade_available: bool = False       # hint: show upgrade CTA on client
```

`retry_after` calculation for rolling windows:
```python
# If limit is 1/day and the user generated at 14:00, they can generate again at 14:00 tomorrow.
# retry_after = oldest_event_in_window.created_at + window_duration
```

---

### 3. Error Codes

| Code | HTTP | When | Client action |
|------|------|------|---------------|
| `TIER_LIMIT_DAILY` | 429 | Daily limit hit | Show timer countdown + optional upgrade CTA |
| `TIER_LIMIT_WEEKLY` | 429 | Weekly limit hit | Show timer countdown + optional upgrade CTA |
| `TIER_LIMIT_MONTHLY` | 429 | Monthly limit hit | Show timer countdown + optional upgrade CTA |
| `TIER_LIMIT_TOTAL` | 402 | Lifetime cap hit | Show upgrade dialog (no timer) |
| `TIER_LIMIT_CREDITS` | 402 | No credits remaining | Show "Buy credits" dialog |
| `TIER_FEATURE_LOCKED` | 402 | Feature not on current tier | Show upgrade dialog |
| `TIER_CONCURRENT_LIMIT` | 429 | Too many in-flight jobs | Show "Generation in progress" message, retry |

HTTP semantics: `429` = "you can use this later"; `402` = "you need to upgrade/pay".

#### API error response shape

```json
{
  "error": {
    "code": "TIER_LIMIT_DAILY",
    "message": "Daily generation limit reached",
    "detail": {
      "limit": 1,
      "used": 1,
      "retry_after": "2026-03-17T14:32:00Z",
      "reset_in_seconds": 82800,
      "upgrade_available": true
    }
  }
}
```

`upgrade_available: true` when a higher tier would remove this specific restriction (client shows upgrade CTA). `false` for `TIER_CONCURRENT_LIMIT` (retrying suffices).

---

### 4. FastAPI Entitlement Dependency

Route-level enforcement via `Depends` — no middleware (middleware runs before auth, lacks user context).

```python
# dependencies/entitlement.py

from fastapi import Depends, HTTPException
from services.entitlement import EntitlementService, EntitlementResult
from dependencies.auth import get_current_user

def require_entitlement(action: str):
    """
    Usage:
        @router.post("/generations")
        async def create_generation(
            _: None = Depends(require_entitlement("generation")),
            user: User = Depends(get_current_user),
        ): ...
    """
    async def _check(
        user: User = Depends(get_current_user),
        svc: EntitlementService = Depends(get_entitlement_service),
    ) -> None:
        result: EntitlementResult = await svc.check(user.id, action)
        if not result.allowed:
            status = 402 if result.error_code in {
                "TIER_LIMIT_TOTAL", "TIER_LIMIT_CREDITS", "TIER_FEATURE_LOCKED"
            } else 429
            raise HTTPException(
                status_code=status,
                detail={
                    "error": {
                        "code": result.error_code,
                        "message": _messages[result.error_code],
                        "detail": {
                            "limit": result.limit,
                            "used": result.used,
                            "retry_after": result.retry_after.isoformat() if result.retry_after else None,
                            "reset_in_seconds": result.reset_in_seconds,
                            "upgrade_available": result.upgrade_available,
                        },
                    }
                },
            )
    return _check

def require_feature(feature: str):
    """
    Usage:
        @router.post("/advisor/messages")
        async def send_message(
            _: None = Depends(require_feature("advisor_chat")),
            ...
        ): ...
    """
    async def _check(
        user: User = Depends(get_current_user),
        svc: EntitlementService = Depends(get_entitlement_service),
    ) -> None:
        if not await svc.has_feature(user.id, feature):
            raise HTTPException(
                status_code=402,
                detail={"error": {"code": "TIER_FEATURE_LOCKED", "detail": {"upgrade_available": True}}},
            )
    return _check
```

Routes that use these dependencies:

| Route | Dependency |
|-------|-----------|
| `POST /generations` | `require_entitlement("generation")` |
| `POST /advisor/messages` | `require_feature("advisor_chat")` |
| `GET /advisor/nudges` | *(no gate — all tiers can read nudges)* |
| `POST /visual-comparison` | `require_feature("visual_comparison")` |

---

## A-7: Story 1-1 Code Review Deferred Fixes

- **Date**: 2026-03-16
- **Trigger**: Code review of Story 1-1 found three medium-severity issues deferred to future migrations.

### A-7a: must_have Grep Exclusion List Update

The Story 1-1 must_have verification requires: "grep for `0.80` or `0.800` outside `app/config.py` and `app/migrations/` returns zero matches." This guard is not satisfied because `app/config/tiers.py` legitimately contains per-tier identity_similarity_threshold values (`0.800`, `0.750`, `0.700`) as part of the tier seed data. Future stories that re-run this grep must also exclude `app/config/tiers.py`.

### A-7b: CHECK Constraints on tiers Limit-Type Columns

`tiers.generation_type` and `tiers.advisor_nudges_type` currently accept any TEXT value. A future migration should add:

```sql
ALTER TABLE tiers ADD CONSTRAINT chk_tiers_generation_type
  CHECK (generation_type IN ('total','daily','weekly','monthly','period','credits','unlimited'));
ALTER TABLE tiers ADD CONSTRAINT chk_tiers_advisor_nudges_type
  CHECK (advisor_nudges_type IN ('total','daily','weekly','monthly','period','credits','unlimited'));
```

### A-7c: CHECK Constraints on usage_events action and status Columns

`usage_events.action` and `usage_events.status` currently accept any TEXT value. A future migration should add constraints once the full set of valid values is confirmed during the generation and advisor services stories. Defer until domain values are finalized.

---

### 5. Concurrent Generation Guard (Redis)

Prevents a user from enqueueing more parallel jobs than `tier.max_concurrent_generations`.

```python
# In EntitlementService.check("generation"):
concurrent_key = f"concurrent:{user_id}"
current = int(await redis.get(concurrent_key) or 0)
if current >= tier.max_concurrent_generations:
    return EntitlementResult(allowed=False, error_code="TIER_CONCURRENT_LIMIT",
                              upgrade_available=False)

# In ARQ worker — job start:
await redis.incr(concurrent_key)
await redis.expire(concurrent_key, settings.GENERATION_TIMEOUT_SECONDS + 30)  # safety TTL

# In ARQ worker — job end (success or failure):
await redis.decr(concurrent_key)
```

The TTL prevents permanently stuck counters if the worker crashes mid-job.

---

### 6. EntitlementService.check() — Full Dispatch

```python
async def check(self, user_id: UUID, action: str) -> EntitlementResult:
    tier = await self._get_tier(user_id)

    if action == "generation":
        # 1. Concurrent guard (Redis)
        concurrent_key = f"concurrent:{user_id}"
        if int(await self._redis.get(concurrent_key) or 0) >= tier.max_concurrent_generations:
            return EntitlementResult(allowed=False, error_code="TIER_CONCURRENT_LIMIT")

        # 2. Credits check
        if tier.credits_based:
            if not await self._has_credits(user_id):
                return EntitlementResult(allowed=False, error_code="TIER_LIMIT_CREDITS",
                                          upgrade_available=True)
            return EntitlementResult(allowed=True)

        # 3. Time-window / total check
        return await self._check_window(
            user_id, action="generation",
            limit_type=LimitType(tier.generation_type),
            limit=tier.generation_limit,
            period_seconds=tier.generation_period_seconds,
        )

    if action == "advisor_nudge":
        return await self._check_window(
            user_id, action="advisor_nudge",
            limit_type=LimitType(tier.advisor_nudges_type),
            limit=tier.advisor_nudges_limit,
            period_seconds=tier.advisor_nudges_period_seconds,
        )

    raise ValueError(f"Unknown entitlement action: {action}")


async def _check_window(
    self, user_id, action, limit_type, limit, period_seconds=None
) -> EntitlementResult:
    match limit_type:
        case LimitType.UNLIMITED:
            return EntitlementResult(allowed=True)
        case LimitType.DAILY:   window = timedelta(days=1);    code = "TIER_LIMIT_DAILY"
        case LimitType.WEEKLY:  window = timedelta(weeks=1);   code = "TIER_LIMIT_WEEKLY"
        case LimitType.MONTHLY: window = timedelta(days=30);   code = "TIER_LIMIT_MONTHLY"
        case LimitType.PERIOD:  window = timedelta(seconds=period_seconds); code = "TIER_LIMIT_DAILY"
        case LimitType.TOTAL:   window = None;                 code = "TIER_LIMIT_TOTAL"

    since = (now() - window) if window else None
    events = await self._usage_repo.get_events(user_id, action, since=since, status="committed")
    count = len(events)

    if count < limit:
        return EntitlementResult(allowed=True, limit=limit, used=count)

    retry_after = (min(e.created_at for e in events) + window) if window else None
    reset_in = int((retry_after - now()).total_seconds()) if retry_after else None
    return EntitlementResult(
        allowed=False,
        error_code=code,
        limit=limit, used=count,
        retry_after=retry_after,
        reset_in_seconds=reset_in,
        upgrade_available=True,
    )
```

---

### 7. Story Scope Extensions

| Story | Addition |
|-------|---------|
| 1-1 | `usage_events` table + indexes in DB migration |
| 4-1 | `UsageRepository`, `EntitlementService.check()`, `EntitlementResult`, dependencies/entitlement.py |
| 3-1 | `Depends(require_entitlement("generation"))` on POST /generations |
| 4-2 | ARQ worker: Redis INCR on job start, DECR on job end; commit/release usage_events status |
| 7-2 | `Depends(require_feature("advisor_chat"))` on POST /advisor/messages; `check("advisor_nudge")` before nudge dispatch |

---

## A-4: DB-Driven Tier System (supersedes A-2)

- **Date**: 2026-03-16
- **Trigger**: Pre-implementation requirement — no tier names in code or env vars; tiers are DB rows identified by UUID; switching the default tier for new users is a DB operation, not a code change
- **Stories**: 1-1 (DB migration), 4-1 (EntitlementService), 2-1 (registration), 4-4 (Stripe webhook)

### What A-2 said

`TierConfig` Pydantic settings model loaded from `TIER__*` env vars at startup. Tier identity (`trial`, `credit_holder`, `premium`) used as strings throughout service code.

### What is actually being built

Tiers are rows in a `tiers` table seeded by migration. All limit fields are columns on the row. Application code reads `user.tier_id: UUID` → fetches `TierRecord` from DB (Redis-cached). No tier name or enum ever appears in business logic.

---

### DB Schema

```sql
CREATE TABLE tiers (
  id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Admin/seeding reference — slug is NEVER used in application logic or conditionals.
  -- It exists solely so migrations and admin scripts can reference rows by name.
  slug                            TEXT NOT NULL UNIQUE,

  display_name                    TEXT NOT NULL,   -- shown to users in the app
  is_default                      BOOLEAN NOT NULL DEFAULT false,
  is_active                       BOOLEAN NOT NULL DEFAULT true,

  -- Generation limits
  generation_type                 TEXT NOT NULL,   -- total|daily|weekly|monthly|period|credits|unlimited
  generation_limit                INT,             -- null for credits/unlimited
  generation_period_seconds       INT,             -- PERIOD type only

  -- Advisor nudge limits (window is always explicit — no ambiguity)
  advisor_nudges_type             TEXT NOT NULL,
  advisor_nudges_limit            INT,
  advisor_nudges_period_seconds   INT,

  -- Thresholds (per-tier)
  max_concurrent_generations      INT         NOT NULL DEFAULT 1,
  identity_similarity_threshold   DECIMAL(4,3) NOT NULL DEFAULT 0.800,

  -- Feature flags
  feature_advisor_chat            BOOLEAN NOT NULL DEFAULT false,
  feature_visual_comparison       BOOLEAN NOT NULL DEFAULT false,

  -- Payment
  stripe_price_id                 TEXT,     -- null = free tier
  credits_based                   BOOLEAN NOT NULL DEFAULT false,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- At most one default tier; default requires active
CREATE UNIQUE INDEX idx_tiers_one_default ON tiers(is_default) WHERE is_default = true;
ALTER TABLE tiers ADD CONSTRAINT chk_default_requires_active
  CHECK (NOT is_default OR is_active);
```

`is_active` semantics:
- `true` → tier works for existing users AND can be assigned to new users
- `false` → existing users keep full access; new users cannot be assigned to it

---

### Seed Data (`config/tiers.py` — used by migration only, not at runtime)

```python
# config/tiers.py
# SEED DEFINITIONS ONLY — not imported at runtime.
# The migration reads this module and inserts rows into the `tiers` table.
# At runtime, all tier reads go through tier_repo.get(user.tier_id).

from dataclasses import dataclass
from services.limits import LimitType  # shared enum, see below

@dataclass(frozen=True)
class TierSeed:
    slug: str
    display_name: str
    is_default: bool
    generation_type: LimitType
    generation_limit: int | None
    generation_period_seconds: int | None
    advisor_nudges_type: LimitType
    advisor_nudges_limit: int | None
    max_concurrent_generations: int
    identity_similarity_threshold: float
    feature_advisor_chat: bool
    feature_visual_comparison: bool
    stripe_price_id: str | None
    credits_based: bool

SEED_TIERS: list[TierSeed] = [
    TierSeed(
        slug="free",
        display_name="Free",
        is_default=True,
        generation_type=LimitType.DAILY,
        generation_limit=1,
        generation_period_seconds=None,
        advisor_nudges_type=LimitType.WEEKLY,
        advisor_nudges_limit=3,
        max_concurrent_generations=1,
        identity_similarity_threshold=0.80,
        feature_advisor_chat=False,
        feature_visual_comparison=False,
        stripe_price_id=None,
        credits_based=False,
    ),
    TierSeed(
        slug="credits",
        display_name="Credits",
        is_default=False,
        generation_type=LimitType.CREDITS,
        generation_limit=None,
        generation_period_seconds=None,
        advisor_nudges_type=LimitType.WEEKLY,
        advisor_nudges_limit=10,
        max_concurrent_generations=2,
        identity_similarity_threshold=0.75,
        feature_advisor_chat=False,
        feature_visual_comparison=False,
        stripe_price_id=None,       # set per-environment via admin script
        credits_based=True,
    ),
    TierSeed(
        slug="premium",
        display_name="Premium",
        is_default=False,
        generation_type=LimitType.MONTHLY,
        generation_limit=100,
        generation_period_seconds=None,
        advisor_nudges_type=LimitType.UNLIMITED,
        advisor_nudges_limit=None,
        max_concurrent_generations=3,
        identity_similarity_threshold=0.70,
        feature_advisor_chat=True,
        feature_visual_comparison=True,
        stripe_price_id="price_CHANGE_ME",
        credits_based=False,
    ),
]
```

`LimitType` enum lives in `services/limits.py` — shared by the seed file and `EntitlementService`. Same 7 values as A-2.

---

### Runtime: EntitlementService

```python
# services/entitlement.py
# TierRecord = dataclass mirroring the tiers table row (populated by tier_repo)

class EntitlementService:
    async def _get_tier(self, user_id: UUID) -> TierRecord:
        """Fetch tier for user, Redis-cached (TTL 5 min)."""
        user = await self._user_repo.get(user_id)
        return await self._tier_repo.get(user.tier_id)   # cache key: tier:{tier_id}

    async def can_generate(self, user_id: UUID) -> bool:
        tier = await self._get_tier(user_id)
        match LimitType(tier.generation_type):
            case LimitType.UNLIMITED:
                return True
            case LimitType.CREDITS:
                return await self._has_credits(user_id)
            case LimitType.DAILY:
                since = now() - timedelta(days=1)
            case LimitType.WEEKLY:
                since = now() - timedelta(weeks=1)
            case LimitType.MONTHLY:
                since = now() - timedelta(days=30)
            case LimitType.PERIOD:
                since = now() - timedelta(seconds=tier.generation_period_seconds)
            case LimitType.TOTAL:
                return await self._count_all(user_id) < tier.generation_limit
        return await self._count_since(user_id, since) < tier.generation_limit

    async def can_send_nudge(self, user_id: UUID) -> bool:
        tier = await self._get_tier(user_id)
        # same dispatch pattern on advisor_nudges_type / advisor_nudges_limit

    async def has_feature(self, user_id: UUID, feature: str) -> bool:
        tier = await self._get_tier(user_id)
        return getattr(tier, f"feature_{feature}", False)

    async def max_concurrent(self, user_id: UUID) -> int:
        return (await self._get_tier(user_id)).max_concurrent_generations

    async def similarity_threshold(self, user_id: UUID) -> float:
        return (await self._get_tier(user_id)).identity_similarity_threshold
```

No tier name, no enum comparison, no `if tier == "premium"` anywhere. Behaviour is driven entirely by the DB row.

---

### Registration (AuthService)

```python
async def register(self, ...) -> User:
    default_tier = await self._tier_repo.get_default()
    # raises TierConfigurationError if no active default tier exists
    # startup health-check verifies this at boot time
    user = await self._user_repo.create(..., tier_id=default_tier.id)
    return user
```

---

### Switching default tier (no code change)

```sql
-- Enable trial mode for new users
BEGIN;
UPDATE tiers SET is_default = false WHERE is_default = true;
UPDATE tiers SET is_active = true, is_default = true WHERE slug = 'trial';
COMMIT;

-- Revert to free tier
BEGIN;
UPDATE tiers SET is_default = false WHERE is_default = true;
UPDATE tiers SET is_default = true WHERE slug = 'free';
COMMIT;
```

Or insert an entirely new tier row and flip `is_default` — no deployment needed.

---

### Admin Tier Management API

Tiers can be created, modified, and deactivated at runtime via authenticated admin endpoints — no SQL, no code changes, no redeployment.

#### Endpoints

```
GET    /admin/tiers              # List all tiers (including inactive)
POST   /admin/tiers              # Create a new tier
GET    /admin/tiers/{id}         # Get single tier
PATCH  /admin/tiers/{id}         # Update any tier field
POST   /admin/tiers/{id}/default # Make this the default tier for new users
DELETE /admin/tiers/{id}         # Deactivate tier (sets is_active=false; existing users keep access)
```

#### Auth

Protected by `X-Admin-Key` header (value from `ADMIN_API_KEY` env var). Never user-facing JWT auth — admin key stays server-side. In production: store in AWS Secrets Manager.

#### Request/Response examples

```jsonc
// POST /admin/tiers — create a promo tier
{
  "slug": "promo_influencer",
  "display_name": "Creator Pro",
  "generation_type": "monthly",
  "generation_limit": 50,
  "advisor_nudges_type": "unlimited",
  "advisor_nudges_limit": null,
  "max_concurrent_generations": 2,
  "identity_similarity_threshold": 0.75,
  "feature_advisor_chat": true,
  "feature_visual_comparison": false,
  "stripe_price_id": null,
  "credits_based": false
}
// → 201 { "id": "uuid", "slug": "promo_influencer", "is_default": false, "is_active": true, ... }

// PATCH /admin/tiers/{id} — bump free tier generation limit to 2/day
{ "generation_limit": 2 }
// → 200 { ...updated tier record... }

// POST /admin/tiers/{id}/default — switch default tier for new users
// → 200 { "previous_default": "uuid-of-old", "new_default": "uuid-of-new" }
// Runs the two-UPDATE transaction atomically

// DELETE /admin/tiers/{id} — deactivate (existing users unaffected)
// → 204 No Content
// If tier is_default → 409: "Cannot deactivate the default tier. Set a different default first."
```

#### Cache invalidation

When any tier row is modified via admin API, `tier_repo` must evict the affected cache key (`tier:{tier_id}`) from Redis and also bust `tier:default` key. All active user sessions see the change within one cache TTL cycle (max 5 min for non-default field changes; immediate for default-switch).

#### New env var

```bash
ADMIN_API_KEY=CHANGE_ME    # Required; 32+ char random string; rotate periodically
```

---

### Story 4-1 Scope (replaces A-2 scope)

1. `services/limits.py` — `LimitType` StrEnum (7 values)
2. `config/tiers.py` — `TierSeed` dataclass + `SEED_TIERS` list (seed only)
3. DB migration (Story 1-1) — `CREATE TABLE tiers` + seed insert from `SEED_TIERS`
4. `repositories/tier_repo.py` — `get(id)`, `get_default()`, Redis cache TTL 5 min, cache invalidation on write
5. `services/entitlement.py` — `EntitlementService` with DB-driven dispatch (all 7 `LimitType` branches)
6. Auth service `register()` calls `tier_repo.get_default()` — no tier name
7. Startup health check asserts `SELECT COUNT(*) FROM tiers WHERE is_default AND is_active = 1`
8. `routers/admin/tiers.py` — admin CRUD endpoints (6 routes, `X-Admin-Key` auth)
9. `ADMIN_API_KEY` env var wired into app config

### Supersedes

Amendment A-2 is **fully superseded** by A-4:
- All `TIER__*` env vars removed
- `TierConfig` pydantic-settings class removed
- `FREE_TRIAL_ANALYSES`, `MAX_CONCURRENT_GENERATIONS_PER_USER`, `IDENTITY_SIMILARITY_THRESHOLD` constants removed (were already superseded by A-2 field additions)
- `trial` tier concept removed — any future trial is a DB row, not a code concept

---

## A-3: Adapter Pattern & Modular Pipeline Architecture

- **Date**: 2026-03-16
- **Trigger**: Pre-implementation requirement — all services, pipeline steps, and prompts must be independently replaceable without touching core business logic
- **Stories**: 3-1, 3-2, 4-2, 7-2, 7-3

### What architecture.md says

`ImagePipelineService`, `FaceAnalysisService`, and `AdvisorService` are described as single cohesive classes calling external providers (Rekognition, MediaPipe, fal.ai, Claude) directly inline.

### What is actually being built

Every external dependency is behind a typed adapter interface. The image processing pipeline is a list of composable steps. LLM prompts live in `prompts/` files loaded at runtime. Swapping a provider = swap one env var and one adapter file — zero core logic changes.

---

### 1. Pipeline Step Protocol

```python
# services/pipeline/base.py

from typing import Protocol
from dataclasses import dataclass, field

@dataclass
class PipelineContext:
    user_id: str
    image_bytes: bytes
    image_path: str = ""          # set after storage step
    metadata: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    should_abort: bool = False    # set by any step to stop the chain

class PipelineStep(Protocol):
    """A single composable step in a pipeline."""
    async def process(self, ctx: PipelineContext) -> PipelineContext: ...
    async def rollback(self, ctx: PipelineContext) -> None: ...
    # rollback called in reverse order if a later step fails

class ImagePipeline:
    """Runs a list of steps in order; rolls back on failure."""
    def __init__(self, steps: list[PipelineStep]) -> None:
        self._steps = steps

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        completed: list[PipelineStep] = []
        try:
            for step in self._steps:
                if ctx.should_abort:
                    break
                ctx = await step.process(ctx)
                completed.append(step)
        except Exception:
            for step in reversed(completed):
                await step.rollback(ctx)
            raise
        return ctx
```

Pipeline composition in `config/pipelines.py`:

```python
# config/pipelines.py
from services.pipeline.steps.nsfw import NSFWScreeningStep
from services.pipeline.steps.exif import ExifStripStep
from services.pipeline.steps.storage import StorageStep
from services.pipeline.steps.face_analysis import FaceAnalysisStep
from services.pipeline.steps.generation import ImageGenerationStep
from services.pipeline.steps.similarity import SimilarityCheckStep

# Compose by listing step classes — add/remove steps here only
UPLOAD_PIPELINE_STEPS: list[type] = [
    NSFWScreeningStep,   # remove to disable NSFW screening
    ExifStripStep,       # remove to skip EXIF strip
    StorageStep,
]

ANALYSIS_PIPELINE_STEPS: list[type] = [
    NSFWScreeningStep,
    ExifStripStep,
    FaceAnalysisStep,
    StorageStep,
]

GENERATION_PIPELINE_STEPS: list[type] = [
    SimilarityCheckStep,   # blocks if identity score too low
    ImageGenerationStep,
    StorageStep,
]
```

---

### 2. Adapter Interfaces

One Protocol per provider category. Concrete implementations in `adapters/{provider}/`.

```python
# adapters/base/nsfw.py
from typing import Protocol
from dataclasses import dataclass

@dataclass
class NSFWResult:
    is_explicit: bool
    confidence: float
    labels: list[str]

class NSFWAdapter(Protocol):
    async def screen(self, image: bytes) -> NSFWResult: ...

# adapters/base/face_analysis.py
@dataclass
class FaceFeatures:
    face_shape: str
    symmetry_score: float
    key_features: dict[str, str]
    scores: dict[str, float]
    recommendations: list[str]

class FaceAnalysisAdapter(Protocol):
    async def analyze(self, image: bytes) -> FaceFeatures: ...

# adapters/base/image_generation.py
@dataclass
class GenerationResult:
    image_bytes: bytes
    similarity_score: float   # 0–1, identity preservation
    cost_usd: float

class ImageGenerationAdapter(Protocol):
    async def generate(
        self,
        source_image: bytes,
        prompt: str,
        reference_features: FaceFeatures,
    ) -> GenerationResult: ...

# adapters/base/llm.py
@dataclass
class LLMMessage:
    role: str   # "user" | "assistant" | "system"
    content: str | list[dict]   # str or vision content blocks

class LLMAdapter(Protocol):
    async def complete(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        max_tokens: int = 1024,
    ) -> str: ...

# adapters/base/storage.py
class StorageAdapter(Protocol):
    async def upload(self, path: str, data: bytes, content_type: str) -> str: ...
    async def signed_url(self, path: str, expires_in: int = 3600) -> str: ...

# adapters/base/payment.py
class PaymentAdapter(Protocol):
    async def create_checkout(self, user_id: str, product_id: str) -> str: ...   # returns URL
    async def get_subscription(self, customer_id: str) -> dict | None: ...
```

#### Concrete Implementations

| Interface | Default | Alternative |
|-----------|---------|-------------|
| `NSFWAdapter` | `adapters/rekognition/nsfw.py` | `adapters/sightengine/nsfw.py`, `adapters/mock/nsfw.py` |
| `FaceAnalysisAdapter` | `adapters/mediapipe/face_analysis.py` | `adapters/mock/face_analysis.py` |
| `ImageGenerationAdapter` | `adapters/fal_ai/image_generation.py` | `adapters/replicate/image_generation.py`, `adapters/mock/image_generation.py` |
| `LLMAdapter` | `adapters/anthropic/llm.py` | `adapters/openai/llm.py`, `adapters/mock/llm.py` |
| `StorageAdapter` | `adapters/supabase/storage.py` | `adapters/s3/storage.py`, `adapters/local/storage.py` |
| `PaymentAdapter` | `adapters/stripe/payment.py` | `adapters/mock/payment.py` |

#### Adapter Selection via Env Vars

```python
# config/adapters.py
import importlib
from functools import lru_cache
from pydantic_settings import BaseSettings

class AdapterConfig(BaseSettings):
    nsfw_adapter: str = "rekognition"
    face_analysis_adapter: str = "mediapipe"
    image_generation_adapter: str = "fal_ai"
    llm_adapter: str = "anthropic"
    storage_adapter: str = "supabase"
    payment_adapter: str = "stripe"

    model_config = SettingsConfigDict(env_prefix="ADAPTER__")

@lru_cache(maxsize=None)
def get_adapter_config() -> AdapterConfig:
    return AdapterConfig()

def _load(category: str, adapter_name: str):
    module = importlib.import_module(f"adapters.{adapter_name}.{category}")
    cls_name = "".join(p.title() for p in adapter_name.split("_")) + category.title().replace("_", "")
    return getattr(module, cls_name)()

def get_nsfw_adapter() -> "NSFWAdapter":
    return _load("nsfw", get_adapter_config().nsfw_adapter)

def get_face_analysis_adapter() -> "FaceAnalysisAdapter":
    return _load("face_analysis", get_adapter_config().face_analysis_adapter)

def get_image_generation_adapter() -> "ImageGenerationAdapter":
    return _load("image_generation", get_adapter_config().image_generation_adapter)

def get_llm_adapter() -> "LLMAdapter":
    return _load("llm", get_adapter_config().llm_adapter)

def get_storage_adapter() -> "StorageAdapter":
    return _load("storage", get_adapter_config().storage_adapter)

def get_payment_adapter() -> "PaymentAdapter":
    return _load("payment", get_adapter_config().payment_adapter)
```

New env vars:
```bash
ADAPTER__NSFW_ADAPTER=rekognition          # or: sightengine, mock
ADAPTER__FACE_ANALYSIS_ADAPTER=mediapipe   # or: mock
ADAPTER__IMAGE_GENERATION_ADAPTER=fal_ai  # or: replicate, mock
ADAPTER__LLM_ADAPTER=anthropic             # or: openai, mock
ADAPTER__STORAGE_ADAPTER=supabase          # or: s3, local
ADAPTER__PAYMENT_ADAPTER=stripe            # or: mock
```

---

### 3. Prompts in Separate Files

All LLM prompts live in `prompts/` directory. Loaded at import time, cached in memory.

```python
# services/prompts.py
from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    """Load a prompt template by relative path, e.g. 'advisor/system'."""
    path = PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8")
```

Directory layout:
```
prompts/
  advisor/
    system.txt              # Advisor persona: name, scope, tone, constraints
    nudge_weekly.txt        # Weekly check-in nudge template
    nudge_analysis.txt      # Post-analysis nudge (variables: {face_shape}, {top_recommendation})
    nudge_milestone.txt     # Milestone event nudge
    visual_comparison.txt   # System prompt for vision comparison queries
  generation/
    face_analysis.txt       # Prompt for face feature classification from MediaPipe landmarks
    identity_check.txt      # Prompt for identity similarity scoring
    enhancement_style.txt   # User-facing style prompt injected into fal.ai generation
  system/
    content_moderation.txt  # Reasoning prompt for borderline NSFW decisions
```

Usage in services:
```python
from services.prompts import load_prompt

# In AdvisorService._build_system_prompt():
base_system = load_prompt("advisor/system").format(
    persona_name=settings.ADVISOR_PERSONA_NAME,
    user_name=user.display_name,
)

# In AdvisorService._nudge_payload():
nudge_text = load_prompt("advisor/nudge_analysis").format(
    face_shape=snapshot["face_shape"],
    top_recommendation=snapshot["recommendations"][0],
)
```

---

### 4. Directory Structure (additions to architecture.md)

```
app/
  adapters/
    base/               # Protocol interfaces (NSFWAdapter, FaceAnalysisAdapter, etc.)
    rekognition/        # AWS Rekognition: nsfw.py
    mediapipe/          # MediaPipe: face_analysis.py
    fal_ai/             # fal.ai: image_generation.py
    anthropic/          # Anthropic: llm.py
    supabase/           # Supabase Storage: storage.py
    stripe/             # Stripe: payment.py
    mock/               # All mock adapters (testing + local dev without API keys)
  services/
    pipeline/
      base.py           # PipelineStep protocol, ImagePipeline runner, PipelineContext
      steps/
        nsfw.py         # NSFWScreeningStep
        exif.py         # ExifStripStep
        storage.py      # StorageStep
        face_analysis.py # FaceAnalysisStep
        generation.py   # ImageGenerationStep
        similarity.py   # SimilarityCheckStep
  config/
    adapters.py         # AdapterConfig (pydantic-settings), get_*_adapter() factories
    pipelines.py        # Pipeline step list composition
    tiers.py            # TierConfig (from A-2)
  prompts/
    advisor/            # Advisor LLM prompt templates
    generation/         # Image generation prompt templates
    system/             # System-level prompt templates
```

---

### Story Scope Extensions

| Story | Change |
|-------|--------|
| 3-1 Image Pipeline | Implement as `ImagePipeline` + pluggable step classes; NSFW via `NSFWAdapter`; storage via `StorageAdapter` |
| 3-2 Face Analysis | `FaceAnalysisStep` delegates to `FaceAnalysisAdapter`; writes snapshot to `user_memories` |
| 4-2 Generation Worker | ARQ job instantiates `ImagePipeline(GENERATION_PIPELINE_STEPS)`; generation via `ImageGenerationAdapter` |
| 7-2 Advisor API | `AdvisorService` uses `LLMAdapter`; all prompts via `load_prompt()`; no inline prompt strings |
| 7-3 Nudge Scheduler | Nudge text generated by calling `LLMAdapter` with `load_prompt("advisor/nudge_*")` |
| All stories | `StorageAdapter` used instead of Supabase client directly; `PaymentAdapter` for all Stripe calls |

### No Superseded Values

This amendment adds structure — it does not replace values from A-1 or A-2. TierConfig (A-2) and AdvisorService (A-1) both plug into this adapter/pipeline pattern.

---

## A-2: Config-Driven Tier Limit System

- **Date**: 2026-03-15
- **Trigger**: Pre-implementation requirement — tier thresholds must be fully configurable without code changes
- **Stories**: 4-1

### What architecture.md says

`EntitlementService` manages a credit ledger and state machine. Tier limits are partially specified as constants (e.g., `ADVISOR_NUDGE_WEEKLY_LIMIT=3`, `trial_credits=3`). Limits are embedded in service logic.

### What is actually being built

A `TierConfig` Pydantic settings model loaded from environment variables at startup. `EntitlementService` reads all limits from `TierConfig` — zero hardcoded thresholds.

### TierConfig Design

```python
# config/tiers.py

from enum import StrEnum
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

class LimitType(StrEnum):
    TOTAL     = "total"      # Lifetime cap (all-time count)
    DAILY     = "daily"      # 24h rolling window
    WEEKLY    = "weekly"     # 7d rolling window
    MONTHLY   = "monthly"    # 30d rolling window
    PERIOD    = "period"     # Custom window — period_seconds required
    CREDITS   = "credits"    # Consumed from credit ledger; no extra limit
    UNLIMITED = "unlimited"  # No cap

class LimitConfig(BaseModel):
    type: LimitType
    limit: int | None = None           # Ignored for CREDITS and UNLIMITED
    period_seconds: int | None = None  # Required for PERIOD type only

class FeatureFlags(BaseModel):
    advisor_chat: bool = False
    visual_comparison: bool = False

class TierLimits(BaseModel):
    generation: LimitConfig
    advisor_nudges: LimitConfig
    features: FeatureFlags
    max_concurrent_generations: int = 1          # parallel in-flight jobs per user
    identity_similarity_threshold: float = 0.80  # minimum score to pass SimilarityCheckStep

class TierConfig(BaseSettings):
    trial: TierLimits = TierLimits(
        generation=LimitConfig(type=LimitType.TOTAL, limit=3),
        advisor_nudges=LimitConfig(type=LimitType.WEEKLY, limit=3),
        features=FeatureFlags(),
        max_concurrent_generations=1,
        identity_similarity_threshold=0.80,
    )
    credit_holder: TierLimits = TierLimits(
        generation=LimitConfig(type=LimitType.CREDITS),
        advisor_nudges=LimitConfig(type=LimitType.WEEKLY, limit=3),
        features=FeatureFlags(),
        max_concurrent_generations=2,
        identity_similarity_threshold=0.75,
    )
    premium: TierLimits = TierLimits(
        generation=LimitConfig(type=LimitType.MONTHLY, limit=100),
        advisor_nudges=LimitConfig(type=LimitType.UNLIMITED),
        features=FeatureFlags(advisor_chat=True, visual_comparison=True),
        max_concurrent_generations=3,
        identity_similarity_threshold=0.70,
    )

    model_config = SettingsConfigDict(
        env_prefix="TIER__",
        env_nested_delimiter="__",
    )
```

### How Each Limit Type Works

| Type | Mechanism |
|------|-----------|
| `total` | COUNT `entitlement_events` WHERE user_id = ? AND type = 'generation_consumed' |
| `daily` / `weekly` / `monthly` | COUNT same WHERE created_at ≥ now() − interval |
| `period` | COUNT same WHERE created_at ≥ now() − `period_seconds` seconds |
| `credits` | check `credit_balance > 0` only (existing ledger behavior) |
| `unlimited` | no check — always allowed |

`EntitlementService.can_generate(user_id, tier)` dispatches to the correct check based on `TierConfig.{tier}.generation.type`.

### New Environment Variables

```bash
# Tier Config — loaded via pydantic-settings nested env vars (__ delimiter)

# --- TRIAL ---
TIER__TRIAL__GENERATION__TYPE=total
TIER__TRIAL__GENERATION__LIMIT=3
TIER__TRIAL__ADVISOR_NUDGES__TYPE=weekly
TIER__TRIAL__ADVISOR_NUDGES__LIMIT=3
TIER__TRIAL__MAX_CONCURRENT_GENERATIONS=1
TIER__TRIAL__IDENTITY_SIMILARITY_THRESHOLD=0.80
TIER__TRIAL__FEATURES__ADVISOR_CHAT=false
TIER__TRIAL__FEATURES__VISUAL_COMPARISON=false

# --- CREDIT HOLDER ---
TIER__CREDIT_HOLDER__GENERATION__TYPE=credits
TIER__CREDIT_HOLDER__ADVISOR_NUDGES__TYPE=weekly
TIER__CREDIT_HOLDER__ADVISOR_NUDGES__LIMIT=3
TIER__CREDIT_HOLDER__MAX_CONCURRENT_GENERATIONS=2
TIER__CREDIT_HOLDER__IDENTITY_SIMILARITY_THRESHOLD=0.75
TIER__CREDIT_HOLDER__FEATURES__ADVISOR_CHAT=false
TIER__CREDIT_HOLDER__FEATURES__VISUAL_COMPARISON=false

# --- PREMIUM ---
TIER__PREMIUM__GENERATION__TYPE=monthly
TIER__PREMIUM__GENERATION__LIMIT=100
TIER__PREMIUM__ADVISOR_NUDGES__TYPE=unlimited
TIER__PREMIUM__MAX_CONCURRENT_GENERATIONS=3
TIER__PREMIUM__IDENTITY_SIMILARITY_THRESHOLD=0.70
TIER__PREMIUM__FEATURES__ADVISOR_CHAT=true
TIER__PREMIUM__FEATURES__VISUAL_COMPARISON=true
```

### Config Recipes (change without code)

```bash
# Free tier: 1 generation per day
TIER__TRIAL__GENERATION__TYPE=daily
TIER__TRIAL__GENERATION__LIMIT=1

# Free tier: 50 total lifetime generations
TIER__TRIAL__GENERATION__TYPE=total
TIER__TRIAL__GENERATION__LIMIT=50

# Free tier: 1 generation per 86400 seconds (custom period)
TIER__TRIAL__GENERATION__TYPE=period
TIER__TRIAL__GENERATION__LIMIT=1
TIER__TRIAL__GENERATION__PERIOD_SECONDS=86400

# Premium: unlimited generations
TIER__PREMIUM__GENERATION__TYPE=unlimited
```

### Story 4-1 Scope Extension

Story 4-1 (Entitlement Service) must now:
1. Add `config/tiers.py` with `TierConfig` model (pydantic-settings v2)
2. `EntitlementService.__init__` accepts `TierConfig` dependency
3. `EntitlementService.can_generate(user_id, tier)` dispatches on `LimitType`
4. Add sliding-window query helper: `_count_events_in_window(user_id, type, since)` on `entitlement_events`
5. `EntitlementService.can_send_nudge(user_id, tier)` reads `TierConfig.{tier}.advisor_nudges`
6. `EntitlementService.has_feature(user_id, tier, feature)` reads `TierConfig.{tier}.features`
7. `EntitlementService.max_concurrent(tier)` returns `TierConfig.{tier}.max_concurrent_generations`
8. `EntitlementService.similarity_threshold(tier)` returns `TierConfig.{tier}.identity_similarity_threshold`
9. Unit tests cover all 6 `LimitType` branches

### Superseded Values

The following env vars from A-1 and architecture.md are **superseded**:
- `ADVISOR_NUDGE_WEEKLY_LIMIT=3` → `TIER__TRIAL__ADVISOR_NUDGES__LIMIT=3` (same default)
- Hardcoded `trial_credits=3` in EntitlementService → `TIER__TRIAL__GENERATION__LIMIT=3`
- `FREE_TRIAL_ANALYSES` constant → `TIER__TRIAL__GENERATION__LIMIT` (do not read from `FREE_TRIAL_ANALYSES`)
- `MAX_CONCURRENT_GENERATIONS_PER_USER` constant → `TIER__{tier}__MAX_CONCURRENT_GENERATIONS` (per-tier)
- `IDENTITY_SIMILARITY_THRESHOLD` constant → `TIER__{tier}__IDENTITY_SIMILARITY_THRESHOLD` (per-tier)

---

## A-1: Personal Advisor — AI Memory & Coaching System

- **Date**: 2026-03-15
- **Trigger**: Pre-implementation scope addition (discovered during DevOps Pass 1)
- **Stories**: 7-1, 7-2, 7-3, 7-4

### What architecture.md says
No personal advisor component. No persistent user memory. No LLM integration beyond fal.ai image generation.

### What is actually being built
A named AI advisor persona with persistent per-user memory, bidirectional chat (paid), and proactive nudges (all tiers). Scope: appearance + broader self-improvement (fitness, style, grooming, confidence).

### New Component: AdvisorService

**Responsibilities:**
- Manage advisor conversations (create session, append messages, summarise old sessions)
- Read/write user memories (goals, accepted/dismissed suggestions, user notes, analysis insights)
- Build per-turn context: inject top-K semantically relevant memories via pgvector + recent conversation history
- Enforce tier limits: free = advisor-initiated nudges only, capped at 3/week; paid = full bidirectional chat + nudges
- Schedule proactive nudges via ARQ job `advisor:nudge`

**Visual context strategy (hybrid):**
- **Default path — appearance snapshots (JSON):** After every face analysis, `FaceAnalysisService` serializes a structured snapshot from MediaPipe + classification results and stores it as a `user_memory` of type `analysis_insight` (with pgvector embedding). The advisor uses these snapshots for routine context — cheap, fast, semantically searchable.
- **On-demand path — actual images:** For visual comparison queries ("compare my before and after", "can you see my jawline?"), the AdvisorService fetches Supabase Storage signed URLs for the relevant analysis images and passes them as Claude vision content blocks. No extra storage layer needed — images are already in Supabase Storage.

Snapshot schema (stored in `user_memories.content` JSONB):
```json
{
  "analysis_id": "uuid",
  "date": "ISO-date",
  "face_shape": "oval",
  "symmetry_score": 0.82,
  "key_features": { "jawline": "defined", "eyes": "almond, deep-set" },
  "scores": { "overall": 7.2, "symmetry": 8.1, "structure": 6.8 },
  "recommendations": ["grow beard along jawline", "try curtain bangs"],
  "image_path": "generated-images/uuid.jpg",
  "changes_from_previous": ["jawline more defined vs 2026-02-10 analysis"]
}
```

`FaceAnalysisService` responsibility added: after analysis completes, write snapshot to `user_memories` (type `analysis_insight`). No new infrastructure — one extra DB write per analysis.

**LLM:**
- Chat responses: `claude-sonnet-4-6` (Anthropic Claude API)
- Visual comparison queries: `claude-sonnet-4-6` with vision content blocks (signed Supabase Storage URLs)
- Nudge generation: `claude-haiku-4-5-20251001` (lower cost for scheduled messages)
- Context injection: system prompt includes user analysis history + top-K memories + advisor persona definition

**Advisor persona:** Ada (she/her) — defined in `app/advisor/SOUL.md` following the OpenClaw/SoulSpec pattern. The SOUL.md file is the single source of truth for Ada's identity, voice, values, boundaries, and example interactions. It is loaded as the system prompt foundation for all advisor LLM calls (chat + nudges). The AdvisorService reads this file at startup and injects it as the first system message in every conversation context.

### New Database Tables

```sql
-- Conversation sessions (one active per user at a time)
CREATE TABLE advisor_conversations (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  summarised_at TIMESTAMPTZ,
  summary      TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Individual messages within a conversation
CREATE TABLE advisor_messages (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES advisor_conversations(id) ON DELETE CASCADE,
  role            TEXT NOT NULL CHECK (role IN ('user', 'advisor')),
  content         TEXT NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Persistent user memories with pgvector embeddings for semantic recall
CREATE TABLE user_memories (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  type       TEXT NOT NULL CHECK (type IN (
               'goal', 'dismissed_suggestion', 'accepted_suggestion',
               'user_note', 'analysis_insight'
             )),
  content    JSONB NOT NULL,
  embedding  vector(1536),  -- text-embedding-3-small or equivalent
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_user_memories_user_id ON user_memories(user_id);
CREATE INDEX idx_user_memories_embedding ON user_memories USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_advisor_conversations_user_id ON advisor_conversations(user_id);
CREATE INDEX idx_advisor_messages_conversation_id ON advisor_messages(conversation_id);
```

Enable pgvector: `CREATE EXTENSION IF NOT EXISTS vector;` in first migration.

### New Environment Variables

```
ANTHROPIC_API_KEY                     # Claude API — required
ADVISOR_NUDGE_WEEKLY_LIMIT=3          # Free tier nudge cap
ADVISOR_CONTEXT_MEMORY_LIMIT=20       # Top-K memories injected per turn
ADVISOR_PERSONA_NAME=TBD              # Advisor character name (set before Story 7-2)
```

### New ARQ Job Type

`advisor:nudge` — queued by trigger conditions:
- Post-analysis completion (analysis insight nudge)
- Weekly scheduled check-in (every 7 days since last nudge)
- Milestone events (10th analysis, first community reaction spike)

Free tier: capped at `ADVISOR_NUDGE_WEEKLY_LIMIT` per user per rolling 7-day window, enforced in EntitlementService.

### API Endpoints Added (Story 7-2)

```
POST   /advisor/messages              # Send message (paid only; 403 for free)
GET    /advisor/conversations         # Conversation history (paginated)
GET    /advisor/messages              # Messages in active conversation
POST   /memories                      # Add user goal or note
GET    /memories                      # List user memories (paginated, filterable by type)
DELETE /memories/{id}                 # Delete single memory
DELETE /memories                      # Clear all memories (user-initiated wipe)
GET    /advisor/nudges                # Unread advisor-initiated messages (all tiers)
POST   /advisor/nudges/{id}/read      # Mark nudge as read
```

### Infrastructure Impact

- `ANTHROPIC_API_KEY` added to ECS task definition secrets (AWS Secrets Manager)
- Supabase pgvector extension enabled on nxme-dev, staging, and prod Supabase projects
- No new cloud services required — all within existing stack
- ARQ worker gains `advisor:nudge` job handler — no new worker process

### Stories Added to Plan

| Story | Title | Size | Wave | Dependencies |
|-------|-------|------|------|--------------|
| 7-1 | Advisor Memory Schema & pgvector Setup | S | 1 | — (extends story 1-1 DB migrations) |
| 7-2 | Advisor API — Chat, Nudges & Memory Management | M | 8 | 4-1, 3-3, 2-1 |
| 7-3 | Advisor Nudge Scheduler — ARQ Job & Trigger Conditions | S | 9 | 7-2 |
| 7-4 | Mobile Advisor UI — Chat Screen & Nudge Feed | M | 11 | 7-2, 6-5 |

**Plan totals after amendment:** 30 stories, 11 waves, 8 waves unchanged, stories added into waves 1/8/9/11.

