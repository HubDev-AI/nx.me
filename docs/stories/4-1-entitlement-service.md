---
id: "4-1-entitlement-service"
status: complete
created: 2026-03-16
---

# Story: Entitlement Service — Credit Ledger, State Machine & Trial Grant

## User Story

As the platform, I need a single authoritative entitlement module that manages credit balances, subscription states, and trial grants, so that no feature handler ever directly reads raw credit or subscription database fields.

## Acceptance Criteria

- Given `EntitlementService.get_entitlement(user_id)`, When called, Then it recomputes from `credit_ledger + subscriptions` tables; `users.tier` is updated as a denormalized cache in the same transaction but is never the sole source of truth (AC-D1).
- Given `EntitlementService.can_generate(user_id)`, When called, Then it returns `{ can_generate: bool, reason: str | None }` — a user with `tier = 'TRIAL'` and `trial_analyses_remaining = 0` returns `can_generate: False`.
- Given the credit ledger, When `CreditLedger.reserve(user_id)` is called, Then a ledger entry with `type='reserve', delta=-1` is created; `CreditLedger.release(reservation_id)` creates `type='release', delta=+1`; `CreditLedger.commit(reservation_id)` creates `type='commit', delta=0` — all three invariants (reserve+release=0, reserve+commit=-1) are verified by unit tests (Section 3.5 invariants).
- Given a grep scan of the entire codebase, When `EntitlementService` is complete, Then zero occurrences of direct `credit_ledger` or `subscriptions` table reads exist outside the entitlement module (AC-D1).
- Given any code referencing tier values, When scanned, Then only `TRIAL`, `CREDIT_HOLDER`, `PREMIUM` string constants are used — zero inline literals.

## Architecture Guardrails

### Technology Stack

- **Backend:** Python 3.12 + FastAPI
- **Database:** Supabase PostgreSQL via supabase-py 2.15.1 (pinned in requirements.txt)
- **Cache:** Redis 7.2 via redis-py (async) for tier caching and concurrent generation counters
- **Config:** pydantic-settings 2.9.1 (pinned in requirements.txt)
- **No automated tests during development** -- per QA skill decision; however, the AC-3 credit ledger invariant tests ARE required by the architecture (Section 10.4). These are the exception: minimal unit tests for reserve/release/commit invariants only.

### Non-Negotiable Boundaries

- **AC-D1 LOCKED:** All entitlement checks route through `EntitlementService`; no handler reads subscription or credit fields directly. After this story is complete, a grep for `.table("credit_ledger")` and `.table("subscriptions")` outside `app/entitlement/` must return zero matches.
- **C-2 LOCKED:** No attractiveness score or ranking in any API response, UI element, or data model field.

### Entitlement State Machine

```
TRIAL (trials_remaining > 0)
  -> exhaust trials -> TRIAL [trials_remaining = 0, can_generate = false]
  -> purchase credits -> CREDIT_HOLDER
  -> subscribe -> PREMIUM

CREDIT_HOLDER (credit_balance > 0)
  -> exhaust credits -> TRIAL [trials_remaining = 0]
  -> subscribe -> PREMIUM

PREMIUM (active subscription)
  -> cancel (access continues until billing_period_end)
  -> period ends -> CREDIT_HOLDER (if credit_balance > 0) else TRIAL [trials_remaining = 0]
```

**Note on "exhausted trial" state:** A user who has exhausted their free trial and has neither credits nor a subscription is represented as `tier = 'TRIAL'` with `trial_analyses_remaining = 0`. This is NOT a separate tier value -- it is a logical state within `TRIAL`. `EntitlementService.can_generate()` returns `False` for this state and the handler returns HTTP 402 with paywall data.

### DB-Driven Tier System (Amended by A-4)

Tiers are rows in the `tiers` table, seeded by migration `0004_seed_tiers.sql`. Application code reads `user.tier_id: UUID` and fetches a `TierRecord` from the DB (Redis-cached, TTL 5 min). No tier name or enum ever appears in business logic conditionals.

The `tiers.slug` column exists solely for migrations and admin scripts. Business logic NEVER conditions on slug -- it reads the row's limit/feature columns directly.

**Registration assigns tier by:** `_tier_repo.get_default()` which selects `WHERE is_default = true AND is_active = true`.

### `users` Table Schema (Amended by A-4: `tier_id` UUID FK, not `tier` TEXT)

```sql
CREATE TABLE users (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username                  TEXT UNIQUE NOT NULL,
    display_name              TEXT NOT NULL,
    email                     TEXT UNIQUE,
    avatar_storage_key        TEXT,
    tier_id                   UUID NOT NULL REFERENCES tiers(id),
    trial_analyses_remaining  INT NOT NULL DEFAULT 2,
    guest_session_token       TEXT,
    email_verified            BOOLEAN NOT NULL DEFAULT FALSE,
    is_minor                  BOOLEAN,
    deleted_at                TIMESTAMPTZ,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Note: Architecture.md describes `users.tier TEXT CHECK (...)` but A-4 supersedes this. The actual DB has `tier_id UUID REFERENCES tiers(id)`. `users.tier` TEXT column does NOT exist. The "denormalized cache" referenced in AC-1 means `users.tier_id` is updated in the same transaction as entitlement-modifying operations. The canonical tier is always recomputed from `credit_ledger + subscriptions`.

### `tiers` Table Schema (Amended by A-4)

```sql
CREATE TABLE tiers (
    id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug                            TEXT NOT NULL UNIQUE,
    display_name                    TEXT NOT NULL,
    is_default                      BOOLEAN NOT NULL DEFAULT false,
    is_active                       BOOLEAN NOT NULL DEFAULT true,
    generation_type                 TEXT NOT NULL,
    generation_limit                INT,
    generation_period_seconds       INT,
    advisor_nudges_type             TEXT NOT NULL,
    advisor_nudges_limit            INT,
    advisor_nudges_period_seconds   INT,
    max_concurrent_generations      INT         NOT NULL DEFAULT 1,
    identity_similarity_threshold   DECIMAL(4,3) NOT NULL DEFAULT 0.800,
    feature_advisor_chat            BOOLEAN NOT NULL DEFAULT false,
    feature_visual_comparison       BOOLEAN NOT NULL DEFAULT false,
    stripe_price_id                 TEXT,
    credits_based                   BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_tiers_one_default ON tiers(is_default) WHERE is_default = true;
ALTER TABLE tiers ADD CONSTRAINT chk_default_requires_active
    CHECK (NOT is_default OR is_active);
```

Seed data (from `0004_seed_tiers.sql`):

| slug | display_name | generation_type | generation_limit | credits_based | max_concurrent | feature_advisor_chat | feature_visual_comparison |
|------|-------------|-----------------|-----------------|---------------|----------------|---------------------|--------------------------|
| `free` | Free | daily | 1 | false | 1 | false | false |
| `credits` | Credits | credits | NULL | true | 2 | false | true |
| `premium` | Premium | monthly | 100 | false | 3 | true | true |

Fixed UUIDs (from `app/constants/tiers.py`):
- `TIER_ID_TRIAL = "a0000000-0000-0000-0000-000000000001"` (slug: `free`)
- `TIER_ID_CREDIT_HOLDER = "a0000000-0000-0000-0000-000000000002"` (slug: `credits`)
- `TIER_ID_PREMIUM = "a0000000-0000-0000-0000-000000000003"` (slug: `premium`)

### `credit_ledger` Table Schema

```sql
CREATE TABLE credit_ledger (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES users(id),
    delta        INT NOT NULL,
    type         TEXT NOT NULL
                 CHECK (type IN ('trial_grant','purchase','reserve','commit','release','refund','adjustment')),
    reference_id UUID,
    note         TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_ledger_user_id ON credit_ledger (user_id, created_at DESC);
```

**Balance Invariants (enforced by unit tests -- AC-3):**

- Balance query: `SELECT SUM(delta) FROM credit_ledger WHERE user_id = $1`
- This includes ALL types including `reserve`. Reserve/release pairs net to zero. Reserve/commit pairs net to -1 (the credit is consumed).
- **Invariant 1:** reserve + release = 0 (net). `reserve: delta = -1` (optimistic hold), `release: delta = +1` (undo the hold).
- **Invariant 2:** reserve + commit = -1 (net). `reserve: delta = -1`, `commit: delta = 0` (no second deduction; reserve already reduced balance).
- **Invariant 3:** No new `type` value may be added without a corresponding unit test asserting its balance invariant. This is a CI gate.

### `credit_reservations` Table Schema

```sql
CREATE TABLE credit_reservations (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES users(id),
    amount       INT NOT NULL DEFAULT 1,
    status       TEXT NOT NULL DEFAULT 'reserved'
                 CHECK (status IN ('reserved', 'committed', 'released')),
    job_id       UUID,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at  TIMESTAMPTZ
);
CREATE INDEX idx_reservations_user_status ON credit_reservations (user_id, status);
```

### `subscriptions` Table Schema

```sql
CREATE TABLE subscriptions (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                  UUID NOT NULL REFERENCES users(id),
    provider                 TEXT NOT NULL DEFAULT 'stripe',
    provider_subscription_id TEXT UNIQUE NOT NULL,
    status                   TEXT NOT NULL
                             CHECK (status IN ('active', 'cancelled', 'expired', 'past_due')),
    billing_period_start     TIMESTAMPTZ NOT NULL,
    billing_period_end       TIMESTAMPTZ NOT NULL,
    cancelled_at             TIMESTAMPTZ,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_subscriptions_user ON subscriptions (user_id) WHERE status = 'active';
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

`status` lifecycle (generation only):
- `reserved` -> set when ARQ job is enqueued (credit deducted from balance)
- `committed` -> set when generation completes successfully
- `released` -> set when generation fails (credit restored)

For non-credit tiers (daily/weekly/monthly), events are always `committed` immediately at enqueue time. Counting only includes `committed` events.

### Tier Constants (AC-5: named constants only)

From `app/constants/tiers.py`:

```python
TRIAL: str = "TRIAL"
CREDIT_HOLDER: str = "CREDIT_HOLDER"
PREMIUM: str = "PREMIUM"
```

These are the ONLY acceptable tier string literals in the entire codebase. Used in API response serialization, queue routing, admin scripts, seed references. NEVER used in `EntitlementService` business logic conditionals (A-4: business logic reads tier DB row columns, not slugs/names).

### LimitType Enum

From `app/services/limits.py`:

```python
from enum import StrEnum

class LimitType(StrEnum):
    TOTAL     = "total"
    DAILY     = "daily"
    WEEKLY    = "weekly"
    MONTHLY   = "monthly"
    PERIOD    = "period"
    CREDITS   = "credits"
    UNLIMITED = "unlimited"
```

### EntitlementResult (Amended by A-5)

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class EntitlementResult:
    allowed: bool
    error_code: str | None = None
    limit: int | None = None
    used: int | None = None
    retry_after: datetime | None = None
    reset_in_seconds: int | None = None
    upgrade_available: bool = False
```

### Error Codes (Amended by A-5)

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

API error response shape:

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

### FastAPI Entitlement Dependencies (Amended by A-5)

Route-level enforcement via `Depends` -- no middleware (middleware runs before auth, lacks user context).

```python
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

### Concurrent Generation Guard (Redis) (Amended by A-5)

```python
# In EntitlementService.check("generation"):
concurrent_key = f"concurrent:{user_id}"
current = int(await redis.get(concurrent_key) or 0)
if current >= tier.max_concurrent_generations:
    return EntitlementResult(allowed=False, error_code="TIER_CONCURRENT_LIMIT",
                              upgrade_available=False)

# In ARQ worker -- job start:
await redis.incr(concurrent_key)
await redis.expire(concurrent_key, settings.GENERATION_TIMEOUT_SECONDS + 30)

# In ARQ worker -- job end (success or failure):
await redis.decr(concurrent_key)
```

### EntitlementService.check() -- Full Dispatch (Amended by A-5)

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

### EntitlementService._get_tier() Runtime Pattern (Amended by A-4)

```python
class EntitlementService:
    async def _get_tier(self, user_id: UUID) -> TierRecord:
        """Fetch tier for user, Redis-cached (TTL 5 min)."""
        user = await self._user_repo.get(user_id)
        return await self._tier_repo.get(user.tier_id)  # cache key: tier:{tier_id}

    async def can_generate(self, user_id: UUID) -> CanGenerateResult:
        tier = await self._get_tier(user_id)
        match LimitType(tier.generation_type):
            case LimitType.UNLIMITED:
                return CanGenerateResult(can_generate=True, reason=None)
            case LimitType.CREDITS:
                if await self._has_credits(user_id):
                    return CanGenerateResult(can_generate=True, reason=None)
                return CanGenerateResult(can_generate=False, reason="No credits remaining")
            case LimitType.DAILY:
                since = now() - timedelta(days=1)
            case LimitType.WEEKLY:
                since = now() - timedelta(weeks=1)
            case LimitType.MONTHLY:
                since = now() - timedelta(days=30)
            case LimitType.PERIOD:
                since = now() - timedelta(seconds=tier.generation_period_seconds)
            case LimitType.TOTAL:
                count = await self._count_all(user_id)
                if count < tier.generation_limit:
                    return CanGenerateResult(can_generate=True, reason=None)
                return CanGenerateResult(can_generate=False, reason="Lifetime limit reached")
        count = await self._count_since(user_id, since)
        if count < tier.generation_limit:
            return CanGenerateResult(can_generate=True, reason=None)
        return CanGenerateResult(can_generate=False, reason="Generation limit reached")

    async def has_feature(self, user_id: UUID, feature: str) -> bool:
        tier = await self._get_tier(user_id)
        return getattr(tier, f"feature_{feature}", False)

    async def max_concurrent(self, user_id: UUID) -> int:
        return (await self._get_tier(user_id)).max_concurrent_generations

    async def similarity_threshold(self, user_id: UUID) -> float:
        return float((await self._get_tier(user_id)).identity_similarity_threshold)
```

### `users.tier_id` is a Derived Read Cache

`EntitlementService.get_entitlement(user_id)` always recomputes the canonical entitlement state from `credit_ledger + subscriptions` (never reads `users.tier_id` as the source of truth). `users.tier_id` is updated as a denormalized performance cache after every entitlement-modifying operation (credit purchase, subscription event, trial grant) in the same transaction. This means:
- `GET /entitlement` always reflects ground truth
- `users.tier_id` can be used for fast filtering (e.g., queue priority assignment at enqueue time) but must never be the sole source of truth in business logic

### Slug-to-Tier-Name Mapping for API Responses

Existing in `app/api/entitlement.py` -- maps DB tier slugs to public API tier identifiers:

```python
_SLUG_TO_TIER_NAME: dict[str, str] = {
    "free": "TRIAL",
    "credits": "CREDIT_HOLDER",
    "premium": "PREMIUM",
}
```

This mapping is used for API response serialization ONLY. It must use constants from `app/constants/tiers.py`, not inline strings.

### GET /entitlement API Response Contract

```json
// CREDIT_HOLDER
{ "tier": "CREDIT_HOLDER", "credit_balance": 4, "trial_analyses_remaining": 0, "subscription": null }
// PREMIUM
{ "tier": "PREMIUM", "credit_balance": 0, "trial_analyses_remaining": 0,
  "subscription": { "status": "active", "billing_period_end": "2026-04-15T00:00:00Z", "cancel_at_period_end": false } }
// TRIAL (exhausted)
{ "tier": "TRIAL", "credit_balance": 0, "trial_analyses_remaining": 0, "subscription": null }
```

### File Structure for This Story

```
app/
  entitlement/
    __init__.py               # Already exists
    trial_grantor.py          # Already exists (Story 2-1) -- keep as-is
    service.py                # NEW: EntitlementService -- orchestrates tier resolution, can_generate, check, get_entitlement
    ledger.py                 # NEW: CreditLedger -- append-only ledger with reserve/commit/release
    models.py                 # NEW: EntitlementState, CanGenerateResult, EntitlementResult, TierRecord dataclasses
    usage_repo.py             # NEW: UsageRepository -- queries usage_events for rolling-window checks
    tier_repo.py              # NEW: TierRepository -- fetches TierRecord from DB with Redis cache
  api/
    entitlement.py            # MODIFY: refactor GET /entitlement to delegate to EntitlementService
    deps.py                   # MODIFY: add get_entitlement_service dependency provider
```

### Transaction Requirements (Amended by A-6)

| Operation | Transaction required? | Why |
|-----------|----------------------|-----|
| `CreditLedger.reserve()` | Yes (reserve entry + reservation row) | Reservation meaningless without ledger entry |
| `CreditLedger.release()` | Yes (release entry + reservation status) | Must be atomic |
| `CreditLedger.commit()` | Yes (commit entry + reservation status) | Must be atomic |
| `get_entitlement()` | No (read-only) | Single SELECT with joins |
| `_update_tier_cache()` | Yes (UPDATE users.tier_id in same txn as ledger write) | Cache must match truth |

Since Supabase PostgREST does not support multi-statement transactions, use RPC calls wrapping both writes atomically (consistent with the `grant_trial` RPC pattern in `trial_grantor.py`). Fallback to sequential writes with idempotency checks when RPC is unavailable.

## Verified Interfaces

### TrialGrantor (app/entitlement/trial_grantor.py)

- **Source:** `app/entitlement/trial_grantor.py:29-33`
- **Signature:** `class TrialGrantor` with `def __init__(self, supabase: Client) -> None` and `def grant(self, user_id: UUID) -> None`
- **Plan match:** Matches -- existing implementation from Story 2-1. Uses `self._sb.table("credit_ledger")` for idempotency check and `self._sb.rpc("grant_trial", ...)` for atomic grant. This story does NOT modify TrialGrantor.

### Settings (app/config.py)

- **Source:** `app/config.py:42-45`
- **Signature:** `FREE_TRIAL_ANALYSES: int = 2`, `IDENTITY_SIMILARITY_THRESHOLD: float = 0.80`, `MAX_CONCURRENT_GENERATIONS_PER_USER: int = 3`
- **Plan match:** Matches -- these are global defaults/ceilings. Per-tier values in DB take precedence in EntitlementService (A-4 vs AC-3 tension resolution per napkin).

### Settings -- Redis (app/config.py)

- **Source:** `app/config.py:19`
- **Signature:** `REDIS_URL: str = "redis://localhost:6379/0"`
- **Plan match:** Matches

### get_supabase_service (app/db/client.py)

- **Source:** `app/db/client.py:10`
- **Signature:** `def get_supabase_service() -> Client`
- **Plan match:** Matches

### get_current_user (app/api/deps.py)

- **Source:** `app/api/deps.py:40-43`
- **Signature:** `def get_current_user(authorization: Annotated[str | None, Header()] = None, supabase: Client = Depends(get_supabase)) -> UserClaims`
- **Plan match:** Matches -- Amended by A-8 (sub: Required[str])

### get_supabase (app/api/deps.py)

- **Source:** `app/api/deps.py:25-27`
- **Signature:** `def get_supabase(request: Request) -> Client`
- **Plan match:** Matches

### get_redis (app/api/deps.py)

- **Source:** `app/api/deps.py:30-32`
- **Signature:** `def get_redis(request: Request) -> aioredis.Redis`
- **Plan match:** Matches

### UserClaims (app/api/middleware/auth.py)

- **Source:** `app/api/middleware/auth.py:22-34`
- **Signature:** `class UserClaims(TypedDict, total=False)` with `sub: Required[str]`, `exp: Required[int]`
- **Plan match:** Matches -- Amended by A-8

### LimitType (app/services/limits.py)

- **Source:** `app/services/limits.py:4-11`
- **Signature:** `class LimitType(StrEnum)` with values `TOTAL`, `DAILY`, `WEEKLY`, `MONTHLY`, `PERIOD`, `CREDITS`, `UNLIMITED`
- **Plan match:** Matches

### Tier Constants (app/constants/tiers.py)

- **Source:** `app/constants/tiers.py:5-13`
- **Signature:** `TRIAL: str = "TRIAL"`, `CREDIT_HOLDER: str = "CREDIT_HOLDER"`, `PREMIUM: str = "PREMIUM"`, plus `TIER_ID_TRIAL`, `TIER_ID_CREDIT_HOLDER`, `TIER_ID_PREMIUM` fixed UUID strings
- **Plan match:** Matches

### Existing GET /entitlement endpoint (app/api/entitlement.py)

- **Source:** `app/api/entitlement.py:31-86`
- **Signature:** `def get_entitlement(claims: dict = Depends(get_current_user), supabase: Client = Depends(get_supabase)) -> EntitlementResponse`
- **Plan match:** This endpoint currently reads `credit_ledger` and `users` tables directly. Story 4-1 refactors it to delegate to `EntitlementService`. The existing `_SLUG_TO_TIER_NAME` mapping and `EntitlementResponse` Pydantic model will be reused/moved.

### app/main.py lifespan (app/main.py)

- **Source:** `app/main.py:22-52`
- **Signature:** `async def lifespan(app: FastAPI) -> AsyncIterator[None]`
- **Plan match:** Matches -- this story does NOT modify lifespan.

### EntitlementService.get_entitlement (interface contract -- this story defines it)

- **Source:** Not yet implemented -- this story creates it
- **Signature:** `async def get_entitlement(self, user_id: UUID) -> EntitlementState`
- **Plan match:** UNVERIFIED -- source not yet implemented, using plan contract

### EntitlementService.can_generate (interface contract -- this story defines it)

- **Source:** Not yet implemented -- this story creates it
- **Signature:** `async def can_generate(self, user_id: UUID) -> CanGenerateResult`
- **Plan match:** UNVERIFIED -- source not yet implemented, using plan contract

### CreditLedger.reserve / release / commit (interface contract -- this story defines it)

- **Source:** Not yet implemented -- this story creates it
- **Signatures:**
  - `def reserve(self, user_id: UUID) -> UUID` (returns reservation_id)
  - `def release(self, reservation_id: UUID) -> None`
  - `def commit(self, reservation_id: UUID) -> None`
- **Plan match:** UNVERIFIED -- source not yet implemented, using plan contract

## Tasks

- [x] Task 1: Create `app/entitlement/models.py` -- EntitlementState, CanGenerateResult, EntitlementResult, TierRecord dataclasses
  - Maps to: AC-1 (EntitlementState), AC-2 (CanGenerateResult with can_generate + reason fields)
  - Files: `app/entitlement/models.py`

- [x] Task 2: Create `app/entitlement/tier_repo.py` -- TierRepository with Redis-cached tier lookups
  - Maps to: AC-1 (tier resolution from DB), AC-5 (no inline tier literals)
  - Files: `app/entitlement/tier_repo.py`

- [x] Task 3: Create `app/entitlement/ledger.py` -- CreditLedger with reserve/release/commit and balance query
  - Maps to: AC-3 (all three ledger invariants)
  - Files: `app/entitlement/ledger.py`

- [x] Task 4: Create `app/entitlement/usage_repo.py` -- UsageRepository for rolling-window usage event queries
  - Maps to: AC-2 (can_generate relies on usage counts for time-window tiers)
  - Files: `app/entitlement/usage_repo.py`

- [x] Task 5: Create `app/entitlement/service.py` -- EntitlementService orchestrator (get_entitlement, can_generate, check, has_feature)
  - Maps to: AC-1 (get_entitlement recomputes from credit_ledger + subscriptions), AC-2 (can_generate returns bool + reason)
  - Files: `app/entitlement/service.py`

- [x] Task 6: Modify `app/api/entitlement.py` -- refactor GET /entitlement to delegate to EntitlementService; add `get_entitlement_service` dependency to `app/api/deps.py`; add `require_entitlement` and `require_feature` dependencies
  - Maps to: AC-1 (entitlement endpoint uses service), AC-4 (no direct table reads outside entitlement module), AC-5 (use constants from app/constants/tiers.py)
  - Files: `app/api/entitlement.py`, `app/api/deps.py`

- [x] Task 7: Credit ledger invariant tests and codebase grep verification
  - Maps to: AC-3 (reserve+release=0, reserve+commit=-1 verified by unit tests), AC-4 (grep scan for direct table reads), AC-5 (grep scan for inline tier literals)
  - Files: `tests/test_credit_ledger_invariants.py` (minimal -- only the invariant tests required by architecture Section 10.4)

## must_haves

truths:
  - "EntitlementService.get_entitlement(user_id) recomputes tier from credit_ledger SUM(delta) + subscriptions WHERE status = 'active'; never reads users.tier_id as sole source of truth"
  - "EntitlementService.can_generate(user_id) returns CanGenerateResult with can_generate=False and reason string for a user with tier slug 'free' and trial_analyses_remaining=0"
  - "CreditLedger.reserve(user_id) creates a credit_ledger entry with type='reserve' and delta=-1 and a credit_reservations entry with status='reserved'"
  - "CreditLedger.release(reservation_id) creates a credit_ledger entry with type='release' and delta=+1 and updates credit_reservations.status to 'released'"
  - "CreditLedger.commit(reservation_id) creates a credit_ledger entry with type='commit' and delta=0 and updates credit_reservations.status to 'committed'"
  - "For a user with initial balance 2: reserve(user_id) then release(reservation_id) results in balance() returning 2 (net zero)"
  - "For a user with initial balance 2: reserve(user_id) then commit(reservation_id) results in balance() returning 1 (net minus one)"
  - "grep for .table('credit_ledger') or .table('subscriptions') outside app/entitlement/ returns zero matches after story completion"
  - "grep for inline tier string literals ('TRIAL', 'CREDIT_HOLDER', 'PREMIUM') outside app/constants/tiers.py, app/config/tiers.py, app/migrations/, and test files returns zero matches"
  - "TierRepository fetches tier row by UUID from tiers table and caches in Redis with TTL"
  - "EntitlementService.check('generation') returns EntitlementResult with error_code='TIER_CONCURRENT_LIMIT' when Redis concurrent counter >= tier.max_concurrent_generations"

artifacts:
  - path: "app/entitlement/models.py"
    contains: ["EntitlementState", "CanGenerateResult", "EntitlementResult", "TierRecord", "can_generate", "reason", "allowed", "error_code"]
  - path: "app/entitlement/tier_repo.py"
    contains: ["TierRepository", "get", "get_default", "TierRecord", "tier_id", "Redis"]
  - path: "app/entitlement/ledger.py"
    contains: ["CreditLedger", "reserve", "release", "commit", "balance", "credit_ledger", "credit_reservations", "delta"]
  - path: "app/entitlement/usage_repo.py"
    contains: ["UsageRepository", "get_events", "usage_events", "action", "status"]
  - path: "app/entitlement/service.py"
    contains: ["EntitlementService", "get_entitlement", "can_generate", "check", "has_feature", "_get_tier", "_check_window", "LimitType"]
  - path: "app/api/entitlement.py"
    contains: ["EntitlementService", "get_entitlement_service"]
  - path: "app/api/deps.py"
    contains: ["get_entitlement_service"]
  - path: "tests/test_credit_ledger_invariants.py"
    contains: ["test_reserve_release_nets_zero", "test_reserve_commit_nets_minus_one", "CreditLedger"]

key_links:
  - pattern: "from app.config import settings"
    in: ["app/entitlement/service.py", "app/entitlement/tier_repo.py"]
  - pattern: "from app.entitlement.models import"
    in: ["app/entitlement/service.py", "app/entitlement/ledger.py", "app/entitlement/tier_repo.py", "app/entitlement/usage_repo.py", "app/api/entitlement.py"]
  - pattern: "from app.entitlement.service import EntitlementService"
    in: ["app/api/deps.py", "app/api/entitlement.py"]
  - pattern: "from app.entitlement.ledger import CreditLedger"
    in: ["app/entitlement/service.py", "tests/test_credit_ledger_invariants.py"]
  - pattern: "from app.services.limits import LimitType"
    in: ["app/entitlement/service.py"]
  - pattern: "from app.constants.tiers import"
    in: ["app/api/entitlement.py"]
  - pattern: "from app.api.deps import get_current_user, get_supabase"
    in: ["app/api/entitlement.py"]
  - pattern: "from app.api.deps import get_entitlement_service"
    in: ["app/api/entitlement.py"]
  - pattern: "get_entitlement_service"
    in: ["app/api/deps.py", "app/api/entitlement.py"]
  - pattern: "require_entitlement"
    in: ["app/api/deps.py"]
  - pattern: "require_feature"
    in: ["app/api/deps.py"]

## Dev Notes

### Testing Approach

Zero automated tests per QA skill decision, EXCEPT for the credit ledger invariant tests which are architecturally mandated (Section 10.4, NFR-16):

- `tests/test_credit_ledger_invariants.py` -- minimal tests verifying:
  - `reserve + release = net zero balance`
  - `reserve + commit = net minus one balance`
- These tests run against a real local Supabase instance (integration tests, not mocked)
- Test isolation: per-test unique user with UUID prefix
- Framework: pytest (already in requirements.txt for story 1-1 migration runner tests)

All other verification is via manual testing against local Supabase:
- Call `GET /entitlement` and verify response matches expected state
- Use Supabase Studio (`http://127.0.0.1:54323`) to inspect `credit_ledger`, `credit_reservations`, `subscriptions` rows
- Grep codebase for direct table reads: `grep -r '.table("credit_ledger")' app/ --include='*.py' | grep -v entitlement/`
- Grep codebase for inline tier literals: `grep -rn "TRIAL\|CREDIT_HOLDER\|PREMIUM" app/ --include='*.py' | grep -v constants/tiers.py | grep -v config/tiers.py | grep -v migrations/`

### Conventions from Prior Stories

**Story 1-1 established:**
- `from app.config import settings` is the canonical config import pattern
- `app/migrations/NNNN_name.sql` is the migration file convention
- pydantic-settings `Settings` class with `SettingsConfigDict(env_file=".env", extra="ignore")`
- All SQL: `snake_case` table and column names; `TIMESTAMPTZ` for all timestamps
- `LimitType` StrEnum at `app/services/limits.py`
- Tier constants at `app/constants/tiers.py` with fixed UUIDs matching seed data
- `app/config/tiers.py` is seed-only -- NEVER imported at runtime

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
- Port/adapter pattern with lazy imports inside feature module (NOT in a separate `app/adapters/` directory)
- `_get_*_adapter()` factory functions with lazy imports based on config adapter selection
- Dataclasses with `frozen=True` for immutable value objects
- `datetime.now(tz=timezone.utc).isoformat()` for timestamps (not bare `now()`)
- Error response format: `{"error": {"code": "...", "message": "...", "retry_eligible": true/false}}`
- Supabase `Client` is synchronous -- async wrappers (`async def`) are fine but the underlying calls are sync
- Module docstrings with interface contract reference

**Story 3-2 established:**
- `asyncio.get_event_loop().run_in_executor()` for CPU-bound sync operations in async handlers
- FaceShape `StrEnum` pattern for domain value objects
- MediaPipe model pre-loaded in lifespan before yield

### Existing Entitlement Code to Integrate

**`app/entitlement/trial_grantor.py`** (Story 2-1): Already exists, already inside the entitlement module. Uses `self._sb.table("credit_ledger")` for idempotency check. This is ACCEPTABLE per AC-4 because it is inside `app/entitlement/`. Do NOT modify this file.

**`app/api/entitlement.py`** (Story 2-1): The GET /entitlement endpoint currently reads `credit_ledger` and `users` tables directly. This VIOLATES AC-4 after story 4-1 is complete. Task 6 refactors this to delegate to `EntitlementService`.

### Async + Sync Considerations

Supabase `Client` methods are synchronous. The `EntitlementService` methods are `async def` (matching the FastAPI handler pattern and future Redis async calls), but the underlying Supabase calls are sync. This is consistent with story 3-1 and 3-2 patterns.

Redis calls via `redis.asyncio` are truly async. The concurrent generation guard and tier cache reads use `await redis.get()` / `await redis.set()`.

### Local Dev Environment

```bash
# Start local Supabase (DB + Auth + Storage):
supabase start

# Start Redis:
docker compose up -d

# Start the API (hot-reload):
./scripts/dev-start.sh
```

Environment variables relevant to this story:
- `SUPABASE_URL` -- local Supabase URL (from `supabase status`, typically `http://127.0.0.1:54321`)
- `SUPABASE_SERVICE_ROLE_KEY` -- local service role key (from `supabase status`)
- `REDIS_URL` -- `redis://localhost:6379/0` (default, from Docker Compose)
- `FREE_TRIAL_ANALYSES` -- `2` (default) -- used by TrialGrantor
- `GENERATION_TIMEOUT_SECONDS` -- `60` (default) -- safety TTL for Redis concurrent counter

### Library Versions

- **supabase-py:** 2.15.1 (pinned in requirements.txt -- project uses this version, not latest 2.28.2)
- **redis-py:** 7.1.1 (verified 2026-03-16 via PyPI) -- `redis.asyncio` for async Redis operations
- **pydantic-settings:** 2.9.1 (pinned in requirements.txt -- project uses this version, not latest 2.13.1)
- **pytest:** already in requirements.txt (used by migration runner tests in story 1-1)

### Supabase RPC Pattern for Transactions

Since Supabase PostgREST does not support multi-statement transactions, the pattern established in `trial_grantor.py` is:

1. Try RPC call wrapping both writes atomically
2. Catch exception if RPC function doesn't exist (fresh DB)
3. Fall back to sequential writes with idempotency check

For CreditLedger operations, define SQL functions:
- `credit_reserve(p_user_id UUID) -> UUID` -- creates reservation + ledger entry atomically
- `credit_release(p_reservation_id UUID) -> VOID` -- creates release entry + updates reservation status
- `credit_commit(p_reservation_id UUID) -> VOID` -- creates commit entry + updates reservation status

These RPCs should be defined in a new migration file if needed, or use the fallback pattern.

### A-4 vs AC-3 Tension Resolution

AC-3 says `FREE_TRIAL_ANALYSES`, `IDENTITY_SIMILARITY_THRESHOLD`, `MAX_CONCURRENT_GENERATIONS_PER_USER` must be named constants in config. A-4 says these are DB-driven per-tier values.

Resolution (from napkin): keep them in `app/config.py` as global defaults/ceilings. Per-tier values in the `tiers` DB table take precedence in `EntitlementService`. Config values serve as circuit-breaker / non-tier paths (e.g., stuck-job watchdog uses `GENERATION_TIMEOUT_SECONDS` from config, not from a tier row).

## Wave Structure

Wave 1: [Task 1, Task 2, Task 3, Task 4] -- independent, no shared output files
  - Task 1: models.py (dataclasses/enums only -- defines types used by other tasks but has no deps on them)
  - Task 2: tier_repo.py (imports from models.py, reads from DB + Redis)
  - Task 3: ledger.py (imports from models.py, reads/writes credit_ledger + credit_reservations)
  - Task 4: usage_repo.py (standalone, reads usage_events table)

Wave 2: [Task 5] -- depends on all Wave 1 outputs (service orchestrator imports models, tier_repo, ledger, usage_repo)

Wave 3: [Task 6, Task 7] -- independent of each other
  - Task 6: refactors API endpoint + deps.py (depends on Task 5 service)
  - Task 7: invariant tests (depends on Task 3 CreditLedger)
