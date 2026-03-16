-- 0001_initial.sql
-- Creates all 13 architecture tables in FK-dependency order.
-- Handles circular FK between credit_reservations and glow_up_jobs
-- by deferring the credit_reservations.job_id FK constraint.

-- 1. users (no tier_id yet — added in 0002_tiers.sql after tiers table exists)
CREATE TABLE users (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username                  TEXT UNIQUE NOT NULL,
    display_name              TEXT NOT NULL,
    email                     TEXT UNIQUE,
    avatar_storage_key        TEXT,
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

-- 2. images (FK to users)
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
CREATE INDEX idx_images_user_status ON images (user_id, status);
CREATE INDEX idx_images_moderation ON images (status) WHERE status IN ('pending', 'quarantined');

-- 3. analyses (FK to users, images)
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
CREATE INDEX idx_analyses_user_id ON analyses (user_id, created_at DESC);

-- 4. credit_reservations (FK to users; job_id FK deferred — circular dep with glow_up_jobs)
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

-- 5. glow_up_jobs (FK to users, analyses, images, credit_reservations)
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

-- 6. Add deferred FK: credit_reservations.job_id -> glow_up_jobs(id)
ALTER TABLE credit_reservations
    ADD CONSTRAINT fk_credit_reservations_job_id
    FOREIGN KEY (job_id) REFERENCES glow_up_jobs(id);

-- 7. credit_ledger (FK to users)
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

-- 8. subscriptions (FK to users)
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

-- 9. posts (FK to users, glow_up_jobs, images)
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

-- 10. reactions (FK to posts, users)
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

-- 11. comments (FK to posts, users)
CREATE TABLE comments (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id     UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES users(id),
    content     TEXT NOT NULL CHECK (length(content) BETWEEN 1 AND 1000),
    is_deleted  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_comments_post ON comments (post_id, created_at ASC) WHERE NOT is_deleted;

-- 12. shareable_cards (FK to users, posts)
CREATE TABLE shareable_cards (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID UNIQUE NOT NULL REFERENCES users(id),
    post_id     UUID REFERENCES posts(id),
    slug        TEXT UNIQUE NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_cards_slug ON shareable_cards (slug);

-- 13. reports (FK to posts, users)
CREATE TABLE reports (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id          UUID NOT NULL REFERENCES posts(id),
    reporter_user_id UUID NOT NULL REFERENCES users(id),
    reason           TEXT,
    status           TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending','reviewed','actioned','dismissed')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 14. processed_webhook_events (no FK)
CREATE TABLE processed_webhook_events (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider     TEXT NOT NULL,
    event_id     TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider, event_id)
);

-- DOWN:

DROP TABLE IF EXISTS processed_webhook_events CASCADE;
DROP TABLE IF EXISTS reports CASCADE;
DROP TABLE IF EXISTS shareable_cards CASCADE;
DROP TABLE IF EXISTS comments CASCADE;
DROP TABLE IF EXISTS reactions CASCADE;
DROP TABLE IF EXISTS posts CASCADE;
DROP TABLE IF EXISTS subscriptions CASCADE;
DROP TABLE IF EXISTS credit_ledger CASCADE;
ALTER TABLE credit_reservations DROP CONSTRAINT IF EXISTS fk_credit_reservations_job_id;
DROP TABLE IF EXISTS glow_up_jobs CASCADE;
DROP TABLE IF EXISTS credit_reservations CASCADE;
DROP TABLE IF EXISTS analyses CASCADE;
DROP TABLE IF EXISTS images CASCADE;
DROP TABLE IF EXISTS users CASCADE;
