from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="app/.env", extra="ignore")

    # App
    APP_ENV: str = "development"
    SECRET_KEY: str
    ADMIN_API_KEY: str

    # Logging — empty means "derive from APP_ENV": DEBUG in development,
    # INFO everywhere else. Override with LOG_LEVEL=INFO|DEBUG|WARNING|...
    # to pin the level explicitly. ``effective_log_level`` resolves the
    # final value at runtime.
    LOG_LEVEL: str = ""

    @property
    def effective_log_level(self) -> str:
        explicit = (self.LOG_LEVEL or "").strip().upper()
        if explicit:
            return explicit
        return "DEBUG" if self.APP_ENV.strip().lower() == "development" else "INFO"

    @property
    def advisor_debug_payload_enabled(self) -> bool:
        """True when full Anthropic prompts + responses should hit the logs.

        Defaults to True in development DEBUG mode so a fresh dev setup
        sees the full advisor flow without flipping a flag. Production
        must NEVER auto-enable: signed URLs and raw user content land in
        DEBUG records. Explicit ``ADVISOR_DEBUG_LOG_PROMPT=true`` still
        wins everywhere for ad-hoc debugging.
        """
        if self.ADVISOR_DEBUG_LOG_PROMPT:
            return True
        return (
            self.APP_ENV.strip().lower() == "development"
            and self.effective_log_level == "DEBUG"
        )

    @field_validator("SECRET_KEY")
    @classmethod
    def _secret_key_min_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

    @field_validator("ADMIN_API_KEY")
    @classmethod
    def _admin_api_key_min_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("ADMIN_API_KEY must be at least 32 characters")
        return v

    # Supabase
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_JWT_SECRET: str
    # Public-facing Supabase URL for signed storage URLs (mobile needs LAN IP in dev)
    SUPABASE_PUBLIC_URL: str = ""

    # Redis
    REDIS_URL: str = "redis://:localdev@localhost:6379/0"

    # External APIs
    FAL_API_KEY: str = ""
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    STRIPE_API_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    # Publishable key returned to mobile clients alongside PaymentIntent
    # bundles so they can sanity-check against the compiled-in key.
    STRIPE_PUBLISHABLE_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""  # Required when ADAPTER__EMBEDDING_ADAPTER=openai
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"

    # Adapter selection
    ADAPTER__NSFW_ADAPTER: str = "mock"
    ADAPTER__FACE_ANALYSIS_ADAPTER: str = "mock"
    ADAPTER__IMAGE_GENERATION_ADAPTER: str = "mock"
    ADAPTER__LLM_ADAPTER: str = "mock"
    ADAPTER__EMBEDDING_ADAPTER: str = "mock"  # mock | openai | ollama
    ADAPTER__PAYMENT_ADAPTER: str = "mock"
    ADAPTER__STORAGE_ADAPTER: str = "supabase"

    # Advisor
    # Advisor module (pluggable — set to False to disable entirely)
    ADVISOR_ENABLED: bool = True
    ADVISOR_PERSONA_NAME: str = "Ada"
    ADVISOR_CONTEXT_MEMORY_LIMIT: int = (
        3  # Max memories per request. Less = more human.
    )
    ADVISOR_MAX_MESSAGE_LENGTH: int = 2000  # Max chars per user message
    ADVISOR_CHAT_RATE_LIMIT: int = 30  # Max messages per hour per user
    ADVISOR_DEGRADATION_THRESHOLD: int = 50  # Daily messages before degrading to Haiku
    ADVISOR_CONVERSATION_SUMMARY_THRESHOLD: int = 30  # Messages before auto-summarize
    ADVISOR_CONVERSATION_INACTIVE_DAYS: int = 7  # Days before auto-new conversation
    # DEPRECATED — Plan 2026-04-17-003 Unit 8. The vision-grounded
    # nudge redesign dropped the fixed 60-min cooldown entirely: dedup
    # now emerges from the model's own access to prior nudge bodies +
    # model-authored ``observation_tag``s in the prompt's "do not
    # repeat" block. Kept at 0 as a rollback knob — set to a positive
    # value to temporarily gate post_analysis / post_glowup on a time
    # window if the vision path ever misbehaves. A rapid-retry dedup
    # (same upload_id within 5 min) still fires at the scheduler level.
    ADVISOR_POST_ANALYSIS_NUDGE_COOLDOWN_MINUTES: int = 0

    # Plan 2026-04-17-003 Unit 8. How many prior nudges (body +
    # observation_tag) are included in the vision-nudge prompt's
    # "do not repeat" block. The cap keeps the prompt compact — the
    # model only needs enough context to steer away from recent
    # observations, not the full history.
    ADVISOR_NUDGE_RECENT_CONTEXT_LIMIT: int = 5

    # Plan 2026-04-17-003 Unit 8. Rapid-retry dedup window for
    # ``post_glowup`` nudges. If a second post_glowup fires within this
    # many minutes of the previous one for the same user AND the prior
    # job was for the same source upload (same ``upload_id``), skip the
    # second generation. Narrow guard against the "user tapped Analyze,
    # got a failure, tapped again" scenario producing back-to-back
    # near-duplicate images.
    ADVISOR_POST_GLOWUP_RAPID_RETRY_MINUTES: int = 5
    ADVISOR_MEMORY_CAP: int = 500  # Max memories per user (spec §10).
    ADVISOR_CONTEXT_TOKEN_BUDGET: int = 5000  # Max input tokens to the LLM (spec §10).

    # Advisor payload logging (Plan 2026-04-17-003 Unit 5).
    # When True, every Ada LLM call ALSO emits a DEBUG record carrying the
    # full system + messages payload. INFO records (always on) are safe —
    # hashed user_id, only host + expiry-presence for signed URLs, no raw
    # user content. DEBUG records include full content and signed URLs —
    # DO NOT enable in production.
    ADVISOR_DEBUG_LOG_PROMPT: bool = False

    # Advisor chat nudge context (Plan 2026-04-17-003 Unit 4).
    # Ada's chat context gains a dedicated 4th system block listing the
    # user's most recent nudges (read and unread). Cap the block at the
    # newest ``ADVISOR_CONTEXT_NUDGE_LIMIT`` nudges created within the
    # trailing ``ADVISOR_CONTEXT_NUDGE_AGE_DAYS`` window. Block budget is
    # ~150-300 tokens, absorbed by the existing 5 000-token cap.
    ADVISOR_CONTEXT_NUDGE_LIMIT: int = 5
    ADVISOR_CONTEXT_NUDGE_AGE_DAYS: int = 14

    # Advisor tool surface (Plan 2026-04-17-003 Unit 9).
    # Ada chat operates via a tool surface the model invokes on demand.
    # ``ADVISOR_MAX_TOOL_ROUNDS`` caps the number of tool-use rounds the
    # model can request per user turn — on exhaustion, remaining tool_use
    # blocks receive a synthetic "tool round cap exceeded" tool_result so
    # the model can still finalize its text rather than loop indefinitely.
    # ``ADVISOR_TOOLS_ENABLED`` is the kill switch: when False, tools are
    # not advertised to the model and the legacy eager-vision path remains
    # authoritative.
    ADVISOR_MAX_TOOL_ROUNDS: int = 3
    ADVISOR_TOOLS_ENABLED: bool = True

    # Entitlement constants (AC-3: must be named constants, not inline literals)
    FREE_TRIAL_ANALYSES: int = 2
    # ArcFace buffalo_l cosine similarity between L2-normalised face
    # embeddings. Face verification ("same person") literature lands in
    # the 0.28-0.50 band; glow-ups intentionally change style, hair, and
    # makeup while preserving the person, so 0.80 rejects almost every
    # legitimate output. 0.45 keeps obvious drift out without punishing
    # the creative path. Override per-environment via
    # ``IDENTITY_SIMILARITY_THRESHOLD`` (e.g. raise during incidents).
    IDENTITY_SIMILARITY_THRESHOLD: float = 0.45
    MAX_CONCURRENT_GENERATIONS_PER_USER: int = 3

    # Advisor tuning (audit A-3, A-5, A-6)
    ADVISOR_CHAT_RATE_LIMIT_WINDOW_SECONDS: int = 3600
    ADVISOR_EMBEDDING_MODEL: str = "text-embedding-3-small"
    # Embedding vector size — must match the DB column dimension. Ollama's
    # nomic-embed-text outputs 768 natively; OpenAI text-embedding-3-small
    # supports any dim 1..1536 via Matryoshka. Migration
    # 0037_advisor_embedding_dim_768.sql sets the vector(768) column.
    EMBEDDING_DIMENSIONS: int = 768
    ADVISOR_MODEL_HAIKU: str = "claude-haiku-4-5-20251001"

    # Identity retry tuning (audit G-4)
    IDENTITY_RETRY_ID_WEIGHT_DELTA: float = 0.10
    IDENTITY_RETRY_ID_WEIGHT_CAP: float = 0.95
    IDENTITY_RETRY_GUIDANCE_DELTA: float = 0.5
    IDENTITY_RETRY_GUIDANCE_FLOOR: float = 3.5

    # Color normalization tuning (audit G-8)
    COLOR_NORM_BRIGHTNESS_DELTA: int = 20
    COLOR_NORM_FACTOR_MIN: float = 0.8
    COLOR_NORM_FACTOR_MAX: float = 1.2

    # Generation httpx timeout (audit G-5)
    GENERATION_HTTPX_TIMEOUT_SECONDS: float = 60.0

    # Model cost estimates (USD per generation, from provider pricing)
    FAL_COST_NANO_BANANA_PRO: float = 0.150  # $0.15/image (Gemini 3 Pro)
    FAL_COST_NANO_BANANA_2: float = 0.080  # $0.08/image at 1K default
    FAL_COST_FLUX2_FLEX: float = 0.063  # $0.06/MP for 1024x1024
    FAL_COST_NANO_BANANA: float = 0.039
    FAL_COST_KONTEXT: float = 0.040
    FAL_COST_FLUX_PULID: float = 0.035
    FAL_COST_FLUX_DEV_IMG2IMG: float = 0.026
    FAL_COST_INSTANTID: float = 0.020
    FAL_COST_DEFAULT: float = 0.080

    # Advisor Sonnet model (chat responses)
    ADVISOR_MODEL_SONNET: str = "claude-sonnet-4-6"

    # LLM call timeouts (M-6)
    ADVISOR_LLM_TIMEOUT_SECONDS: float = 30.0
    ADVISOR_EMBEDDING_TIMEOUT_SECONDS: float = 15.0

    # SDK retry config (explicit — do not rely on SDK defaults)
    LLM_MAX_RETRIES: int = 2
    EMBEDDING_MAX_RETRIES: int = 2

    # Public storage — stable CDN URLs for post images (no signing)
    # Supabase: {SUPABASE_URL}/storage/v1/object/public/{bucket}/{path}
    # Production: override with CloudFront distribution URL
    PUBLIC_STORAGE_BASE_URL: str = ""

    # Upload limits
    MAX_UPLOAD_SIZE_MB: int = 20
    MAX_IMAGE_DIMENSION_PX: int = 8192
    SIGNED_URL_EXPIRY_SECONDS: int = 3600

    # Generation / cost
    # Ceiling must sit ABOVE the current per-generation model cost,
    # otherwise every free-tier generation trips it as soon as the
    # rolling 24h average catches up (observed: fal NANO_BANANA_2 at
    # $0.080/gen against a $0.060 ceiling — 503'd on the first gen).
    # $0.20 covers NANO_BANANA_PRO ($0.150) with headroom for provider
    # price bumps; the guard still fires on a genuine 2-3x runaway.
    # Alert trips at $0.12 — 50 % above NANO_BANANA_2 — so cost creep
    # is visible in logs before the hard gate.
    IMAGE_GEN_COST_CEILING_USD: float = 0.20
    GENERATION_TIMEOUT_SECONDS: int = 180
    CREDIT_COST_ALERT_USD: float = 0.12

    # Dev-only repro harness for the result screen's latency tolerance.
    # Both default off in production. The mobile result screen relies on
    # these to deterministically reproduce the two known failure shapes —
    # client-side env flags can't simulate the real race because the worker
    # row-insert and the URL write happen server-side.
    #
    #   FORCE_404 — GET /v1/jobs/{id} returns 404 for the first N seconds
    #   after a job's created_at, simulating read-after-write replica lag.
    #   Mobile's grace window (JOB_CREATION_GRACE_MS = 10s) and hard
    #   timeout (RESULT_SCREEN_HARD_TIMEOUT_MS = 240s) gate the user-facing
    #   behavior on top of this.
    #
    #   EMIT_NULL_URLS — worker._finalize_job writes after_image_url=NULL on
    #   completed jobs, exercising the "completed with missing URLs" branch
    #   that the result screen now waits out for up to
    #   RESULT_SCREEN_IMAGE_URL_TIMEOUT_MS (60s) before falling to error.
    DEV_GLOWUP_FORCE_404_FOR_NEW_JOBS_SECONDS: int = 0
    DEV_GLOWUP_EMIT_NULL_URLS_ON_COMPLETE: bool = False
    IDENTITY_MAX_RETRIES: int = 1
    MAX_PROMPT_KEYWORDS: int = 6
    FACE_CROP_THRESHOLD: float = 0.25
    GENERATION_EMERGENCY_STOP: bool = False
    MAX_GENERATIONS_PER_USER_PER_DAY: int = 50
    MAX_QUEUE_DEPTH: int = 15000

    # Generation wait estimation (M-3)
    AVG_SECONDS_PER_JOB: int = 15

    # Cost tracker circuit breaker tuning (L-11)
    CB_FAILURE_THRESHOLD: int = 5  # failures within window to open circuit
    CB_FAILURE_WINDOW_SECONDS: int = 300  # 5-minute sliding window
    CB_COOLDOWN_SECONDS: int = 30  # seconds in OPEN before HALF_OPEN probe
    COST_BUCKET_TTL_SECONDS: int = 90_000  # 25 hours (24h + 1h buffer)

    # Generation models
    FAL_MODEL_PRIMARY: str = "fal-ai/nano-banana-2/edit"
    FAL_MODEL_FALLBACK_1: str = "fal-ai/nano-banana/edit"
    FAL_MODEL_FALLBACK_2: str = "fal-ai/nano-banana-pro/edit"

    # Transformation modules — pluggable feature flags
    ENABLED_TRANSFORMATION_MODULES: str = (
        "styling"  # Comma-separated: "styling,teeth,eyes"
    )

    # Stripe SDK call budgets. The SDK's `request_timeout` kwarg isn't
    # always strict, so `StripePaymentAdapter` wraps each call with an
    # `asyncio.wait_for` upper bound equal to the per-call timeout plus
    # `STRIPE_RPC_TIMEOUT_SLACK_SECONDS`. Values chosen against the R17
    # delete-account budget — keep them in sync with the webhook/entitlement
    # timeouts if those ever move.
    STRIPE_DELETE_CUSTOMER_TIMEOUT_SECONDS: float = 3.0
    STRIPE_RETRIEVE_SUBSCRIPTION_TIMEOUT_SECONDS: float = 3.0
    STRIPE_RPC_TIMEOUT_SLACK_SECONDS: float = 0.5

    # Stripe checkout return URLs (server-controlled — never user-supplied)
    STRIPE_SUCCESS_URL: str = "https://nxme.ai/payment/success"
    STRIPE_CANCEL_URL: str = "https://nxme.ai/payment/cancel"

    # Credits-only engine (Unit 7 — plan 2026-04-19-002)
    # Required — fail-fast at settings load if missing or blank.
    STRIPE_PRICE_PRO_V1: str

    # ── Payments — Credits engine (plan 2026-04-19-002) ────────────────────
    # Server-side HMAC key used to derive `signup_grants_issued.deterministic_hash`
    # from the mobile-generated installation UUID. Required; fail-fast if
    # missing or blank at call time (per feedback_no_env_fallbacks). Stored
    # as a comma-separated list so secrets can be rotated without downtime —
    # primary first, optional secondary second. Lookups probe primary then
    # secondary during a rotation window; writes always use primary. See
    # `app/entitlement/fingerprint.py::get_server_secrets` + the runbook.
    SIGNUP_FINGERPRINT_SERVER_SECRET: str

    # Signup credit grant — milli-credits issued on first registration per
    # device fingerprint. 300 milli = 3 glow-ups at 100 milli/glow-up.
    SIGNUP_GRANT_MILLI: int = 300

    # Weekly free grant for Free (non-Pro, non-banned) users.
    # 100 milli = 1 glow-up. Scheduled ARQ worker delivers it on a 7-day cadence.
    WEEKLY_FREE_GRANT_MILLI: int = 100

    # Pro monthly allotment — milli-credits granted per billing period on
    # subscription.created / invoice.payment_succeeded (REPLACE semantics, R7).
    # Also used by charge.refunded + dispute.closed_lost compensating entries
    # as the atomic refund amount for a full-period Pro subscription charge.
    # 3000 milli = 30 glow-ups OR ~200 Ada messages (shared pool per R3).
    MONTHLY_ALLOTMENT_MILLI: int = 3000

    # Per-action debit amounts (milli-credits). Must divide MONTHLY_ALLOTMENT_MILLI
    # evenly so "N glow-ups" / "~M Ada messages" copy stays honest.
    # Changing either creates a new plan_versions row (R12) — existing Pro
    # subscribers stay bound to their original row until they explicitly migrate.
    GLOWUP_COST_MILLI: int = 100
    ADA_COST_MILLI: int = 15

    # Pro monthly price as displayed on the paywall. Must mirror the Stripe
    # Price object (`PRO_SUBSCRIPTION_STRIPE_PRICE_ID`) — if the Stripe price
    # changes, this constant MUST be updated in the same change-set.
    PRO_MONTHLY_PRICE_USD: str = "$9.99"

    # Rate limiting — registration (Story 2-1 AC-3, Story 2-2 AC-4)
    REGISTRATION_FINGERPRINT_LIMIT: int = 3  # max attempts per device fingerprint
    REGISTRATION_FINGERPRINT_WINDOW_SECONDS: int = 86_400  # 24 hours
    REGISTRATION_IP_LIMIT: int = 4  # max attempts per IP address
    REGISTRATION_IP_WINDOW_SECONDS: int = 3_600  # 1 hour

    # Rate limiting — login (LE-5: independent from registration)
    # Tightened to prevent brute force on shared IPs (corporate/mobile networks)
    LOGIN_IP_LIMIT: int = 5
    LOGIN_IP_WINDOW_SECONDS: int = 900  # 15 minutes

    # Rate limiting — comments
    COMMENT_RATE_LIMIT: int = 10
    COMMENT_RATE_WINDOW_SECONDS: int = 60

    # Rate limiting — reports
    REPORT_RATE_LIMIT: int = 5
    REPORT_RATE_WINDOW_SECONDS: int = 3600

    # Content moderation
    REPORT_AUTO_HIDE_THRESHOLD: int = 3

    # Proxy headers — enable only when deployed behind a trusted reverse proxy
    # (e.g., ALB, nginx) that sets X-Forwarded-For.
    TRUST_PROXY_HEADERS: bool = False

    # Account deletion (Story 2-2 AC-FR5)
    USERNAME_RESERVATION_DAYS: int = 180  # days username is reserved post-deletion

    # Retention policy — nightly cron in app/workers/retention.py
    RETENTION_UPLOAD_DAYS: int = (
        30  # uploads not accessed for N days are purged (with CASCADE)
    )
    RETENTION_JOB_DAYS: int = 7  # unsaved jobs older than N days are purged
    # Cap on the per-run unsaved-job purge batch — the nightly worker runs
    # enumerate-before-cascade one job at a time and wipes blobs inline, so
    # a very large backlog is bounded here to keep any single run short.
    # The next night's run picks up the remainder.
    RETENTION_JOB_BATCH_LIMIT: int = 1000

    # Orphan-blob reclaim — nightly cron in app/workers/orphan_reclaim.py
    # (migration 0036). Rows exceeding MAX_ATTEMPTS stay in the DLQ table for
    # operator review; BATCH_SIZE caps DB reads per run.
    ORPHAN_RECLAIM_MAX_ATTEMPTS: int = 5
    ORPHAN_RECLAIM_BATCH_SIZE: int = 100

    # Orphan-analysis reclaim — nightly cron in
    # app/workers/orphan_analysis_reclaim.py (migration 0047). Rows hitting
    # MAX_ATTEMPTS are left in the DLQ for operator review; BATCH_SIZE caps
    # DB reads per run. Kept separate from ORPHAN_RECLAIM_* so the two
    # sweepers can be tuned independently (different surface, different
    # delete cost — blobs hit object storage, analyses hit Postgres).
    ORPHAN_ANALYSIS_RECLAIM_MAX_ATTEMPTS: int = 5
    ORPHAN_ANALYSIS_RECLAIM_BATCH_SIZE: int = 100

    # Reconcile/retention cron mutex — reconcile holds a Redis lock so the
    # retention cron (scheduled 30 min later) skips if reconcile is still
    # running. 1800s = 30 min, matching the cron-spacing budget.
    RECONCILE_LOCK_TTL_SECONDS: int = 1800

    # Auth provider feature flags — toggle login methods per environment.
    # When disabled: API rejects requests, mobile hides the button.
    AUTH_PROVIDER_GOOGLE_ENABLED: bool = True
    AUTH_PROVIDER_APPLE_ENABLED: bool = False
    AUTH_PROVIDER_EMAIL_ENABLED: bool = False
    AUTH_PROVIDER_TIKTOK_ENABLED: bool = False

    # Feature flags — unified registry exposed via GET /v1/features.
    # Prod-safe defaults. Override per-env via app/.env.
    # In development, typical dev overrides are:
    #   FEATURE_ONBOARDING_ENABLED=false
    #   FEATURE_SOCIAL_ENABLED=false  (already default)
    FEATURE_SOCIAL_ENABLED: bool = False  # post-poned — flip when launching social
    FEATURE_SHARE_ENABLED: bool = True
    FEATURE_ONBOARDING_ENABLED: bool = True
    # Note: the advisor flag is the existing ADVISOR_ENABLED setting above.

    # Bypass all per-tier `require_feature` gates. Default False (prod-safe).
    # Set to True only in dev/staging to exercise premium-gated endpoints
    # (e.g., POST /v1/advisor/messages) with free-tier accounts.
    FEATURE_PREMIUM_BYPASS: bool = False

    # TikTok OAuth2 credentials (Login Kit v2)
    TIKTOK_CLIENT_KEY: str = ""
    TIKTOK_CLIENT_SECRET: str = ""
    # Synthetic email domain for TikTok users (internal identifier, never user-facing)
    TIKTOK_SYNTHETIC_EMAIL_DOMAIN: str = "oauth.nxme.internal"
    # Timeout for TikTok API calls (token exchange, user info)
    TIKTOK_HTTPX_TIMEOUT_SECONDS: float = 15.0


settings = Settings()
