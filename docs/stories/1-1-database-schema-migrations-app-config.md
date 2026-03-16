---
id: "1-1-database-schema-migrations-app-config"
status: ready
created: 2026-03-16
---

# Story: Database Schema, Migrations & App Config

## User Story

As a developer, I want all database tables and application configuration constants defined before implementation begins, so that all stories code against verified schemas and constants rather than ad-hoc definitions.

## Acceptance Criteria

- Given all 13 tables from the architecture (users, analyses, glow_up_jobs, credit_reservations, credit_ledger, subscriptions, images, posts, reactions, comments, shareable_cards, reports, processed_webhook_events), When migrations are applied, Then schema matches the architecture data models exactly including all CHECK constraints, indexes, and foreign keys.
- Given a fresh database with migrations applied, When a CI migration cycle (up → seed → down → up) runs, Then it completes without errors.
- Given the config module, When any component reads `FREE_TRIAL_ANALYSES`, `IDENTITY_SIMILARITY_THRESHOLD`, `GENERATION_TIMEOUT_SECONDS`, `MAX_CONCURRENT_GENERATIONS_PER_USER`, `MAX_UPLOAD_SIZE_MB`, `MAX_IMAGE_DIMENSION_PX`, `CREDIT_COST_ALERT_USD`, `IMAGE_GEN_COST_CEILING_USD`, Then it reads from a named constant — grep asserts zero inline numeric literals for these values outside the config module.
- Given the tier identifier module, When any code uses tier values, Then it uses exactly `TRIAL`, `CREDIT_HOLDER`, `PREMIUM` from named constants — grep asserts zero inline string literals outside the constants file.

## Architecture Guardrails

### Technology Stack

- **Backend:** Python 3.12 + FastAPI
- **Database:** Supabase PostgreSQL (managed, hosted — NOT local Postgres in Docker)
- **Config library:** `pydantic-settings` 2.13.1 (verified 2026-03-16)
- **Migration runner:** Custom Python runner (`app/migrations/run.py`) — NOT Alembic
- **No automated tests** — per QA skill decision; zero test code written during development

### File Structure for This Story

```
app/
  config.py                    # Settings class (pydantic-settings), all env-backed constants
  constants/
    __init__.py
    tiers.py                   # TRIAL, CREDIT_HOLDER, PREMIUM as named string constants
  migrations/
    __init__.py
    run.py                     # Migration runner (up/down, --target flag)
    0001_initial.sql           # All 13 architecture tables
    0002_tiers.sql             # Amendment A-4: tiers table + users.tier_id column
    0003_usage_events.sql      # Amendment A-5: usage_events table
    0004_seed_tiers.sql        # Seed TRIAL, CREDIT_HOLDER, PREMIUM tier rows
  services/
    limits.py                  # LimitType StrEnum (7 values) — required by config/tiers.py
  config/
    tiers.py                   # TierSeed dataclass + SEED_TIERS list (seed only, not runtime)
```

### Naming Conventions

- All SQL: `snake_case` table and column names
- Python: `PascalCase` classes, `SCREAMING_SNAKE_CASE` constants, `snake_case` functions
- Migration filenames: `NNNN_descriptive_name.sql` (zero-padded 4 digits)
- Always `TIMESTAMPTZ` (not `TIMESTAMP`) for all timestamp columns
- Soft deletes via `deleted_at` column pattern (or `is_deleted BOOLEAN` where used in architecture)
- Audit columns (`created_at`, `updated_at`) on every table where shown

### Import Pattern

```python
# Config import (all service files):
from app.config import settings

# Tier constants import (wherever tier values are compared/returned):
from app.constants.tiers import TRIAL, CREDIT_HOLDER, PREMIUM
```

### pydantic-settings Pattern (Required)

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    
    APP_ENV: str = "development"
    SECRET_KEY: str
    # ... all fields with defaults or required
    
settings = Settings()
```

### Migration Runner Contract

```
python -m app.migrations.run --target 0001_initial   # run up to including 0001
python -m app.migrations.run --target 0004_seed_tiers  # run all migrations
python -m app.migrations.run --down --target 0001_initial  # rollback to before 0001
```

The runner connects to Supabase using `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`. It must track applied migrations in a `_schema_migrations` table (created on first run if not present). Each `.sql` file must have a corresponding `-- DOWN:` section (or separate `_down.sql` file — pick one approach consistently).

### Amendment Integration: A-4 (DB-Driven Tier System)

**Amendment A-4 supersedes the architecture's `users.tier TEXT CHECK (...)` column.**

Architecture.md section 3.1 defines `users.tier TEXT NOT NULL DEFAULT 'TRIAL' CHECK (tier IN ('TRIAL', 'CREDIT_HOLDER', 'PREMIUM'))`. A-4 **replaces** this with `tier_id UUID NOT NULL REFERENCES tiers(id)`.

The `tiers` table (added in `0002_tiers.sql`) holds all limit configuration. The `users.tier_id` FK points to the appropriate tier row seeded in `0004_seed_tiers.sql`.

**Note on AC-3 vs A-4 tension:** AC-3 requires `FREE_TRIAL_ANALYSES`, `IDENTITY_SIMILARITY_THRESHOLD`, and `MAX_CONCURRENT_GENERATIONS_PER_USER` in the config module. A-4 moves `identity_similarity_threshold` and `max_concurrent_generations` to per-tier DB columns. The resolution: `app/config.py` still defines `FREE_TRIAL_ANALYSES` as an app-level default (used by `TrialGrantor` in story 2-1 as the initial `trial_analyses_remaining` value on account creation). `IDENTITY_SIMILARITY_THRESHOLD` and `MAX_CONCURRENT_GENERATIONS_PER_USER` in `app/config.py` serve as **global defaults / circuit-breaker values** used outside the per-tier path (e.g., the stuck-job watchdog in section 9.4 uses `MAX_CONCURRENT_GENERATIONS_PER_USER`). This satisfies AC-3's grep assertion while respecting A-4's DB-first principle.

### Amendment Integration: A-5 (Usage Events Table)

**Amendment A-5 adds the `usage_events` table** (added in `0003_usage_events.sql`).

This table is an append-only log of every consumed action, used as the source of truth for rolling-window limit checks by `EntitlementService` in story 4-1.

---

## Data Models

### 3.1 `users` (Amended by A-4: `tier_id UUID FK` replaces `tier TEXT CHECK`)

```sql
CREATE TABLE users (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username                  TEXT UNIQUE NOT NULL,
    display_name              TEXT NOT NULL,
    email                     TEXT UNIQUE,
    avatar_storage_key        TEXT,
    tier_id                   UUID NOT NULL REFERENCES tiers(id),
    -- NOTE: tier_id is set to default tier (from tiers.is_default=true) at registration.
    -- No tier name string ever stored here. EntitlementService reads user.tier_id -> TierRecord.
    trial_analyses_remaining  INT NOT NULL DEFAULT 2,
    guest_session_token       TEXT,
    email_verified            BOOLEAN NOT NULL DEFAULT FALSE,
    is_minor                  BOOLEAN,
    deleted_at                TIMESTAMPTZ,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_users_username ON users (username);
CREATE INDEX idx_users_guest_token ON users (guest_session_token) WHERE guest_session_token IS NOT NULL;
```

### 3.2 `analyses`

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
-- NOTE: landmark_vectors are NOT stored — ephemeral per ADR-1
CREATE INDEX idx_analyses_user_id ON analyses (user_id, created_at DESC);
```

### 3.3 `glow_up_jobs`

```sql
CREATE TABLE glow_up_jobs (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key             TEXT UNIQUE NOT NULL,
    analysis_id                 UUID NOT NULL REFERENCES analyses(id),
    user_id                     UUID NOT NULL REFERENCES users(id),
    status                      TEXT NOT NULL DEFAULT 'pending'
                                CHECK (status IN ('pending','queued','processing','completed','failed','cancelled')),
    failure_reason              TEXT
                                CHECK (failure_reason IN (
                                    'FACE_VALIDATION_FAILED','GENERATION_TIMEOUT','NSFW_QUARANTINE',
                                    'IDENTITY_PRESERVATION_FAILED','PROVIDER_ERROR','UNKNOWN'
                                ) OR failure_reason IS NULL),
    before_image_id             UUID REFERENCES images(id),
    after_image_id              UUID REFERENCES images(id),
    identity_similarity_score   FLOAT,
    identity_preserved          BOOLEAN,
    credit_reservation_id       UUID REFERENCES credit_reservations(id),
    user_tier_at_enqueue        TEXT NOT NULL CHECK (user_tier_at_enqueue IN ('TRIAL','CREDIT_HOLDER','PREMIUM')),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at                TIMESTAMPTZ
);
CREATE INDEX idx_jobs_user_id ON glow_up_jobs (user_id, created_at DESC);
CREATE INDEX idx_jobs_status ON glow_up_jobs (status) WHERE status IN ('pending','queued','processing');
CREATE INDEX idx_jobs_watchdog ON glow_up_jobs (updated_at) WHERE status = 'processing';
```

**Note on `user_tier_at_enqueue`:** This column stores the slug-based tier label for the queue routing decision only (which ARQ lane to use). It is not used for any business logic check — that goes through `tier_id`. This is the one place tier name strings appear in DB schema, purposely limited to this denormalized audit/routing field.

### 3.4 `credit_reservations`

```sql
CREATE TABLE credit_reservations (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES users(id),
    amount       INT NOT NULL DEFAULT 1,
    status       TEXT NOT NULL DEFAULT 'reserved'
                 CHECK (status IN ('reserved', 'committed', 'released')),
    job_id       UUID REFERENCES glow_up_jobs(id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at  TIMESTAMPTZ
);
CREATE INDEX idx_reservations_user_status ON credit_reservations (user_id, status);
```

### 3.5 `credit_ledger`

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
-- Balance invariants (enforced by tests in story where CreditLedger is built):
-- reserve + release = 0 net; reserve + commit = -1 net
CREATE INDEX idx_ledger_user_id ON credit_ledger (user_id, created_at DESC);
```

### 3.6 `subscriptions`

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

### 3.7 `images`

```sql
CREATE TABLE images (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID NOT NULL REFERENCES users(id),
    storage_key    TEXT UNIQUE,
    bucket         TEXT,
    image_type     TEXT NOT NULL
                   CHECK (image_type IN ('selfie','generated_before','generated_after','avatar')),
    status         TEXT NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending','cleared','quarantined')),
    screened_at    TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- storage_key is NULLABLE: NULL for quarantined images (never written to storage)
CREATE INDEX idx_images_user_status ON images (user_id, status);
CREATE INDEX idx_images_moderation ON images (status) WHERE status IN ('pending', 'quarantined');
```

### 3.8 `posts`

```sql
CREATE TABLE posts (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES users(id),
    glow_up_job_id   UUID NOT NULL REFERENCES glow_up_jobs(id),
    caption          TEXT,
    before_image_id  UUID NOT NULL REFERENCES images(id),
    after_image_id   UUID NOT NULL REFERENCES images(id),
    before_image_url TEXT NOT NULL,
    after_image_url  TEXT NOT NULL,
    reaction_count   INT NOT NULL DEFAULT 0,
    comment_count    INT NOT NULL DEFAULT 0,
    is_deleted       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_posts_user ON posts (user_id, created_at DESC) WHERE NOT is_deleted;
CREATE INDEX idx_posts_feed_newest ON posts (created_at DESC) WHERE NOT is_deleted;
CREATE INDEX idx_posts_feed_trending ON posts (reaction_count DESC, created_at DESC) WHERE NOT is_deleted;
```

### 3.9 `reactions`

```sql
CREATE TABLE reactions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id             UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    user_id             UUID REFERENCES users(id),
    guest_session_token TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT reaction_source_check
        CHECK ((user_id IS NOT NULL) <> (guest_session_token IS NOT NULL)),
    CONSTRAINT reactions_unique_user
        UNIQUE (post_id, user_id),
    CONSTRAINT reactions_unique_guest
        UNIQUE (post_id, guest_session_token)
);
```

### 3.10 `comments`

```sql
CREATE TABLE comments (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id     UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES users(id),
    content     TEXT NOT NULL CHECK (length(content) BETWEEN 1 AND 1000),
    is_deleted  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_comments_post ON comments (post_id, created_at ASC) WHERE NOT is_deleted;
```

### 3.11 `shareable_cards`

```sql
CREATE TABLE shareable_cards (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID UNIQUE NOT NULL REFERENCES users(id),
    post_id     UUID REFERENCES posts(id),
    slug        TEXT UNIQUE NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_cards_slug ON shareable_cards (slug);
```

### 3.12 `reports`

```sql
CREATE TABLE reports (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id          UUID NOT NULL REFERENCES posts(id),
    reporter_user_id UUID NOT NULL REFERENCES users(id),
    reason           TEXT,
    status           TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending','reviewed','actioned','dismissed')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 3.13 `processed_webhook_events`

```sql
CREATE TABLE processed_webhook_events (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider     TEXT NOT NULL,
    event_id     TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider, event_id)
);
```

### `tiers` Table (Amended by A-4 — new table, not in architecture.md)

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
-- At most one default tier; default requires active
CREATE UNIQUE INDEX idx_tiers_one_default ON tiers(is_default) WHERE is_default = true;
ALTER TABLE tiers ADD CONSTRAINT chk_default_requires_active
  CHECK (NOT is_default OR is_active);
```

### `usage_events` Table (Amended by A-5 — new table, not in architecture.md)

```sql
CREATE TABLE usage_events (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  action     TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'committed',
  job_id     TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- action values: 'generation', 'advisor_nudge', 'advisor_message'
-- status lifecycle: 'reserved' -> 'committed' -> 'released' (generation only)
-- non-credit tiers: always 'committed' at enqueue; only 'committed' events counted
CREATE UNIQUE INDEX idx_usage_events_job_id ON usage_events(job_id) WHERE job_id IS NOT NULL;
CREATE INDEX idx_usage_events_user_action_time ON usage_events(user_id, action, created_at DESC);
```

### Migration Ordering and FK Dependencies

Because `0001_initial.sql` contains FKs between tables, create them in this order:

1. `users` — no FKs (but requires `tiers` via `tier_id` — create `tiers` first in `0002`)
2. In `0001_initial.sql`, `users.tier_id` is NOT added yet (tiers table doesn't exist in 0001). `0001` creates `users` WITHOUT `tier_id`. `0002_tiers.sql` creates `tiers` and then `ALTER TABLE users ADD COLUMN tier_id UUID REFERENCES tiers(id)` and `ALTER TABLE users ALTER COLUMN tier_id SET NOT NULL` (after seeding in 0004).
3. `images` — FK to `users`
4. `analyses` — FK to `users`, `images`
5. `credit_reservations` — FK to `users`, `glow_up_jobs` (circular — use deferred FK or create without FK first, add later)
6. `glow_up_jobs` — FK to `users`, `analyses`, `images`, `credit_reservations`
7. All remaining tables in dependency order

**Handling the circular FK between `glow_up_jobs` and `credit_reservations`:**

```sql
-- In 0001_initial.sql:
-- Create credit_reservations WITHOUT the job_id FK initially:
CREATE TABLE credit_reservations (
    ...
    job_id UUID,  -- no REFERENCES yet
    ...
);
-- Create glow_up_jobs WITH FK to credit_reservations:
CREATE TABLE glow_up_jobs (
    ...
    credit_reservation_id UUID REFERENCES credit_reservations(id),
    ...
);
-- Then add the FK back on credit_reservations:
ALTER TABLE credit_reservations
    ADD CONSTRAINT fk_credit_reservations_job_id
    FOREIGN KEY (job_id) REFERENCES glow_up_jobs(id);
```

### `LimitType` StrEnum (required by `config/tiers.py`)

```python
# app/services/limits.py
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

### Tier Seed Data

Three tiers are seeded in `0004_seed_tiers.sql`. The UUIDs are fixed/deterministic (generated once and hardcoded in the migration) so that `app/constants/tiers.py` can reference them by UUID constant for use in tests and admin scripts:

| Slug | display_name | is_default | generation_type | generation_limit | advisor_nudges_type | advisor_nudges_limit | max_concurrent | id_similarity_threshold | credits_based |
|------|-------------|------------|-----------------|-----------------|---------------------|---------------------|---------------|------------------------|---------------|
| `free` | Free | true | daily | 1 | weekly | 3 | 1 | 0.800 | false |
| `credits` | Credits | false | credits | NULL | weekly | 10 | 2 | 0.750 | true |
| `premium` | Premium | false | monthly | 100 | unlimited | NULL | 3 | 0.700 | false |

The `0004_seed_tiers.sql` file must use explicit fixed UUIDs (not `gen_random_uuid()`) so the constants file can reference them:

```sql
-- Use these fixed UUIDs (chosen once, never changed):
-- TRIAL/free:          'a0000000-0000-0000-0000-000000000001'
-- CREDIT_HOLDER/credits: 'a0000000-0000-0000-0000-000000000002'
-- PREMIUM/premium:      'a0000000-0000-0000-0000-000000000003'
```

### `app/config.py` Required Constants

```python
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

    # Advisor
    ADVISOR_PERSONA_NAME: str = "TBD"
    ADVISOR_CONTEXT_MEMORY_LIMIT: int = 20

    # Entitlement constants (AC-3: must be named constants, not inline literals)
    FREE_TRIAL_ANALYSES: int = 2
    IDENTITY_SIMILARITY_THRESHOLD: float = 0.80  # global default; per-tier value overrides in DB
    MAX_CONCURRENT_GENERATIONS_PER_USER: int = 3   # global ceiling; per-tier value in tiers table

    # Upload limits
    MAX_UPLOAD_SIZE_MB: int = 20
    MAX_IMAGE_DIMENSION_PX: int = 8192
    SIGNED_URL_EXPIRY_SECONDS: int = 3600

    # Generation / cost
    IMAGE_GEN_COST_CEILING_USD: float = 0.05
    GENERATION_TIMEOUT_SECONDS: int = 60
    CREDIT_COST_ALERT_USD: float = 0.04

settings = Settings()
```

### `app/constants/tiers.py` Required Constants

```python
# Tier slug constants (AC-4) — used only where tier slugs must be compared/returned:
# - API responses (GET /entitlement returns tier display context)
# - Queue routing (which ARQ lane to use)
# - Admin scripts and seed references
# NEVER used in EntitlementService business logic conditionals.

TRIAL: str = "TRIAL"
CREDIT_HOLDER: str = "CREDIT_HOLDER"
PREMIUM: str = "PREMIUM"

# Fixed UUIDs matching 0004_seed_tiers.sql (for tests and admin scripts):
TIER_ID_TRIAL: str = "a0000000-0000-0000-0000-000000000001"
TIER_ID_CREDIT_HOLDER: str = "a0000000-0000-0000-0000-000000000002"
TIER_ID_PREMIUM: str = "a0000000-0000-0000-0000-000000000003"
```

**Critical constraint:** `TRIAL`, `CREDIT_HOLDER`, `PREMIUM` string constants are used ONLY in:
- `app/constants/tiers.py` (definition)
- API response serialization (`tier_slug` field in responses)
- `glow_up_jobs.user_tier_at_enqueue` column writes
- The seed migration `0004_seed_tiers.sql` (`slug` column values)

They MUST NOT appear as string literals in service logic, conditionals, or any business rules.

---

## Verified Interfaces

This is the first story — no source code exists yet. All interface entries are UNVERIFIED, using plan/architecture contracts.

### Settings (pydantic-settings)

- **Source:** `app/config.py` — to be created in this story
- **Signature:** `settings: Settings` — module-level singleton
- **Plan match:** UNVERIFIED — source not yet implemented, using plan contract

### Migration Runner CLI

- **Source:** `app/migrations/run.py` — to be created in this story
- **Signature:** `python -m app.migrations.run [--target MIGRATION_ID] [--down]`
- **Plan match:** UNVERIFIED — source not yet implemented, using plan contract

### LimitType StrEnum

- **Source:** `app/services/limits.py` — to be created in this story
- **Signature:** `LimitType(StrEnum)` with values: `total`, `daily`, `weekly`, `monthly`, `period`, `credits`, `unlimited`
- **Plan match:** UNVERIFIED — source not yet implemented, using plan contract

---

## Tasks

- [x] Task 1: Core schema migrations (0001, 0002, 0003)
  - Maps to: AC-1, AC-2
  - Files to create:
    - `app/migrations/__init__.py`
    - `app/migrations/run.py`
    - `app/migrations/0001_initial.sql`
    - `app/migrations/0002_tiers.sql`
    - `app/migrations/0003_usage_events.sql`
  - Also create: `app/services/__init__.py`, `app/services/limits.py` (LimitType StrEnum — required by config/tiers.py in Task 2)

- [x] Task 2: Tier seed migration (0004)
  - Maps to: AC-4, AC-2
  - Files to create:
    - `app/migrations/0004_seed_tiers.sql`
    - `app/config/__init__.py`
    - `app/config/tiers.py` (TierSeed dataclass + SEED_TIERS list — seed only, not runtime)
  - Depends on: Task 1 (tiers table must exist)

- [x] Task 3: App config module and tier constants
  - Maps to: AC-3, AC-4
  - Files to create:
    - `app/config.py`
    - `app/constants/__init__.py`
    - `app/constants/tiers.py`
  - Note: `app/config.py` is distinct from `app/config/` directory. The `app/config/` directory is for seed-only files (tiers.py). The `app/config.py` file is the runtime settings singleton.

---

## must_haves

truths:
  - "app/migrations/0001_initial.sql creates tables: users, analyses, glow_up_jobs, credit_reservations, credit_ledger, subscriptions, images, posts, reactions, comments, shareable_cards, reports, processed_webhook_events"
  - "app/migrations/0002_tiers.sql creates the tiers table with slug, display_name, is_default, is_active, generation_type, generation_limit, advisor_nudges_type, advisor_nudges_limit, max_concurrent_generations, identity_similarity_threshold, feature_advisor_chat, feature_visual_comparison, stripe_price_id, credits_based columns, and adds tier_id UUID column to users"
  - "app/migrations/0003_usage_events.sql creates usage_events table with indexes idx_usage_events_job_id and idx_usage_events_user_action_time"
  - "app/migrations/0004_seed_tiers.sql inserts exactly 3 tier rows with slugs: free, credits, premium; the free tier has is_default=true"
  - "app/config.py defines Settings class with fields: FREE_TRIAL_ANALYSES, GENERATION_TIMEOUT_SECONDS, MAX_UPLOAD_SIZE_MB, MAX_IMAGE_DIMENSION_PX, IMAGE_GEN_COST_CEILING_USD, CREDIT_COST_ALERT_USD, IDENTITY_SIMILARITY_THRESHOLD, MAX_CONCURRENT_GENERATIONS_PER_USER"
  - "app/constants/tiers.py defines TRIAL = 'TRIAL', CREDIT_HOLDER = 'CREDIT_HOLDER', PREMIUM = 'PREMIUM' as string constants"
  - "grep for the literal string '0.05' outside app/config.py returns zero matches in the app/ directory"
  - "grep for the literal string '0.80' or '0.800' outside app/config.py and app/migrations/ returns zero matches in the app/ directory"
  - "grep for the literal string \"'TRIAL'\" or '\"TRIAL\"' outside app/constants/tiers.py and app/migrations/ returns zero matches in the app/ directory"

artifacts:
  - path: "app/config.py"
    contains: ["Settings", "FREE_TRIAL_ANALYSES", "GENERATION_TIMEOUT_SECONDS", "MAX_UPLOAD_SIZE_MB", "IMAGE_GEN_COST_CEILING_USD", "CREDIT_COST_ALERT_USD", "IDENTITY_SIMILARITY_THRESHOLD", "MAX_CONCURRENT_GENERATIONS_PER_USER", "settings = Settings()"]
  - path: "app/constants/tiers.py"
    contains: ["TRIAL", "CREDIT_HOLDER", "PREMIUM", "TIER_ID_TRIAL", "TIER_ID_CREDIT_HOLDER", "TIER_ID_PREMIUM"]
  - path: "app/migrations/0001_initial.sql"
    contains: ["CREATE TABLE users", "CREATE TABLE analyses", "CREATE TABLE glow_up_jobs", "CREATE TABLE credit_reservations", "CREATE TABLE credit_ledger", "CREATE TABLE subscriptions", "CREATE TABLE images", "CREATE TABLE posts", "CREATE TABLE reactions", "CREATE TABLE comments", "CREATE TABLE shareable_cards", "CREATE TABLE reports", "CREATE TABLE processed_webhook_events"]
  - path: "app/migrations/0002_tiers.sql"
    contains: ["CREATE TABLE tiers", "idx_tiers_one_default", "chk_default_requires_active", "tier_id UUID"]
  - path: "app/migrations/0003_usage_events.sql"
    contains: ["CREATE TABLE usage_events", "idx_usage_events_job_id", "idx_usage_events_user_action_time"]
  - path: "app/migrations/0004_seed_tiers.sql"
    contains: ["INSERT INTO tiers", "a0000000-0000-0000-0000-000000000001", "a0000000-0000-0000-0000-000000000002", "a0000000-0000-0000-0000-000000000003", "is_default"]
  - path: "app/migrations/run.py"
    contains: ["def main", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "_schema_migrations"]
  - path: "app/services/limits.py"
    contains: ["LimitType", "StrEnum", "TOTAL", "DAILY", "WEEKLY", "MONTHLY", "PERIOD", "CREDITS", "UNLIMITED"]
  - path: "app/config/tiers.py"
    contains: ["TierSeed", "SEED_TIERS", "LimitType"]

key_links:
  - pattern: "from app.config import settings"
    in: ["all service files in app/"]
  - pattern: "from app.constants.tiers import"
    in: ["any file that uses TRIAL, CREDIT_HOLDER, or PREMIUM values"]
  - pattern: "FREE_TRIAL_ANALYSES"
    in: ["app/config.py"]
  - pattern: "SEED_TIERS"
    in: ["app/config/tiers.py", "app/migrations/run.py"]
  - pattern: "LimitType"
    in: ["app/services/limits.py", "app/config/tiers.py"]

---

## Dev Notes

### Testing Approach

Zero automated tests per QA skill decision. All verification is via:
- Grep assertions (patterns in must_haves.truths above)
- Manual: run migrations against the nxme-dev Supabase project; verify tables exist in Supabase dashboard
- Manual: run the CI migration cycle: `python -m app.migrations.run --target 0004_seed_tiers` then `python -m app.migrations.run --down --target 0001_initial` then `python -m app.migrations.run --target 0004_seed_tiers` (should complete without errors)

### Local Dev Environment

Redis is the only Docker service. Supabase is a real `nxme-dev` free-tier project (not local Postgres).

```bash
# Start Redis (only Docker service):
docker compose up -d

# Activate Python venv:
source .venv/bin/activate

# Run migrations against real Supabase dev:
python -m app.migrations.run --target 0004_seed_tiers

# Verify Redis is up:
docker compose exec redis redis-cli ping
```

Environment variables required for this story (all must be in `.env`):
- `SUPABASE_URL` — Supabase project URL (e.g., `https://xxxx.supabase.co`)
- `SUPABASE_SERVICE_ROLE_KEY` — server-only service role key (bypasses RLS for migrations)
- `SUPABASE_ANON_KEY` — public anon key
- `SUPABASE_JWT_SECRET` — JWT secret from Supabase Settings → API
- `SECRET_KEY` — JWT signing key (32+ chars)
- `ADMIN_API_KEY` — admin API key (32+ chars)
- All constants listed in AC-3: `FREE_TRIAL_ANALYSES`, `GENERATION_TIMEOUT_SECONDS`, `MAX_UPLOAD_SIZE_MB`, `MAX_IMAGE_DIMENSION_PX`, `IMAGE_GEN_COST_CEILING_USD`, `CREDIT_COST_ALERT_USD`

Dev setup scripts:
- `./scripts/dev-setup.sh` — first-time setup (runs migrations)
- `./scripts/dev-start.sh` — daily start
- `./scripts/dev-reset.sh` — clean slate

Manual migration run:
```bash
source .venv/bin/activate
python -m app.migrations.run --target 0001_initial
```

### Library Versions

- **pydantic-settings:** 2.13.1 (verified 2026-03-16 via PyPI)
- **Python:** 3.12

### Migration Runner Implementation Notes

The `run.py` migration runner must:
1. Connect to Supabase PostgreSQL using `psycopg2` or `supabase-py` with the service role key
2. Create `_schema_migrations (id SERIAL, migration_id TEXT UNIQUE, applied_at TIMESTAMPTZ)` if not exists
3. On `--target MIGRATION_ID`: apply all migrations in order up to and including the target that haven't been applied yet
4. On `--down --target MIGRATION_ID`: reverse migrations in reverse order from current down to and including the target
5. Each `.sql` file should have a `-- DOWN:` marker separating the up and down SQL sections, or implement as paired `NNNN_name_up.sql` / `NNNN_name_down.sql` files
6. **Each migration must run inside a transaction**: if any statement in the migration fails, the entire migration rolls back — nothing is partially applied. Use `conn.autocommit = False`, execute all statements, then `conn.commit()` on success or `conn.rollback()` on exception. Also wrap the `_schema_migrations` INSERT in the same transaction so the migration record is only recorded if all SQL succeeded.

```python
# Pattern for each migration:
conn.autocommit = False
try:
    cur.execute(migration_sql)  # all DDL/DML in the .sql file
    cur.execute(
        "INSERT INTO _schema_migrations (migration_id, applied_at) VALUES (%s, NOW())",
        (migration_id,)
    )
    conn.commit()
except Exception:
    conn.rollback()
    raise
```

### No Inline Literals Rule

After Task 3 completes, the following grep checks should return zero results outside their designated files:

```bash
# No hardcoded 0.05 (IMAGE_GEN_COST_CEILING_USD) outside config:
grep -r "0\.05" app/ --include="*.py" | grep -v "app/config.py"

# No hardcoded 20 as upload limit (MAX_UPLOAD_SIZE_MB) outside config:
grep -r "\b20\b" app/ --include="*.py" | grep -v "app/config.py"

# No tier string literals outside constants and migrations:
grep -r "'TRIAL'\|\"TRIAL\"\|'CREDIT_HOLDER'\|\"CREDIT_HOLDER\"\|'PREMIUM'\|\"PREMIUM\"" \
    app/ --include="*.py" | grep -v "app/constants/tiers.py"
```

### `app/config/tiers.py` vs `app/config.py` Distinction

These are two different files:
- `app/config.py` — runtime settings singleton (`from pydantic_settings import BaseSettings`)
- `app/config/tiers.py` — seed-only data class file (`TierSeed` dataclass + `SEED_TIERS` list). **Never imported at runtime.** Used only by `app/migrations/run.py` to seed the tiers table. The `app/config/__init__.py` must not re-export anything from `tiers.py`.

### Prior Story Intelligence

This is story 1-1 — the first story. No prior story patterns to inherit. The conventions established here become the baseline for all subsequent stories:
- `from app.config import settings` is the canonical config import pattern
- `from app.constants.tiers import TRIAL, CREDIT_HOLDER, PREMIUM` is the canonical tier reference pattern
- `app/migrations/NNNN_name.sql` is the migration file convention
- `python -m app.migrations.run --target MIGRATION_ID` is the migration runner CLI

---

## Wave Structure

Wave 1 (single wave — all tasks are sequential due to FK dependencies):
- Task 1 (core schema migrations) must complete before Task 2 (tier seed migration requires tiers table)
- Task 2 (tier seed migration) must complete before Task 3 can be fully validated (constants reference seeded UUIDs)
- Task 3 (app config + tier constants) can be written in parallel with Tasks 1-2 but must be validated after migrations run

Note: All three tasks can be written (files created) in parallel. They become execution-dependent only when running the actual migration against Supabase.
