from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_ENV: str = "development"
    SECRET_KEY: str
    ADMIN_API_KEY: str

    # Supabase
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_JWT_SECRET: str

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # External APIs
    FAL_API_KEY: str = ""
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    STRIPE_API_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    ANTHROPIC_API_KEY: str = ""

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
    ADVISOR_CONTEXT_MEMORY_LIMIT: int = 3   # Max memories per request. Less = more human.

    # Entitlement constants (AC-3: must be named constants, not inline literals)
    FREE_TRIAL_ANALYSES: int = 2
    IDENTITY_SIMILARITY_THRESHOLD: float = 0.80
    MAX_CONCURRENT_GENERATIONS_PER_USER: int = 3

    # Upload limits
    MAX_UPLOAD_SIZE_MB: int = 20
    MAX_IMAGE_DIMENSION_PX: int = 8192
    SIGNED_URL_EXPIRY_SECONDS: int = 3600

    # Generation / cost
    IMAGE_GEN_COST_CEILING_USD: float = 0.06
    GENERATION_TIMEOUT_SECONDS: int = 60
    CREDIT_COST_ALERT_USD: float = 0.05
    GENERATION_OUTPUT_RESOLUTION: int = 1024
    IDENTITY_MAX_RETRIES: int = 1
    MAX_PROMPT_KEYWORDS: int = 6
    FACE_CROP_THRESHOLD: float = 0.25
    GENERATION_EMERGENCY_STOP: bool = False
    MAX_GENERATIONS_PER_USER_PER_DAY: int = 50
    MAX_QUEUE_DEPTH: int = 15000

    # Generation models (from generation-spec.md)
    FAL_MODEL_PRIMARY: str = "fal-ai/flux-pulid"
    FAL_MODEL_FALLBACK_1: str = "fal-ai/flux-general/image-to-image"
    FAL_MODEL_FALLBACK_2: str = "fal-ai/instantid"

    # Transformation modules — pluggable feature flags
    ENABLED_TRANSFORMATION_MODULES: str = "styling"  # Comma-separated: "styling,teeth,eyes"

    # Rate limiting — registration (Story 2-1 AC-3, Story 2-2 AC-4)
    REGISTRATION_FINGERPRINT_LIMIT: int = 3       # max attempts per device fingerprint
    REGISTRATION_FINGERPRINT_WINDOW_SECONDS: int = 86_400  # 24 hours
    REGISTRATION_IP_LIMIT: int = 4                # max attempts per IP address
    REGISTRATION_IP_WINDOW_SECONDS: int = 3_600   # 1 hour

    # Account deletion (Story 2-2 AC-FR5)
    USERNAME_RESERVATION_DAYS: int = 180          # days username is reserved post-deletion


settings = Settings()
