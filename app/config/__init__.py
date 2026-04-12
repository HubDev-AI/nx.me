from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="app/.env", extra="ignore")

    # App
    APP_ENV: str = "development"
    SECRET_KEY: str
    ADMIN_API_KEY: str

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
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""  # Required when ADAPTER__LLM_ADAPTER=anthropic (used for embeddings via OpenAI API)

    # Adapter selection
    ADAPTER__NSFW_ADAPTER: str = "mock"
    ADAPTER__FACE_ANALYSIS_ADAPTER: str = "mock"
    ADAPTER__IMAGE_GENERATION_ADAPTER: str = "mock"
    ADAPTER__LLM_ADAPTER: str = "mock"
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
    ADVISOR_MILESTONE_DEDUP_HOURS: int = (
        48  # Hours before a duplicate milestone nudge is allowed
    )

    # Entitlement constants (AC-3: must be named constants, not inline literals)
    FREE_TRIAL_ANALYSES: int = 2
    IDENTITY_SIMILARITY_THRESHOLD: float = 0.80
    MAX_CONCURRENT_GENERATIONS_PER_USER: int = 3

    # Advisor tuning (audit A-3, A-5, A-6)
    ADVISOR_CHAT_RATE_LIMIT_WINDOW_SECONDS: int = 3600
    ADVISOR_EMBEDDING_MODEL: str = "text-embedding-3-small"
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
    IMAGE_GEN_COST_CEILING_USD: float = 0.06
    GENERATION_TIMEOUT_SECONDS: int = 180
    CREDIT_COST_ALERT_USD: float = 0.05
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

    # Stripe checkout return URLs (server-controlled — never user-supplied)
    STRIPE_SUCCESS_URL: str = "https://nxme.ai/payment/success"
    STRIPE_CANCEL_URL: str = "https://nxme.ai/payment/cancel"

    # Stripe credit pack price IDs (Story 4-4 — set per-environment)
    STRIPE_PRICE_CREDITS_10: str = ""
    STRIPE_PRICE_CREDITS_25: str = ""
    STRIPE_PRICE_CREDITS_50: str = ""

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

    # Guest reaction token registry (LR-8)
    GUEST_TOKEN_TTL_SECONDS: int = 86_400  # 24 hours — registration window per token
    GUEST_REACTION_LIMIT: int = 50  # max reactions per guest token per 24h

    # Account deletion (Story 2-2 AC-FR5)
    USERNAME_RESERVATION_DAYS: int = 180  # days username is reserved post-deletion

    # Retention policy — nightly cron in app/workers/retention.py
    RETENTION_UPLOAD_DAYS: int = (
        30  # uploads not accessed for N days are purged (with CASCADE)
    )
    RETENTION_JOB_DAYS: int = 7  # unsaved jobs older than N days are purged

    # Auth provider feature flags — toggle login methods per environment.
    # When disabled: API rejects requests, mobile hides the button.
    AUTH_PROVIDER_GOOGLE_ENABLED: bool = True
    AUTH_PROVIDER_APPLE_ENABLED: bool = False
    AUTH_PROVIDER_EMAIL_ENABLED: bool = False
    AUTH_PROVIDER_TIKTOK_ENABLED: bool = False

    # Feature flags — unified registry exposed via GET /v1/features.
    # Prod-safe defaults. Override per-env via app/.env.
    # In development, typical dev overrides are:
    #   FEATURE_AUTH_REQUIRED=false
    #   FEATURE_ONBOARDING_ENABLED=false
    #   FEATURE_SOCIAL_ENABLED=false  (already default)
    FEATURE_AUTH_REQUIRED: bool = True
    FEATURE_SOCIAL_ENABLED: bool = False  # post-poned — flip when launching social
    FEATURE_SHARE_ENABLED: bool = True
    FEATURE_ONBOARDING_ENABLED: bool = True
    # Note: the advisor flag is the existing ADVISOR_ENABLED setting above.

    # Fixed user ID used as a fallback when auth is fully disabled (legacy dev guest).
    # Per-session guest users (users.is_guest=true) coexist with this one.
    DEV_GUEST_USER_ID: str = "00000000-0000-0000-0000-000000000001"

    # TikTok OAuth2 credentials (Login Kit v2)
    TIKTOK_CLIENT_KEY: str = ""
    TIKTOK_CLIENT_SECRET: str = ""
    # Synthetic email domain for TikTok users (internal identifier, never user-facing)
    TIKTOK_SYNTHETIC_EMAIL_DOMAIN: str = "oauth.nxme.internal"
    # Timeout for TikTok API calls (token exchange, user info)
    TIKTOK_HTTPX_TIMEOUT_SECONDS: float = 15.0


settings = Settings()
