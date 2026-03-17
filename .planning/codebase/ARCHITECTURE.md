# Architecture

**Analysis Date:** 2026-03-17

## Pattern Overview

**Overall:** Layered backend (FastAPI + ARQ) with pluggable adapters, decoupled frontend (Expo mobile + Next.js web).

**Key Characteristics:**
- **Adapter-driven integrations** — All external services (fal.ai, Anthropic, Stripe, Rekognition, Supabase storage) plugged via interface contracts
- **FastAPI synchronous handlers** with async support; ARQ for background jobs
- **Entitlement as cross-cutting concern** — dependency injected via `require_entitlement()` and `require_feature()` decorators
- **Two-phase generation** — enqueue via HTTP (reserve credits, validate), process via ARQ worker (generate, verify identity, commit)
- **Feature-first structure** — advisor, generation, payment modules are self-contained with internal adapters

## Layers

**API Layer (FastAPI routers):**
- Purpose: Handle HTTP requests, enforce auth/entitlements, serialize responses
- Location: `app/api/*.py`
- Contains: Route handlers, Pydantic request/response models, HTTP status codes
- Depends on: Services, EntitlementService, adapters via dependency injection
- Used by: Mobile (Expo) and web (Next.js, card-web) clients

**Service Layer (domain logic):**
- Purpose: Business logic, transactions, validation, orchestration
- Location: `app/entitlement/service.py`, `app/advisor/service.py`, `app/generation/worker.py`
- Contains: EntitlementService (credit/tier state machine), AdvisorService (conversation + memory), GenerationWorker (async job processor)
- Depends on: Repositories, adapters, models
- Used by: API handlers, ARQ worker tasks, other services

**Adapter Layer (pluggable integrations):**
- Purpose: Encapsulate third-party APIs behind protocol contracts
- Location: `app/generation/adapters/`, `app/advisor/adapters/`, `app/payment/adapters/`, `app/face_analysis/`, `app/image_pipeline/`
- Contains: FalAiAdapter (image generation), AnthropicAdapter (LLM), StripePaymentAdapter, MockGeneratorAdapter (testing)
- Depends on: External SDK libraries
- Used by: Services, worker, other modules

**Repository Layer (data access):**
- Purpose: Isolate Supabase table queries behind focused interfaces
- Location: `app/entitlement/tier_repo.py`, `app/entitlement/usage_repo.py`, `app/entitlement/ledger.py`
- Contains: TierRepository (tier configs), UsageRepository (usage_events reads), CreditLedger (credit_ledger CRUD)
- Depends on: Supabase client
- Used by: Services

**Database Layer (Supabase):**
- Purpose: Persistent storage with RLS (multi-tenant isolation)
- Location: 13 tables defined in migrations `app/migrations/0001_initial.sql` through `0007_advisor_tables.sql`
- Contains: Users, tiers, analyses, glow_up_jobs, credit reservations/ledger, advisor conversations/memories, posts, subscriptions
- Schema: All timestamps as TIMESTAMPTZ, soft deletes via deleted_at, composites like (user_id, status) indexed per ESR rule
- Used by: Repositories, direct SQL in migrations

## Data Flow

**Registration & Trial:**

1. Mobile calls `POST /v1/auth/register` with email, password, username
2. API validates disposable email, rate limits (per IP, per device fingerprint), age gate
3. Creates user row (tier = default, trial_analyses_remaining = 0)
4. Returns email_verification_required = true if email auth enabled
5. Client triggers email verification flow
6. On email confirmed, `TrialGrantor.grant()` awards 2 trial analyses, sets trial_analyses_remaining = 2

**Analysis & Generation (2-phase):**

1. Mobile uploads selfie, API calls analysis service (Rekognition/MediaPipe adapter)
2. Analysis stored in `analyses` table with face_shape, symmetry_score, recommendations
3. Mobile calls `POST /v1/analyses/{analysis_id}/generate` → API:
   - Checks entitlement via `EntitlementService.can_generate(user_id, tier)` → CanGenerateResult (allowed, cost_usd, error)
   - Creates credit_reservations row (status='reserved', amount=1)
   - Creates glow_up_jobs row (status='pending', credit_reservation_id=FK, user_tier_at_enqueue=TRIAL/CREDIT_HOLDER/PREMIUM)
   - Enqueues ARQ job in appropriate lane (generation:trial, generation:credit, generation:premium)
   - Returns job_id, estimated_wait_seconds based on queue depth
4. Mobile polls `GET /v1/jobs/{job_id}` → status, estimated_wait, before/after URLs
5. ARQ worker processes (background):
   - Pulls job from queue, claims status=PROCESSING (conditional UPDATE on status=QUEUED)
   - Builds prompt from analysis + user preferences
   - Calls GlowUpGeneratorPort.generate() (FalAiAdapter or mock)
   - Screens output via NSFW adapter (Rekognition or mock)
   - Checks identity via ArcFace (IdentityChecker)
   - Commits: credit_reservations.status='committed', glow_up_jobs.status='COMPLETED', copies credit to credit_ledger
   - On failure: credit_reservations.status='released', glow_up_jobs.status='FAILED', failure_reason set
   - All writes wrapped in transactions (P2-6: prevent orphaned credits)

**Payment & Stripe:**

1. Mobile calls `POST /v1/entitlement/checkout` with pack_id (10, 25, 50 credits)
2. API creates Stripe checkout session (return URLs: nxme://payment/success, nxme://payment/cancel)
3. Mobile opens Stripe payment URL → user authorizes → webhook called
4. Webhook at `/webhooks/stripe` updates subscriptions + credits in credit_ledger
5. EntitlementService refreshes tier on next request (denormalized user.tier_id for fast checks)

**Advisor Chat (pluggable, disabled in non-PREMIUM):**

1. Mobile calls `POST /v1/advisor/messages` (requires feature flag check)
2. API validates feature enabled on tier via `require_feature("advisor_chat")` dependency
3. AdvisorService.process_message():
   - Loads conversation + memories (SQLite-based memory system, see `SOUL.md`)
   - Builds context: last N memories (limit = ADVISOR_CONTEXT_MEMORY_LIMIT = 3)
   - Calls LLM adapter (AnthropicAdapter.generate_response or mock)
   - Saves message + response to advisor_messages table
   - NudgeScheduler checks if milestone nudge should trigger
4. Returns response text + usage for UI display

**State Management:**

- **Synchronous state:** User, analysis, posting metadata — in Supabase rows, denormalized in user.tier_id for perf
- **Asynchronous state:** Generation job status tracked in Redis (job:{job_id}:status, job:{job_id}:queue_position)
- **Rate limiting:** Stored in Redis with TTL (registration attempts, login attempts, advisor chat frequency)
- **Transactional guarantees:** Multi-step DB operations (register + grant trial, reserve + commit credit) wrapped in explicit transactions via `conn.autocommit = False`

## Key Abstractions

**Port (Protocol Interface):**
- Purpose: Define what external service contracts must implement
- Examples: `GlowUpGeneratorPort` (`app/generation/ports.py`), `LLMPort` (`app/advisor/llm_port.py`), `PaymentPort` (`app/payment/ports.py`)
- Pattern: Python Protocol (structural typing) — adapters inherit/implement but can vary impl

**EntitlementService (AC-1, AC-2, A-5):**
- Purpose: Single authoritative module for credit/subscription/tier state
- Interface: `get_entitlement(user_id) -> EntitlementState`, `can_generate(user_id) -> CanGenerateResult`, `check(user_id, action) -> EntitlementResult`
- Invariant: credit_ledger is single source of truth; user.tier_id is denormalized cache only
- Tiers are DB-driven (tiers table, seeded at migration 0004), not hardcoded

**TierConfig (Amendment A-4):**
- Purpose: Centralized definition of per-tier limits (generation limits, advisor nudges, concurrent jobs, features)
- Location: `app/config/tiers.py` (seed only, never read at runtime)
- Read via: EntitlementService queries tiers table at startup, caches in Redis
- Example: TRIAL tier allows 2 generations/day, no advisor; PREMIUM allows unlimited + advisor

**CreditLedger (Story 4-1):**
- Purpose: Immutable log of all credit transactions (grants, reservations, commitments, releases, refunds)
- Location: `app/entitlement/ledger.py`
- Pattern: Write-only appends; EntitlementService sums balance from ledger rows
- Invariant: Every glow_up_jobs row links to exactly one credit_reservations row; every reservation resolved in ledger

**GenerationPipeline:**
- Purpose: Modular generation steps (crop, prompt build, generate, verify, score)
- Location: `app/generation/` (face_cropper.py, prompt_builder.py, identity_checker.py, cost_tracker.py, color_normalizer.py)
- Pattern: Each step is standalone function; worker orchestrates sequence
- Config: `ENABLED_TRANSFORMATION_MODULES` comma-separated string (styling, teeth, eyes)

**AdvisorService (Story 7):**
- Purpose: Conversation management + nudge scheduling
- Location: `app/advisor/service.py`
- Contains: message processing, memory manager (SOUL.md), nudge scheduler, content filter
- LLM pluggable: Anthropic (real) or mock adapter; selected via config

## Entry Points

**HTTP Server:**
- Location: `app/main.py` → `create_app()` returns FastAPI instance
- Triggers: `uvicorn app.main:app` (development) or Docker entrypoint
- Responsibilities: Wire Supabase/Redis/ARQ at startup (lifespan), mount routers, block mock adapters in production

**ARQ Worker:**
- Location: `app/generation/worker.py` → `process_generation_job(ctx, job_id)` and `watchdog_stuck_jobs(ctx)`
- Triggers: ARQ listens on Redis for enqueued jobs (lanes: generation:premium, generation:credit, generation:trial)
- Responsibilities: Process generation lifecycle, handle failures, release credits, update job status

**Mobile Frontend (Expo):**
- Location: `mobile/` (React Native, Expo Router)
- Entry: `mobile/app/_layout.tsx` → (auth) group for login/register, (tabs) for main app
- API calls via: `mobile/lib/api.ts` (base fetch wrapper), `mobile/lib/analysis.ts`, `mobile/lib/advisor.ts`

**Web Frontend (Next.js card embeds):**
- Location: `card-web/` (Next.js 14.2, shadcn/ui)
- Entry: `card-web/src/app/` (Next.js app router)
- Purpose: Embedded shareable card viewer (posts, results) — lightweight, no auth

## Error Handling

**Strategy:** Distinguish expected (entitlement, validation, external API failures) from exceptional (programmer errors, infra catastrophe).

**Patterns:**

- **Entitlement failures:** `EntitlementResult.allowed=False, error_code='TIER_LIMIT_DAILY'` → HTTP 402 (Payment Required) or 429 (Rate Limit)
- **Validation errors:** Pydantic raises `HTTPException(status_code=422)` on bad request body
- **Provider failures (generation):** FalAiAdapter raises → caught by worker, retried via circuit breaker, if max retries exceeded → job status=FAILED, credit released
- **Database errors:** Supabase transaction rollback → service-level retry with exponential backoff (not in API handlers)
- **Auth failures:** Invalid JWT → HTTP 401 (Unauthorized)

## Cross-Cutting Concerns

**Logging:** Python `logging` module, configured per-module. ARQ jobs log to stdout captured by container.

**Validation:**
- Request bodies: Pydantic BaseModel (EmailStr, Field constraints)
- Age gate: birth_year vs. MIN_AGE_YEARS = 13
- Disposable email: `is_disposable_email()` service call
- Rate limiting: Redis counters with TTL

**Authentication:**
- Bearer JWT in Authorization header (Supabase auth)
- Token validated in `middleware/auth.py` → `validate_jwt(token)` parses claims (sub=user_id, email, etc.)
- Decoded claims injected as UserClaims into handlers via `get_current_user()` dependency

**Entitlement:**
- Injected via `require_entitlement(action)` dependency → calls `EntitlementService.check(user_id, action)`
- Feature gating via `require_feature(name)` → calls `EntitlementService.has_feature(user_id, name)`
- Error codes mapped to HTTP status (402 for payment, 429 for quota)

**Multi-tenancy:**
- User isolation via `user_id` in every query predicate (analyses, posts, comments, advisor_messages, credit_ledger)
- Supabase RLS enforces tenant_id = current_user_id (not yet fully enabled — see CONCERNS.md)

**Adapters & Feature Flags:**
- Adapter selection via config: `ADAPTER__IMAGE_GENERATION_ADAPTER=falai|mock`
- Feature flags via tier: advisor_enabled on PREMIUM tier, retrieved via EntitlementService
- Module disable via config: `ADVISOR_ENABLED=True|False` gates entire advisor router mount

---

*Architecture analysis: 2026-03-17*
