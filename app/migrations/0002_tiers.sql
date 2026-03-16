-- 0002_tiers.sql
-- Amendment A-4: DB-driven tier system.
-- Creates the tiers table and adds tier_id FK column to users.
-- tier_id is nullable here; NOT NULL is enforced in 0004 after seeding.

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

ALTER TABLE users ADD COLUMN tier_id UUID REFERENCES tiers(id);

-- DOWN:

ALTER TABLE users DROP COLUMN IF EXISTS tier_id;
DROP TABLE IF EXISTS tiers CASCADE;
