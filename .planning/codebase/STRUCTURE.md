# Codebase Structure

**Analysis Date:** 2026-03-17

## Directory Layout

```
nxme.ai/
├── app/                          # FastAPI backend (Python)
│   ├── api/                      # HTTP routers
│   │   ├── advisor.py            # Advisor chat endpoints
│   │   ├── analyses.py           # Face analysis endpoints
│   │   ├── auth.py               # Register, login, logout, account deletion
│   │   ├── entitlement.py        # Tier info, checkout, usage endpoints
│   │   ├── generation.py         # Generate, poll job, cancel
│   │   ├── health.py             # Liveness/readiness probes
│   │   ├── posts.py              # Post CRUD, feed, likes, comments
│   │   ├── public.py             # Public endpoints (card embeds, guest analysis)
│   │   ├── social.py             # Follow, followers, blocks
│   │   ├── users.py              # Profile, avatar, username update
│   │   ├── webhooks.py           # Stripe, Supabase auth webhooks
│   │   ├── deps.py               # Dependency injection (supabase, redis, auth, entitlement)
│   │   └── middleware/           # Auth middleware
│   │       └── auth.py           # JWT validation
│   ├── advisor/                  # Advisor service (pluggable)
│   │   ├── service.py            # Message processing, conversation mgmt
│   │   ├── memory_manager.py     # SOUL.md memory system
│   │   ├── nudge_scheduler.py    # Milestone nudges
│   │   ├── context_builder.py    # Assemble context from memories
│   │   ├── content_filter.py     # Filter inappropriate messages
│   │   ├── models.py             # Message, conversation, memory data models
│   │   ├── llm_port.py           # LLM interface contract
│   │   ├── adapters/             # Pluggable LLM adapters
│   │   │   ├── anthropic_adapter.py  # Real: Anthropic Claude
│   │   │   └── mock.py              # Test: MockLLMAdapter
│   │   └── SOUL.md               # Memory architecture docs
│   ├── generation/               # Image generation pipeline
│   │   ├── worker.py             # ARQ job handler (main generation flow)
│   │   ├── models.py             # Job, generation, identity check data classes
│   │   ├── ports.py              # GlowUpGeneratorPort interface
│   │   ├── prompt_builder.py     # Build generation prompt from analysis
│   │   ├── cost_tracker.py       # Cost calculation, circuit breaker
│   │   ├── identity_checker.py   # ArcFace similarity check
│   │   ├── face_cropper.py       # Crop + composite generated face into body
│   │   ├── color_normalizer.py   # Normalize generated image colors
│   │   ├── worker_settings.py    # ARQ configuration
│   │   ├── modules/              # Pluggable generation modules (styling, teeth, eyes)
│   │   │   ├── styling/
│   │   │   ├── teeth/
│   │   │   └── eyes/
│   │   └── adapters/             # Pluggable image generation adapters
│   │       ├── falai.py          # Real: fal.ai (Flux PuLID + fallbacks)
│   │       └── mock.py           # Test: MockGeneratorAdapter
│   ├── entitlement/              # Tier + credit system (AC-1 through A-5)
│   │   ├── service.py            # Authoritative entitlement state machine
│   │   ├── models.py             # EntitlementState, CanGenerateResult, TierRecord
│   │   ├── ledger.py             # Credit ledger CRUD (immutable log)
│   │   ├── tier_repo.py          # Tier configuration repository
│   │   ├── usage_repo.py         # Usage events repository (read-only)
│   │   └── trial_grantor.py      # Award trial analyses to new users
│   ├── payment/                  # Payment processing (pluggable)
│   │   ├── ports.py              # PaymentPort interface
│   │   └── adapters/             # Pluggable payment adapters
│   │       ├── stripe_adapter.py # Real: Stripe checkout + events
│   │       └── mock.py           # Test: MockPaymentAdapter
│   ├── face_analysis/            # Face detection & analysis (pluggable)
│   │   ├── landmark_extractor.py # MediaPipe FaceMesh model loader
│   │   ├── models.py             # FaceAnalysisResult data class
│   │   └── adapters/             # Pluggable face analysis adapters
│   │       ├── rekognition.py    # Real: AWS Rekognition
│   │       ├── mediapipe.py      # Alternative: MediaPipe (local)
│   │       └── mock.py           # Test: MockFaceAnalysisAdapter
│   ├── image_pipeline/           # Image screening & validation (pluggable)
│   │   ├── nsfw_screen.py        # NSFW detection port + adapters
│   │   └── adapters/             # Pluggable NSFW adapters
│   │       ├── rekognition.py    # Real: AWS Rekognition ModerationLabels
│   │       └── mock.py           # Test: MockNSFWAdapter
│   ├── db/                       # Database client factory
│   │   └── client.py             # get_supabase_service() — service-role authenticated
│   ├── config/                   # Configuration (seed-only, never runtime imports)
│   │   ├── tiers.py              # Tier definitions (SEED_TIERS)
│   │   └── pipelines.py          # Generation pipeline configs
│   ├── constants/                # Enum definitions
│   │   └── tiers.py              # TRIAL, CREDIT_HOLDER, PREMIUM tier names
│   ├── services/                 # Shared utilities
│   │   ├── rate_limiter.py       # Redis-backed rate limiting (registration, login)
│   │   ├── disposable_email.py   # Disposable email validation
│   │   ├── public_url.py         # Generate public CDN URLs for storage
│   │   └── limits.py             # LimitType enum
│   ├── migrations/               # Database schema (SQL)
│   │   ├── 0001_initial.sql      # 13 core tables (users, analyses, glow_up_jobs, etc.)
│   │   ├── 0002_tiers.sql        # Tiers table + tier_id FK to users
│   │   ├── 0003_usage_events.sql # Usage tracking table
│   │   ├── 0004_seed_tiers.sql   # Seed TRIAL, CREDIT_HOLDER, PREMIUM
│   │   ├── 0005_username_reserved_until.sql  # Soft delete username reservation
│   │   ├── 0006_glow_up_jobs.sql # Glow up jobs refinement (if needed)
│   │   ├── 0007_advisor_tables.sql  # Advisor conversations + memories
│   │   └── run.py                # Migration runner (executed during deploy)
│   ├── main.py                   # FastAPI app factory + lifespan
│   ├── config.py                 # Settings singleton (pydantic-settings)
│   ├── worker_settings.py        # ARQ worker settings (queue lanes, functions)
│   └── __init__.py
├── mobile/                       # React Native frontend (Expo)
│   ├── app/                      # Expo Router app directory
│   │   ├── _layout.tsx           # Root layout (auth gate, top-level nav)
│   │   ├── (auth)/               # Auth group (login, register, onboarding)
│   │   │   └── login.tsx
│   │   ├── (tabs)/               # Main app (tab-based nav)
│   │   │   ├── feed.tsx          # Timeline / feed
│   │   │   ├── profile.tsx       # User profile
│   │   │   ├── advisor.tsx       # Advisor chat UI (if enabled)
│   │   │   └── explore.tsx
│   │   ├── upload.tsx            # Selfie upload + analysis
│   │   ├── result.tsx            # Generation result viewer
│   │   ├── advisor/              # Advisor feature screens
│   │   │   └── [id].tsx
│   │   ├── card/                 # Post/card viewer
│   │   │   └── [id].tsx
│   │   └── onboarding.tsx        # First-run UX
│   ├── components/               # Reusable React Native components
│   │   ├── auth/                 # Login, register components
│   │   ├── upload/               # Image picker, selfie capture
│   │   ├── result/               # Generation result cards
│   │   ├── feed/                 # Feed items, posts
│   │   ├── advisor/              # Chat, message bubble components
│   │   ├── profile/              # Profile UI
│   │   ├── paywall/              # Credit purchase UI
│   │   ├── comments/             # Comment thread UI
│   │   └── ...
│   ├── lib/                      # TypeScript utilities
│   │   ├── api.ts                # HTTP client (fetch wrapper, base URL)
│   │   ├── auth.ts               # Auth token storage (secure)
│   │   ├── analysis.ts           # Analysis operations (upload, poll)
│   │   ├── advisor.ts            # Advisor API calls
│   │   ├── entitlement.ts        # Check tier, fetch pricing
│   │   ├── guest-session.ts      # Temporary guest session mgmt
│   │   ├── notifications.ts      # Push notification handling
│   │   └── deep-link-guard.ts    # Universal link security
│   ├── constants/                # Constants (API_BASE_URL, etc.)
│   ├── package.json              # Expo dependencies (React 19.2, expo 55)
│   ├── app.json                  # Expo config
│   ├── tsconfig.json
│   └── babel.config.js
├── card-web/                     # Next.js web frontend (shareable cards)
│   ├── src/
│   │   ├── app/                  # Next.js app router
│   │   │   ├── page.tsx          # Home / intro
│   │   │   ├── card/
│   │   │   │   └── [id]/page.tsx # Shareable card view
│   │   │   └── layout.tsx        # Root layout
│   │   ├── components/           # React components
│   │   │   ├── CardViewer.tsx    # Card display
│   │   │   └── ...
│   │   ├── lib/                  # Utilities
│   │   │   ├── api.ts            # Backend API calls
│   │   │   ├── auth.ts           # Auth helpers
│   │   │   └── ...
│   │   └── config/               # Config files
│   ├── package.json              # Next.js 14.2, React 18.3, Tailwind
│   ├── tailwind.config.ts        # Tailwind CSS
│   ├── tsconfig.json
│   └── next.config.mjs           # Next.js config (MJS, not TS)
├── prompts/                      # LLM prompt templates (loaded at runtime)
│   ├── generation/               # Generation prompts
│   │   ├── styling_prompt.txt
│   │   ├── teeth_prompt.txt
│   │   └── eyes_prompt.txt
│   ├── advisor/                  # Advisor prompts
│   │   ├── system_prompt.txt
│   │   ├── context_prompt.txt
│   │   └── nudge_prompt.txt
│   └── ...
├── scripts/                      # Utility scripts
│   ├── seed_tiers.py             # (Alternative) tier seeding
│   ├── export_schema.py          # Export Supabase schema
│   └── ...
├── tests/                        # Python tests
│   ├── test_credit_ledger_invariants.py  # Ledger integrity tests
│   └── ...
├── docs/                         # Documentation
│   ├── generation-spec.md        # Generation module spec (17 sections)
│   ├── advisor-spec.md           # Advisor module spec (17 sections)
│   ├── design-system.md          # UI components, Figma mapping
│   ├── local-dev.md              # Local dev setup + env vars
│   ├── amendments.md             # A-1 through A-5 architectural decisions
│   ├── adr/                      # Architecture Decision Records
│   ├── stories/                  # Story tasks
│   └── reviews/                  # Code review comments
├── app.json                      # Monorepo config (workspaces for mobile, card-web)
├── requirements.txt              # Python dependencies
├── requirements-dev.txt          # Dev-only dependencies
├── docker-compose.yml            # Local Supabase + Redis
├── Dockerfile                    # Production API container
├── .env.example                  # Environment variable template
├── main.py                       # Entry point (if running bare python)
└── .planning/                    # GSD planning artifacts (this file lives here)
    └── codebase/                 # Codebase analysis docs
        ├── ARCHITECTURE.md
        ├── STRUCTURE.md
        ├── CONVENTIONS.md        # (Generated by quality focus)
        ├── TESTING.md            # (Generated by quality focus)
        ├── STACK.md              # (Generated by tech focus)
        ├── INTEGRATIONS.md       # (Generated by tech focus)
        └── CONCERNS.md           # (Generated by concerns focus)
```

## Directory Purposes

**app/api/:**
- **Purpose:** All HTTP request handlers, organized by feature (auth, generation, posts, etc.)
- **Contains:** FastAPI routers, Pydantic request/response schemas, HTTP status codes
- **Key files:** `deps.py` (dependency injection), `middleware/auth.py` (JWT validation)

**app/entitlement/:**
- **Purpose:** Single module authorizing all credit/tier/subscription decisions
- **Contains:** EntitlementService (state machine), CreditLedger (transaction log), TierRepository (tier configs), UsageRepository (usage_events)
- **Contract:** Never read credit_ledger directly from handlers; always route through EntitlementService

**app/generation/:**
- **Purpose:** Full image generation pipeline (enqueue → process → verify → commit)
- **Contains:** Worker (ARQ job handler), adapters (FalAiAdapter, MockGeneratorAdapter), pipeline steps (prompt, identity, cost)
- **Key files:** `worker.py` (main loop), `ports.py` (generator interface), `identity_checker.py` (ArcFace), `models.py` (JobStatus, GenerationOptions)

**app/advisor/:**
- **Purpose:** Pluggable advisor module (conversation, memory, nudges, LLM)
- **Contains:** AdvisorService, MemoryManager, NudgeScheduler, LLM adapters, content filter
- **Pluggable:** Entire module disabled if ADVISOR_ENABLED=False; LLM adapter selected via config

**app/payment/:**
- **Purpose:** Pluggable payment processing (Stripe checkout, webhook handling)
- **Contains:** PaymentPort interface, StripePaymentAdapter, MockPaymentAdapter
- **Responsibility:** Create checkout sessions, handle subscription updates on webhook

**app/face_analysis/ and app/image_pipeline/:**
- **Purpose:** Pluggable screening adapters (face detection, NSFW detection)
- **Adapters:** MediaPipe/Rekognition for face analysis, Rekognition/mock for NSFW
- **Usage:** Called during analysis creation and generation processing

**mobile/:**
- **Purpose:** React Native frontend (iOS, Android, web via Expo)
- **Structure:** Expo Router app directory, tab-based UI, screens for upload/result/advisor
- **API client:** `lib/api.ts` wrapper, feature-specific libs (analysis.ts, advisor.ts, entitlement.ts)

**card-web/:**
- **Purpose:** Next.js web frontend (shareable post cards, embedded viewer)
- **Tech:** Next.js 14.2, React 18.3, Tailwind, no auth required
- **Entry:** `src/app/page.tsx` (home), `src/app/card/[id]/page.tsx` (card viewer)

**app/migrations/:**
- **Purpose:** Database schema versioning (Supabase SQL)
- **Naming:** `YYYYMMDDHHMMSS_description.sql` (only if versioning; current: `00NN_`)
- **Pattern:** Each migration has UP (apply) and DOWN (rollback) sections
- **Execution:** `run.py` executes sequentially on deploy; idempotent guards (IF NOT EXISTS)

**prompts/:**
- **Purpose:** Centralized LLM prompt templates (loaded at runtime, never inlined in code)
- **Structure:** Subdirs by module (generation/, advisor/)
- **Usage:** Loaded as strings in prompt_builder.py, context_builder.py, etc.

## Key File Locations

**Entry Points:**
- `app/main.py`: FastAPI factory function `create_app()` → lifespan, routers, middleware
- `app/generation/worker.py`: ARQ worker entrypoint → `process_generation_job(ctx, job_id)`, `watchdog_stuck_jobs(ctx)`
- `mobile/app/_layout.tsx`: Expo Router root (navigation, auth gate)
- `card-web/src/app/layout.tsx`: Next.js root layout

**Configuration:**
- `app/config.py`: Settings singleton (pydantic-settings, loads from .env)
- `app/config/tiers.py`: Tier seed definitions (used during migration 0004, never imported at runtime)
- `app/constants/tiers.py`: Tier name constants (TRIAL, CREDIT_HOLDER, PREMIUM)

**Core Logic:**
- `app/entitlement/service.py`: Authoritative tier/credit state machine
- `app/generation/worker.py`: Generation lifecycle (6-step process)
- `app/advisor/service.py`: Conversation + nudge orchestration

**Database:**
- `app/migrations/0001_initial.sql`: Schema for 13 tables (users, analyses, glow_up_jobs, credit_ledger, etc.)
- `app/migrations/0004_seed_tiers.sql`: Tier seeding (TRIAL=2/day, CREDIT_HOLDER=unlimited, PREMIUM=unlimited+advisor)

**Testing:**
- `tests/test_credit_ledger_invariants.py`: Ledger transaction integrity

**Documentation:**
- `docs/generation-spec.md`: 17-section spec for generation module (prompts, models, retry, cost)
- `docs/advisor-spec.md`: 17-section spec for advisor module (memory, nudges, costs)
- `docs/amendments.md`: A-1 through A-5 architectural decisions
- `docs/local-dev.md`: Setup guide + env var table

## Naming Conventions

**Files:**
- Python services: `{service_name}.py` (e.g., `entitlement/service.py`, `advisor/service.py`)
- Adapters: `{provider_name}_adapter.py` (e.g., `falai.py`, `anthropic_adapter.py`, `stripe_adapter.py`)
- Migrations: `00NN_descriptive_name.sql` (sequence number + snake_case description)
- React components: `{Component}.tsx` (PascalCase), screens in `app/` as routes
- Utilities: `{function_area}.ts` (e.g., `lib/api.ts`, `lib/analysis.ts`)

**Directories:**
- Feature modules: `app/{feature_name}/` (plural or singular: `generation/`, `advisor/`, `entitlement/`)
- Adapters: `{module}/adapters/` (provider-specific subdirs)
- API routes: Single file per route group in `app/api/`

**Database:**
- Tables: Singular snake_case (users, analyses, glow_up_jobs, credit_ledger, advisor_memories, advisor_conversations)
- Indexes: `idx_{table}_{columns}` (e.g., `idx_users_username`, `idx_jobs_user_id`)
- ForeignKeys: `fk_{table}_{column}` (e.g., `fk_credit_reservations_job_id`)

## Where to Add New Code

**New Feature (e.g., new generation module "styling"):**
- Backend logic: `app/generation/modules/styling/` (service, prompt, params)
- Database: Extend migrations with new columns/tables (0008_styling_config.sql)
- API: New endpoints in `app/api/generation.py` or dedicated `app/api/styling.py`
- Mobile UI: New screen in `mobile/app/` or component in `mobile/components/`

**New Service (e.g., analytics):**
- Code: `app/services/analytics.py` (or `app/analytics/service.py` if substantial)
- Database: Migrations in `app/migrations/` (new table + indexes)
- API: Router in `app/api/analytics.py` mounted in `main.py`
- Tests: `tests/test_analytics.py`

**New Adapter (e.g., OpenAI as alternative to Anthropic):**
- Interface: Add to existing port (`app/advisor/llm_port.py` already exists)
- Implementation: `app/advisor/adapters/openai_adapter.py`
- Config: Add `ADAPTER__LLM_ADAPTER="openai"` option to `app/config.py`
- Selection: Update `get_llm_adapter()` in `app/api/deps.py`

**New Component (mobile):**
- File: `mobile/components/{feature}/{Component}.tsx`
- Shared utilities: `mobile/lib/{feature}.ts`
- Screens: `mobile/app/{screen}.tsx` (or directory if complex routing)

**New API Endpoint:**
- File: `app/api/{resource}.py` (if new resource) or add to existing file
- Dependencies: Declared with `Depends(get_current_user)`, `Depends(require_entitlement(...))`, etc.
- Testing: Add to `tests/` (follow `test_credit_ledger_invariants.py` pattern)

## Special Directories

**app/migrations/:**
- **Purpose:** Database schema version control
- **Generated:** No (hand-written SQL)
- **Committed:** Yes (all migrations checked in)
- **Execution:** `python app/migrations/run.py` runs all pending migrations on app startup or deploy

**.planning/codebase/:**
- **Purpose:** GSD codebase analysis documents (this directory)
- **Generated:** Yes (written by `/gsd:map-codebase` agents)
- **Committed:** Yes
- **Usage:** Loaded by `/gsd:plan-phase` and `/gsd:execute-phase` to guide implementation

**docs/:**
- **Purpose:** Architecture, specifications, guides
- **Generated:** Partially (stories/ populated by story-creator)
- **Committed:** Yes
- **Key files:** generation-spec.md, advisor-spec.md, amendments.md, local-dev.md (PRIMARY sources for stories)

---

*Structure analysis: 2026-03-17*
