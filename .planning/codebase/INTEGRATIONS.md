# External Integrations

**Analysis Date:** 2026-03-17

## APIs & External Services

**Image Generation:**
- fal.ai - AI image generation (primary and fallback models)
  - SDK/Client: `fal-client==0.13.1`
  - Auth: `FAL_API_KEY` (env var)
  - Adapter: `app/generation/adapters/falai.py` (StripePaymentAdapter)
  - Models: Flux PuLID (primary), Flux Dev img2img (fallback 1), InstantID (fallback 2)
  - Estimated cost: ~$0.035/image primary, ~$0.025/image fallbacks

**Content Moderation:**
- AWS Rekognition - NSFW content detection
  - SDK/Client: `boto3==1.42.68`
  - Auth: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` (env vars)
  - Adapter: `app/image_pipeline/nsfw_screener.py` (RekognitionAdapter)
  - Confidence threshold: 80% for explicit content quarantine
  - Timeout: <=5s (enforced in AC-3)

**Payment Processing:**
- Stripe - Credit pack purchases, subscriptions
  - SDK/Client: `stripe==14.4.1`
  - Auth: `STRIPE_API_KEY` (secret key), `STRIPE_WEBHOOK_SECRET` (signing key)
  - Adapter: `app/payment/adapters/stripe_adapter.py`
  - Checkout mode: payment (one-time) via hosted payment sheet (mobile SDK, no PCI-DSS cardholder data)
  - Subscription cancellation supported (cancel_at_period_end)
  - Webhook endpoint: `POST /webhooks/stripe` (unversioned)
  - Env vars for credit pack price IDs: `STRIPE_PRICE_CREDITS_10`, `STRIPE_PRICE_CREDITS_25`, `STRIPE_PRICE_CREDITS_50`

**LLM & Memory:**
- Anthropic Claude - Advisor chat, nudge generation, memory extraction
  - SDK/Client: `anthropic` (lazy import)
  - Auth: `ANTHROPIC_API_KEY` (env var)
  - Adapter: `app/advisor/adapters/anthropic_adapter.py` (AnthropicAdapter)
  - Models: `claude-3-5-sonnet` (chat, context assembly), `claude-3-haiku` (nudges, memory extraction)
  - Rate limit: 30 messages/hour per user (ADVISOR_CHAT_RATE_LIMIT)

**OpenAI (for embeddings only):**
- SDK/Client: `openai` (lazy import, used in AnthropicAdapter)
- Auth: `OPENAI_API_KEY` (falls back to ANTHROPIC_API_KEY slot if not set)
- Model: `text-embedding-3-small` (1536 dimensions)
- Purpose: Memory semantic search in advisor module

## Data Storage

**Databases:**
- PostgreSQL 15+ (via Supabase)
  - Connection: `SUPABASE_URL` (API endpoint), `SUPABASE_SERVICE_ROLE_KEY` (server auth)
  - Client: `supabase==2.15.1`
  - ORM: None (direct SQL via Supabase client, migrations in `app/migrations/*.sql`)
  - Tables: users, images, analyses, credit_reservations, glow_up_jobs, posts, reactions, advisor_conversations, advisor_memories, usage_events, username_reserved_until, tiers
  - RLS enabled on multi-tenant tables (users, posts, reactions, advisor_conversations, usage_events)
  - Migrations: Run on startup via `app/migrations/run.py`

**File Storage:**
- Supabase Storage - Image file persistence
  - Connection: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
  - Client: Supabase Storage API
  - Buckets:
    - `raw-selfies` (private, RLS-protected) - Upload buffer
    - `generated-images` (public, CDN) - Post images with stable URLs
  - Adapter: `app/image_pipeline/storage.py` (SupabaseStorageAdapter for production, LocalStorageAdapter for offline dev)
  - Signed URLs: `SIGNED_URL_EXPIRY_SECONDS` (default 3600s)
  - Public CDN URLs: `PUBLIC_STORAGE_BASE_URL` (override with CloudFront in production)

**Caching:**
- Redis - Rate limiting, session state, tier/entitlement cache
  - Connection: `REDIS_URL` (default: redis://localhost:6379/0)
  - Client: `redis==5.2.1` (via `redis.asyncio` for async)
  - Usage: Advisor chat rate limiting, generation concurrency tracking, entitlement cache (optional)
  - Persistent data: None (ephemeral, lost on restart)

## Authentication & Identity

**Auth Provider:**
- Supabase Auth - User registration, login, email verification, session management
  - Connection: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET`
  - Admin operations: `SUPABASE_SERVICE_ROLE_KEY`
  - Implementation:
    - JWT tokens (HS256, signed with SUPABASE_JWT_SECRET)
    - Token validation in `app/api/middleware/auth.py` (decode_supabase_jwt)
    - Middleware checks Bearer tokens on protected routes
    - Email verification workflow (POST /auth/verify-email after signup)
    - Social login (Google, GitHub) via sign_in_with_id_token
  - Guest sessions: `users.guest_session_token` for pre-auth trials

**Identity Preservation (Generation):**
- ArcFace (insightface) - Face embedding extraction for identity verification
  - Models: Pre-loaded via `app/generation/identity_checker.py`
  - Similarity threshold: `IDENTITY_SIMILARITY_THRESHOLD` (default 0.80)
  - Post-check: Compares generated image ArcFace score to original selfie
  - Retries: `IDENTITY_MAX_RETRIES` (default 1)

## Monitoring & Observability

**Error Tracking:**
- None detected - Errors logged locally via Python logging

**Logs:**
- Python logging module (stdlib)
- Log format: structured logs to stdout (Uvicorn, FastAPI auto-format)
- Destination: Docker logs / CloudWatch / ELK (depending on deployment)

**Health Checks:**
- GET `/` (unversioned) - Load balancer probes (MediaPipe pre-load status, Redis connectivity implicit in ARQ pool creation)

## CI/CD & Deployment

**Hosting:**
- Backend API: Linux container (Dockerfile provided, multi-stage)
- Mobile: Expo Cloud / TestFlight / Google Play
- Web/Card: Vercel (Next.js auto-deploy) or self-hosted

**CI Pipeline:**
- None detected in codebase (likely in GitHub Actions .github/workflows)
- Pre-commit hooks: None detected
- Tests: pytest (Python backend)

**Environment Management:**
- Adapter pattern for provider swapping without code changes
- Separate test/staging/production credentials for external services (Stripe test mode, fal.ai dev API, etc.)

## Environment Configuration

**Required env vars (no defaults):**
- `SECRET_KEY` - JWT signing key (32+ chars)
- `ADMIN_API_KEY` - Admin endpoint authorization
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_ANON_KEY` - Public anon key
- `SUPABASE_SERVICE_ROLE_KEY` - Server-side auth key
- `SUPABASE_JWT_SECRET` - JWT signing secret

**Optional env vars (with defaults or adapter-dependent):**
- `APP_ENV` (default: development)
- `REDIS_URL` (default: redis://localhost:6379/0)
- `FAL_API_KEY` (empty if ADAPTER__IMAGE_GENERATION_ADAPTER != "falai")
- `AWS_ACCESS_KEY_ID` (empty if ADAPTER__NSFW_ADAPTER != "rekognition")
- `AWS_SECRET_ACCESS_KEY` (empty if ADAPTER__NSFW_ADAPTER != "rekognition")
- `AWS_REGION` (default: us-east-1)
- `STRIPE_API_KEY` (empty if ADAPTER__PAYMENT_ADAPTER != "stripe")
- `STRIPE_WEBHOOK_SECRET` (empty if ADAPTER__PAYMENT_ADAPTER != "stripe")
- `ANTHROPIC_API_KEY` (empty if ADVISOR_ENABLED=False or ADAPTER__LLM_ADAPTER != "anthropic")
- `OPENAI_API_KEY` (optional, falls back to ANTHROPIC_API_KEY for embeddings)
- `ADVISOR_ENABLED` (default: True)
- `ADVISOR_PERSONA_NAME` (default: Ada)
- `PUBLIC_STORAGE_BASE_URL` (empty = use default Supabase URL)
- `ADAPTER__*_ADAPTER` (all default to "mock" except STORAGE which defaults to "supabase")

**Secrets location:**
- `.env` file (never committed, blocked by .gitignore)
- In production: Environment variables from container orchestration (Kubernetes secrets, Heroku config vars, etc.)

## Webhooks & Callbacks

**Incoming Webhooks:**
- Stripe payment events: `POST /webhooks/stripe` (unversioned endpoint)
  - Signature verification via Stripe webhook secret
  - Events: `charge.succeeded`, `subscription_schedule.updated`, etc. (implied by code)
  - Handler: `app/api/webhooks.py`

**Outgoing Webhooks:**
- None detected (internal async jobs via ARQ, not external webhooks)

**Async Job Queue:**
- ARQ (Redis-backed) - Generation jobs, advisor nudges, reaction reconciliation
  - Connection: Redis via `REDIS_URL`
  - Worker: `app/worker_settings.py` (separate process: `arq app.worker_settings.WorkerSettings`)
  - Jobs:
    - `process_generation_job` - Flux/InstantID image generation (priority lanes)
    - `persist_reaction` - Post reactions (emoji, likes)
    - `schedule_post_analysis_nudge` - Schedule nudge after analysis
    - `generate_nudge` - Generate personalized nudge via Claude
    - `check_nudge_eligibility` - Daily cron (06:00 UTC)
    - `reconcile_reaction_counts` - Nightly cron (03:00 UTC)
    - `watchdog_stuck_jobs` - Minute-level cron for stalled job recovery
  - Lanes: `HIGH`, `MEDIUM`, `LOW`, `default` (in `app/generation/models.py`)
  - Job timeout: `GENERATION_TIMEOUT_SECONDS` (default 60s)

## Rate Limiting

**API Rate Limiting:**
- Registration: `REGISTRATION_FINGERPRINT_LIMIT` (3 attempts/device/24h), `REGISTRATION_IP_LIMIT` (4 attempts/IP/1h)
- Advisor chat: `ADVISOR_CHAT_RATE_LIMIT` (30 messages/hour per user)
- Enforcement: Redis-backed counters with TTL

## Data Privacy & Security

**Row-Level Security:**
- RLS enabled on all multi-tenant tables (users, posts, reactions, advisor_conversations, advisor_memories, usage_events)
- Tenant context: `app.tenant_id` setting (middleware injects current user_id)
- Policies: prevent cross-tenant data access

**Image Metadata Stripping:**
- EXIF/metadata removal on upload: `app/image_pipeline/metadata_stripper.py`
- Before-image storage: private bucket (raw-selfies)
- After-image/generated storage: public CDN (generated-images)

**PCI-DSS Compliance:**
- SAQ-A: No cardholder data flows through backend (Stripe hosted payment sheet)
- Payment data collection: Stripe SDK on mobile (app client)

---

*Integration audit: 2026-03-17*
