---
id: "4-4-stripe-adapter"
status: ready
created: 2026-03-17
---

# Story: Stripe Adapter — Credit Purchase, Subscription & Webhook Idempotency

## User Story

As the platform, I need Stripe integrated for credit pack purchases and subscription lifecycle, with idempotent webhook handling, so that no raw card data touches NXME servers and payment events are processed exactly once.

## Acceptance Criteria

- Given `POST /credits/purchase`, When processed, Then a Stripe checkout session is created; no raw card data (PAN, CVV, expiry) is transmitted through any NXME-controlled endpoint — verified by network traffic audit (AC-NFR11).
- Given Stripe webhook `checkout.session.completed` delivered twice (retry scenario), When processed, Then the first delivery inserts into `processed_webhook_events(provider='stripe', event_id='evt_xxx')` and processes; the second delivery returns HTTP 200 immediately without re-processing (idempotency constraint).
- Given `customer.subscription.deleted` webhook, When processed, Then `subscriptions.status = 'expired'`; `EntitlementService.get_entitlement()` recomputes tier — if `credit_balance > 0` → `CREDIT_HOLDER`, else → `TRIAL`.
- Given a Stripe webhook without a valid `stripe-signature` header, When received, Then HTTP 401 is returned and no processing occurs.
- Given a Premium subscription cancellation, When `billing_period_end - 1s`, Then Premium access is granted; at `billing_period_end + 1s`, access is reverted — verified by clock-controlled test (AC-FR4).

## Architecture Guardrails

### Technology Stack

- **Backend:** Python 3.12 + FastAPI 0.115.12 (pinned in requirements.txt)
- **Database:** Supabase PostgreSQL via supabase-py 2.15.1 (pinned in requirements.txt)
- **Cache:** Redis 7.x via redis-py 5.2.1 (pinned in requirements.txt)
- **Auth:** JWT validation via PyJWT 2.10.1 (pinned in requirements.txt)
- **Config:** pydantic-settings 2.9.1 (pinned in requirements.txt)
- **Payments:** stripe 14.4.0 (to be added to requirements.txt)
- **No automated tests** -- per QA skill decision; zero test code written during development

### Non-Negotiable Boundaries

- **PCI-DSS SAQ-A (NFR-11):** All card collection via Stripe hosted payment sheet (mobile SDK). NXME never receives, transmits, or stores card data. Webhook payloads contain no card fields.
- **AC-D1:** All entitlement checks route through `EntitlementService`; no handler reads subscription or credit fields directly.
- **AC-A1:** Reserve-before-enqueue for all credit consumption.

### Adapter Pattern (Amended by A-3)

All external services are accessed through Protocol-based adapters. The existing codebase places adapters **inside their domain module** (not in a top-level `adapters/` directory). Examples:

- `app/generation/ports.py` -- `GlowUpGeneratorPort(Protocol)`
- `app/generation/adapters/falai.py` -- `FalAiAdapter`
- `app/generation/adapters/mock.py` -- `MockGeneratorAdapter`
- `app/image_pipeline/nsfw_screener.py` -- `NSFWScreenerPort(Protocol)`
- `app/image_pipeline/storage.py` -- `StoragePort(Protocol)`

**Follow the same pattern for payment.** Create the payment adapter within a `app/payment/` domain module:

```
app/payment/
    __init__.py
    ports.py              # PaymentPort(Protocol)
    adapters/
        __init__.py
        stripe_adapter.py # StripePaymentAdapter
        mock.py           # MockPaymentAdapter
```

#### PaymentPort Protocol (from A-3)

```python
class PaymentPort(Protocol):
    async def create_checkout_session(
        self, user_id: str, price_id: str, mode: str, success_url: str, cancel_url: str
    ) -> str:
        """Create a Stripe checkout session. Returns the checkout URL."""
        ...

    async def cancel_subscription(self, subscription_id: str) -> None:
        """Cancel subscription at period end."""
        ...

    def construct_webhook_event(self, payload: bytes, sig_header: str) -> dict:
        """Verify webhook signature and construct event object.
        Raises ValueError on invalid signature.
        """
        ...
```

NOTE: The architecture A-3 specifies `create_checkout(user_id, product_id) -> str` and `get_subscription(customer_id) -> dict | None`. The implementation expands these to cover the actual Stripe API surface needed for this story (checkout session creation with mode/URLs, webhook construction, subscription cancellation). Use the expanded signatures above.

#### Adapter Selection

Env var `ADAPTER__PAYMENT_ADAPTER` (already in `app/config.py`, default: `"mock"`).

For Stripe test mode: `ADAPTER__PAYMENT_ADAPTER=stripe`.

### Webhook Idempotency Pattern

All incoming webhook events are deduplicated via the `processed_webhook_events` table:

1. Verify `stripe-signature` header using Stripe SDK `stripe.Webhook.construct_event()`
2. Extract `event.id` (e.g., `evt_xxx`)
3. Attempt INSERT into `processed_webhook_events(provider='stripe', event_id=event.id)`
4. If UNIQUE constraint violation (duplicate) -- return HTTP 200 immediately, no processing
5. If INSERT succeeds -- route to event handler, process, return HTTP 200
6. If processing fails -- the event is already recorded; Stripe will retry, but we skip (acceptable: manual recovery for failed processing)

```sql
-- Existing table (migration 0001)
CREATE TABLE processed_webhook_events (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider     TEXT NOT NULL,
    event_id     TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider, event_id)
);
```

### Webhook Events Handled

| Event Type | Action |
|------------|--------|
| `checkout.session.completed` | If `mode='payment'`: grant credits via credit_ledger INSERT. If `mode='subscription'`: activate subscription. |
| `customer.subscription.created` | Insert `subscriptions` row with `status='active'` |
| `customer.subscription.updated` | If `cancel_at_period_end: true`: set `subscriptions.cancelled_at = NOW()`. If plan change: update billing dates. |
| `customer.subscription.deleted` | Set `subscriptions.status = 'expired'`. Recompute tier via EntitlementService. |
| `invoice.payment_failed` | Set `subscriptions.status = 'past_due'`. Log alert. |

### Subscription Lifecycle

```
User subscribes:
  POST /v1/subscriptions -> PaymentPort.create_checkout_session(mode='subscription')
  -> Returns checkout URL -> Mobile app opens Stripe Payment Sheet
  Stripe -> POST /webhooks/stripe {type: "checkout.session.completed"}
  INSERT processed_webhook_events(provider='stripe', event_id='evt_xxx')
  INSERT subscriptions row (status: active, billing_period_*)
  Update users.tier_id to premium tier ID
  EntitlementService: recompute tier -> PREMIUM

User cancels:
  DELETE /v1/subscriptions -> PaymentPort.cancel_subscription(subscription_id)
  -> Stripe sets cancel_at_period_end = true
  Stripe -> POST /webhooks/stripe {type: "customer.subscription.updated"}
  subscriptions.cancelled_at = NOW()
  (access continues until billing_period_end -- AC-FR4)

Period ends:
  Stripe -> POST /webhooks/stripe {type: "customer.subscription.deleted"}
  subscriptions.status = 'expired'
  Recompute tier: if credit_balance > 0 -> CREDIT_HOLDER, else -> TRIAL (free tier)
  Update users.tier_id accordingly
```

### Credit Purchase Flow

```
User purchases credit pack:
  POST /v1/credits/purchase -> PaymentPort.create_checkout_session(mode='payment')
  -> Returns checkout URL -> Mobile app opens Stripe Payment Sheet
  Stripe -> POST /webhooks/stripe {type: "checkout.session.completed", mode: "payment"}
  INSERT processed_webhook_events(provider='stripe', event_id='evt_xxx')
  credit_ledger INSERT: type='purchase', delta=+N (number of credits)
  If user was on free tier -> update users.tier_id to credits tier
```

### Database Tables (Existing -- Migration 0001)

#### `subscriptions` Table

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

#### `processed_webhook_events` Table

```sql
CREATE TABLE processed_webhook_events (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider     TEXT NOT NULL,
    event_id     TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider, event_id)
);
```

### `tiers` Table (Relevant Columns -- Migration 0002)

The `tiers` table includes a `stripe_price_id TEXT` column (nullable). Seed data (migration 0004) does NOT currently populate `stripe_price_id`. The `TierRecord` dataclass in `app/entitlement/models.py` does NOT yet include `stripe_price_id`. This story must:

1. Add `stripe_price_id: str | None` field to `TierRecord`
2. Update `TierRepository._row_to_tier()` and `_tier_to_cache()` to include `stripe_price_id`
3. Use `stripe_price_id` to map tiers to Stripe price objects in the payment adapter

Tier seed data reference:

| slug | stripe_price_id | credits_based |
|------|----------------|---------------|
| free | NULL | false |
| credits | NULL (set per-env via admin) | true |
| premium | env-specific (`price_*`) | false |

### `credit_ledger` Table (Existing -- Migration 0001)

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
```

For credit purchases from Stripe checkout, insert with `type='purchase'` and `delta=+N` (number of credits in the pack). `reference_id` is UUID type -- store NULL for Stripe events (the Stripe event ID is not UUID-compatible). Use the `note` field for the Stripe event ID audit trail.

### Router Table

From architecture section 2.2:

| Router | Endpoints |
|--------|-----------|
| `entitlement` | GET /entitlement, POST /credits/purchase, POST /subscriptions, DELETE /subscriptions |
| `webhooks` | POST /webhooks/stripe |

The payment endpoints (POST /credits/purchase, POST /subscriptions, DELETE /subscriptions) go in the existing entitlement router (`app/api/entitlement.py`). The webhook endpoint goes in a dedicated webhooks router (`app/api/webhooks.py`).

### DB-Driven Tier System (Amended by A-4)

Tiers are rows in the `tiers` table. Business logic never conditions on slug strings. `TierRecord` fields drive all decisions. The `users.tier_id` column is a denormalized cache updated after every entitlement-modifying operation.

After webhook processing that changes entitlement state (subscription activated, subscription expired, credit purchase), update `users.tier_id` to the appropriate tier UUID:

```python
from app.constants.tiers import TIER_ID_TRIAL, TIER_ID_CREDIT_HOLDER, TIER_ID_PREMIUM

# After subscription activation:
supabase.table("users").update({"tier_id": TIER_ID_PREMIUM}).eq("id", user_id).execute()

# After subscription expiration:
balance = CreditLedger(supabase).balance(UUID(user_id))
new_tier_id = TIER_ID_CREDIT_HOLDER if balance > 0 else TIER_ID_TRIAL
supabase.table("users").update({"tier_id": new_tier_id}).eq("id", user_id).execute()
```

### Tier Constants (app/constants/tiers.py)

```python
TRIAL: str = "TRIAL"
CREDIT_HOLDER: str = "CREDIT_HOLDER"
PREMIUM: str = "PREMIUM"

# Fixed UUIDs matching 0004_seed_tiers.sql
TIER_ID_TRIAL: str = "a0000000-0000-0000-0000-000000000001"
TIER_ID_CREDIT_HOLDER: str = "a0000000-0000-0000-0000-000000000002"
TIER_ID_PREMIUM: str = "a0000000-0000-0000-0000-000000000003"
```

### Config (app/config.py) -- Already Exists

```python
STRIPE_API_KEY: str = ""
STRIPE_WEBHOOK_SECRET: str = ""
ADAPTER__PAYMENT_ADAPTER: str = "mock"
```

### Error Response Format

Standard error response pattern established in prior stories:

```python
raise HTTPException(
    status_code=401,
    detail={"error": {"code": "INVALID_WEBHOOK_SIGNATURE", "message": "..."}},
)
```

## Verified Interfaces

### EntitlementService.get_entitlement (app/entitlement/service.py)

- **Source:** `app/entitlement/service.py:76-134`
- **Signature:** `async def get_entitlement(self, user_id: UUID) -> EntitlementState`
- **Plan match:** Matches plan contract

### EntitlementService.__init__ (app/entitlement/service.py)

- **Source:** `app/entitlement/service.py:61-70`
- **Signature:** `def __init__(self, supabase: Client, redis_client: aioredis.Redis) -> None`
- **Plan match:** Matches

### CreditLedger.balance (app/entitlement/ledger.py)

- **Source:** `app/entitlement/ledger.py:33-50`
- **Signature:** `def balance(self, user_id: UUID) -> int`
- **Plan match:** Matches plan contract

### CreditLedger.__init__ (app/entitlement/ledger.py)

- **Source:** `app/entitlement/ledger.py:30-31`
- **Signature:** `def __init__(self, supabase: Client) -> None`
- **Plan match:** Matches

### TierRecord (app/entitlement/models.py)

- **Source:** `app/entitlement/models.py:19-38`
- **Signature:** `@dataclass(frozen=True) class TierRecord` with fields: id, slug, display_name, is_default, is_active, generation_type, generation_limit, generation_period_seconds, advisor_nudges_type, advisor_nudges_limit, advisor_nudges_period_seconds, max_concurrent_generations, identity_similarity_threshold, feature_advisor_chat, feature_visual_comparison, credits_based
- **Plan match:** MISMATCH -- TierRecord is missing `stripe_price_id: str | None`. DB column exists in migration 0002 (`stripe_price_id TEXT`). This story adds it.

### TierRepository._row_to_tier (app/entitlement/tier_repo.py)

- **Source:** `app/entitlement/tier_repo.py:23-42`
- **Signature:** `def _row_to_tier(row: dict) -> TierRecord`
- **Plan match:** MISMATCH -- does not include `stripe_price_id` in mapping. This story adds it.

### TierRepository._tier_to_cache (app/entitlement/tier_repo.py)

- **Source:** `app/entitlement/tier_repo.py:45-64`
- **Signature:** `def _tier_to_cache(tier: TierRecord) -> str`
- **Plan match:** MISMATCH -- does not include `stripe_price_id` in serialization. This story adds it.

### get_current_user (app/api/deps.py)

- **Source:** `app/api/deps.py:41-58`
- **Signature:** `def get_current_user(authorization: Annotated[str | None, Header()] = None, supabase: Client = Depends(get_supabase)) -> UserClaims`
- **Plan match:** Matches -- Amended by A-8

### get_supabase (app/api/deps.py)

- **Source:** `app/api/deps.py:26-28`
- **Signature:** `def get_supabase(request: Request) -> Client`
- **Plan match:** Matches

### get_redis (app/api/deps.py)

- **Source:** `app/api/deps.py:31-33`
- **Signature:** `def get_redis(request: Request) -> aioredis.Redis`
- **Plan match:** Matches

### get_entitlement_service (app/api/deps.py)

- **Source:** `app/api/deps.py:66-75`
- **Signature:** `def get_entitlement_service(request: Request) -> EntitlementService`
- **Plan match:** Matches

### UserClaims (app/api/middleware/auth.py)

- **Source:** `app/api/middleware/auth.py:22-35`
- **Signature:** `class UserClaims(TypedDict, total=False)` with `sub: Required[str]`, `exp: Required[int]`
- **Plan match:** Matches -- Amended by A-8

### Settings (app/config.py)

- **Source:** `app/config.py:1-84`
- **Relevant fields:**
  - `STRIPE_API_KEY: str = ""` (line 26)
  - `STRIPE_WEBHOOK_SECRET: str = ""` (line 27)
  - `ADAPTER__PAYMENT_ADAPTER: str = "mock"` (line 35)
- **Plan match:** Matches

### create_app / lifespan (app/main.py)

- **Source:** `app/main.py:74-102` / `app/main.py:24-71`
- **Signature:** `def create_app() -> FastAPI` / `async def lifespan(app: FastAPI) -> AsyncIterator[None]`
- **Plan match:** Matches -- v1 APIRouter prefix pattern established, ARQ pool already initialized

### Existing entitlement router (app/api/entitlement.py)

- **Source:** `app/api/entitlement.py:1-51`
- **Current routes:** `GET /entitlement` only
- **This story adds:** `POST /credits/purchase`, `POST /subscriptions`, `DELETE /subscriptions`
- **Imports:** `_SLUG_TO_TIER_NAME` mapping available for tier name resolution

### PaymentPort (app/payment/ports.py)

- **Source:** Does not exist yet
- **Signature:** UNVERIFIED -- source not yet implemented, using expanded A-3 contract:
  - `async def create_checkout_session(self, user_id: str, price_id: str, mode: str, success_url: str, cancel_url: str) -> str`
  - `async def cancel_subscription(self, subscription_id: str) -> None`
  - `def construct_webhook_event(self, payload: bytes, sig_header: str) -> dict`

## Tasks

- [ ] Task 1: Add `stripe_price_id` to TierRecord and update TierRepository
  - Maps to: AC-1 (checkout session needs price_id from tier), AC-3 (subscription tier lookup)
  - Files: `app/entitlement/models.py`, `app/entitlement/tier_repo.py`

- [ ] Task 2: Create PaymentPort protocol and adapters
  - Maps to: AC-1 (adapter creates checkout session), AC-4 (signature verification in adapter)
  - Files: `app/payment/__init__.py`, `app/payment/ports.py`, `app/payment/adapters/__init__.py`, `app/payment/adapters/stripe_adapter.py`, `app/payment/adapters/mock.py`

- [ ] Task 3: Create webhook endpoint -- POST /webhooks/stripe
  - Maps to: AC-2 (idempotency), AC-3 (subscription.deleted handling + tier recomputation), AC-4 (signature verification), AC-5 (billing_period_end enforcement)
  - Files: `app/api/webhooks.py`, `app/main.py`

- [ ] Task 4: Create payment endpoints -- POST /credits/purchase, POST /subscriptions, DELETE /subscriptions
  - Maps to: AC-1 (checkout session creation), AC-5 (subscription cancellation with cancel_at_period_end)
  - Files: `app/api/entitlement.py`

- [ ] Task 5: Add `stripe` to requirements.txt
  - Maps to: AC-1 (Stripe SDK dependency)
  - Files: `requirements.txt`

## must_haves

truths:
  - "POST /v1/credits/purchase with authenticated user returns HTTP 200 with JSON containing checkout_url pointing to Stripe"
  - "POST /v1/credits/purchase never receives, transmits, or stores PAN, CVV, or card expiry -- all card data stays within Stripe Payment Sheet"
  - "POST /webhooks/stripe with valid stripe-signature and checkout.session.completed event inserts into processed_webhook_events(provider='stripe', event_id=evt_xxx) and returns HTTP 200"
  - "POST /webhooks/stripe with the same event_id delivered twice returns HTTP 200 on second delivery without re-processing"
  - "POST /webhooks/stripe without valid stripe-signature header returns HTTP 401"
  - "POST /webhooks/stripe with customer.subscription.deleted event sets subscriptions.status='expired' and updates users.tier_id based on credit_balance"
  - "POST /webhooks/stripe with customer.subscription.deleted for user with credit_balance > 0 sets users.tier_id to TIER_ID_CREDIT_HOLDER"
  - "POST /webhooks/stripe with customer.subscription.deleted for user with credit_balance = 0 sets users.tier_id to TIER_ID_TRIAL"
  - "POST /v1/subscriptions with authenticated user returns HTTP 200 with checkout_url for subscription checkout"
  - "DELETE /v1/subscriptions with authenticated user who has active subscription cancels at period end and returns HTTP 200"
  - "POST /webhooks/stripe with checkout.session.completed mode=payment grants credits to user via credit_ledger entry with type='purchase'"
  - "POST /webhooks/stripe with customer.subscription.updated and cancel_at_period_end=true sets subscriptions.cancelled_at timestamp"
  - "Premium access continues until billing_period_end after cancellation -- EntitlementService.get_entitlement returns has_active_subscription=True until period ends"

artifacts:
  - path: "app/payment/__init__.py"
  - path: "app/payment/ports.py"
    contains: ["PaymentPort", "Protocol", "create_checkout_session", "cancel_subscription", "construct_webhook_event"]
  - path: "app/payment/adapters/__init__.py"
  - path: "app/payment/adapters/stripe_adapter.py"
    contains: ["StripePaymentAdapter", "stripe", "construct_event", "create_checkout_session", "cancel_subscription"]
  - path: "app/payment/adapters/mock.py"
    contains: ["MockPaymentAdapter", "create_checkout_session"]
  - path: "app/api/webhooks.py"
    contains: ["router", "APIRouter", "webhooks", "stripe", "processed_webhook_events", "checkout.session.completed", "customer.subscription.deleted", "customer.subscription.updated", "invoice.payment_failed"]
  - path: "app/api/entitlement.py"
    contains: ["credits/purchase", "subscriptions", "PaymentPort"]
  - path: "app/entitlement/models.py"
    contains: ["TierRecord", "stripe_price_id"]
  - path: "app/entitlement/tier_repo.py"
    contains: ["stripe_price_id"]
  - path: "requirements.txt"
    contains: ["stripe"]

key_links:
  - pattern: "from app.payment.ports import PaymentPort"
    in: ["app/api/webhooks.py", "app/api/entitlement.py"]
  - pattern: "from app.payment.adapters.stripe_adapter import StripePaymentAdapter"
    in: ["app/api/webhooks.py", "app/api/entitlement.py"]
  - pattern: "from app.entitlement.ledger import CreditLedger"
    in: ["app/api/webhooks.py"]
  - pattern: "from app.constants.tiers import"
    in: ["app/api/webhooks.py"]
  - pattern: "processed_webhook_events"
    in: ["app/api/webhooks.py"]
  - pattern: "stripe-signature"
    in: ["app/api/webhooks.py"]
  - pattern: "webhooks.router"
    in: ["app/main.py"]
  - pattern: "stripe_price_id"
    in: ["app/entitlement/models.py", "app/entitlement/tier_repo.py"]
  - pattern: "stripe=="
    in: ["requirements.txt"]

## Dev Notes

### Testing Approach

Zero automated tests per QA skill decision. Manual testing via Stripe CLI test mode:

```bash
# Start Stripe webhook forwarding (separate terminal)
stripe listen --forward-to localhost:8000/webhooks/stripe
# Copy the webhook signing secret (whsec_*) to STRIPE_WEBHOOK_SECRET in .env

# Test credit purchase flow
curl -X POST http://localhost:8000/v1/credits/purchase \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{"credit_pack_id": "10_credits"}'
# Open the checkout_url in a browser, use test card 4242424242424242

# Test subscription flow
curl -X POST http://localhost:8000/v1/subscriptions \
  -H "Authorization: Bearer <jwt>"
# Open checkout_url, complete payment

# Trigger specific webhook events manually
stripe trigger checkout.session.completed
stripe trigger customer.subscription.deleted

# Test idempotency: replay the same event
stripe events resend evt_xxx

# Test invalid signature
curl -X POST http://localhost:8000/webhooks/stripe \
  -H "Content-Type: application/json" \
  -H "stripe-signature: invalid" \
  -d '{}'
# Expect: HTTP 401

# Verify tier transition after subscription deletion
curl http://localhost:8000/v1/entitlement \
  -H "Authorization: Bearer <jwt>"
# Expect: tier changes based on credit_balance

# Test cancel at period end
curl -X DELETE http://localhost:8000/v1/subscriptions \
  -H "Authorization: Bearer <jwt>"
# Verify cancelled_at is set, but subscription is still active until billing_period_end
```

### Conventions from Prior Stories

**Story 1-1 established:**
- `from app.config import settings` is the canonical config import pattern
- All SQL: `snake_case` table and column names; `TIMESTAMPTZ` for all timestamps
- Tier constants at `app/constants/tiers.py` with fixed UUIDs (`TIER_ID_TRIAL`, `TIER_ID_CREDIT_HOLDER`, `TIER_ID_PREMIUM`)

**Story 2-2 established:**
- `from app.api.deps import get_current_user, get_supabase` is the canonical dependency import
- `UserClaims` TypedDict with `sub: Required[str]` (Amended by A-8)
- Error responses use `raise HTTPException(status_code=..., detail={"error": {"code": "...", "message": "..."}})` pattern
- Supabase client from `request.app.state.supabase` via `get_supabase` dependency
- Logging: `logger = logging.getLogger(__name__)` at module top
- Router: `router = APIRouter(tags=["..."])`
- Request/Response models as Pydantic `BaseModel` subclasses

**Story 4-1 established:**
- `EntitlementService(supabase, redis_client)` constructor
- `CreditLedger(supabase)` constructor
- Supabase `Client` methods are synchronous; `async def` handlers are fine
- Redis calls via `redis.asyncio` are truly async

**Story 4-2 established:**
- Adapter pattern: `ports.py` for Protocol, `adapters/` directory for implementations
- Port classes use `Protocol` from `typing`
- Adapters lazy-import SDKs in `__init__` to avoid dependency when using mocks
- Example: `FalAiAdapter.__init__` imports `fal_client` lazily

**Story 4-3 established:**
- `_SLUG_TO_TIER_NAME` mapping in `app/api/entitlement.py` for public tier names
- Error code constants as module-level strings

### Stripe SDK Usage Patterns

The Stripe Python SDK (v14.x) uses module-level configuration:

```python
import stripe
stripe.api_key = settings.STRIPE_API_KEY
```

Key API calls for this story:

```python
# Webhook signature verification
event = stripe.Webhook.construct_event(
    payload=raw_body,
    sig_header=stripe_signature,
    secret=settings.STRIPE_WEBHOOK_SECRET,
)

# Create checkout session (credit purchase)
session = stripe.checkout.Session.create(
    customer=stripe_customer_id,  # or customer_email for new customers
    line_items=[{"price": price_id, "quantity": 1}],
    mode="payment",
    success_url=success_url,
    cancel_url=cancel_url,
    metadata={"user_id": user_id, "type": "credit_purchase", "credits": str(credit_count)},
)

# Create checkout session (subscription)
session = stripe.checkout.Session.create(
    customer=stripe_customer_id,
    line_items=[{"price": tier.stripe_price_id, "quantity": 1}],
    mode="subscription",
    success_url=success_url,
    cancel_url=cancel_url,
    metadata={"user_id": user_id, "type": "subscription"},
)

# Cancel subscription at period end
stripe.Subscription.modify(
    subscription_id,
    cancel_at_period_end=True,
)
```

**IMPORTANT:** The webhook handler must read the raw request body (`await request.body()`) BEFORE any JSON parsing. Stripe signature verification requires the raw bytes, not parsed JSON.

### Webhook Endpoint -- No Auth Middleware

The `POST /webhooks/stripe` endpoint must NOT use `get_current_user` or JWT auth. It authenticates via `stripe-signature` header verification instead. Register it outside the v1 prefix (directly on app) or as a separate router.

Per the architecture router table, webhooks are at `POST /webhooks/stripe` (no `/v1` prefix).

### Credit Grant via Webhook

When `checkout.session.completed` fires for a credit purchase, the webhook handler must:

1. Extract `credits` count from `session.metadata["credits"]`
2. Extract `user_id` from `session.metadata["user_id"]`
3. Insert into `credit_ledger`: `type='purchase'`, `delta=+credits`, `note` with Stripe event ID
4. If user current tier is free, update `users.tier_id` to `TIER_ID_CREDIT_HOLDER`

Use direct Supabase INSERT for credit_ledger (not CreditLedger.reserve/commit -- that lifecycle is for generation reservations). The credit_ledger table accepts `type='purchase'` entries with positive delta.

### Adapter Selection at Runtime

Create a `get_payment_adapter()` dependency in `app/api/deps.py` that reads `settings.ADAPTER__PAYMENT_ADAPTER` and returns the appropriate adapter. Follow the pattern of `get_entitlement_service`:

```python
def get_payment_adapter() -> "PaymentPort":
    if settings.ADAPTER__PAYMENT_ADAPTER == "stripe":
        from app.payment.adapters.stripe_adapter import StripePaymentAdapter
        return StripePaymentAdapter()
    from app.payment.adapters.mock import MockPaymentAdapter
    return MockPaymentAdapter()
```

### Local Dev Environment

```bash
supabase start           # Local Supabase (DB + Auth + Storage)
docker compose up -d     # Redis
./scripts/dev-start.sh   # API (hot-reload)

# Stripe webhook forwarding (separate terminal)
stripe listen --forward-to localhost:8000/webhooks/stripe
```

Environment variables for this story:
- `STRIPE_API_KEY` -- Stripe secret key (`sk_test_*` for test mode)
- `STRIPE_WEBHOOK_SECRET` -- from `stripe listen` output (`whsec_*`)
- `ADAPTER__PAYMENT_ADAPTER` -- `"stripe"` for real Stripe, `"mock"` for mock (default)

### Library Versions

- **stripe:** 14.4.0 (verified 2026-03-17 via PyPI -- latest stable)
- **FastAPI:** 0.115.12 (pinned in requirements.txt)
- **supabase-py:** 2.15.1 (pinned in requirements.txt)
- **redis-py:** 5.2.1 (pinned in requirements.txt)
- **pydantic-settings:** 2.9.1 (pinned in requirements.txt)

## Wave Structure

Wave 1: [Task 1, Task 2, Task 5] -- independent: TierRecord update (`app/entitlement/models.py`, `app/entitlement/tier_repo.py`), adapter creation (`app/payment/`), requirements.txt update. No shared files.
Wave 2: [Task 3, Task 4] -- depend on Task 2 (PaymentPort) and Task 1 (stripe_price_id). Task 3 creates `app/api/webhooks.py` + modifies `app/main.py`. Task 4 modifies `app/api/entitlement.py`. No shared files between Task 3 and Task 4.
