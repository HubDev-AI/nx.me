-- Story 4-2: Generation Queue & ARQ Worker
-- Extends glow_up_jobs (created in 0001) with queue/generation columns.
-- Creates prompt_experiments table.

-- ============================================================
-- UP
-- ============================================================

-- Add columns that exist in 0006 spec but not in 0001 schema.
-- Using IF NOT EXISTS so the migration is safe to re-run.

ALTER TABLE glow_up_jobs
    ADD COLUMN IF NOT EXISTS original_image_id       UUID REFERENCES images(id),
    ADD COLUMN IF NOT EXISTS generated_image_id      UUID REFERENCES images(id),
    ADD COLUMN IF NOT EXISTS prompt_mode             TEXT
                                                     CHECK (prompt_mode IN ('everyday', 'polished', 'editorial')),
    ADD COLUMN IF NOT EXISTS prompt_text             TEXT,
    ADD COLUMN IF NOT EXISTS negative_prompt_text    TEXT,
    ADD COLUMN IF NOT EXISTS model_used              TEXT,
    ADD COLUMN IF NOT EXISTS generation_params       JSONB,
    ADD COLUMN IF NOT EXISTS wow_score               FLOAT,
    ADD COLUMN IF NOT EXISTS candidate_count         INT DEFAULT 1,
    ADD COLUMN IF NOT EXISTS estimated_cost_usd      DECIMAL(6,4);

-- Expand failure_reason CHECK to include the values added in this story.
-- DROP the old constraint first, then ADD the replacement.

ALTER TABLE glow_up_jobs
    DROP CONSTRAINT IF EXISTS glow_up_jobs_failure_reason_check;

ALTER TABLE glow_up_jobs
    ADD CONSTRAINT glow_up_jobs_failure_reason_check
    CHECK (failure_reason IS NULL OR failure_reason IN (
        'FACE_VALIDATION_FAILED',
        'GENERATION_TIMEOUT',
        'NSFW_QUARANTINE',
        'IDENTITY_PRESERVATION_FAILED',
        'PROVIDER_ERROR',
        'UNKNOWN',
        'NSFW_CONTENT_DETECTED',
        'CANCELLED',
        'QUEUE_FULL'
    ));

-- Prompt A/B testing experiments
CREATE TABLE IF NOT EXISTS prompt_experiments (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id           UUID NOT NULL REFERENCES glow_up_jobs(id),
    prompt_mode      TEXT NOT NULL,
    prompt_template  TEXT NOT NULL,
    keyword_count    INT NOT NULL,
    arcface_score    FLOAT,
    wow_score        FLOAT,
    user_score       FLOAT,
    final_score      FLOAT,
    retry_count      INT NOT NULL DEFAULT 0,
    generation_ms    INT,
    estimated_cost   DECIMAL(6,4),
    model_used       TEXT NOT NULL,
    outcome          TEXT NOT NULL
                     CHECK (outcome IN ('success', 'identity_failed', 'nsfw_blocked', 'error')),
    feedback_actions TEXT[],
    feedback_at      TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prompt_exp_mode
    ON prompt_experiments (prompt_mode, created_at DESC);

-- DOWN:

-- To roll back this migration:

DROP INDEX IF EXISTS idx_prompt_exp_mode;
DROP TABLE IF EXISTS prompt_experiments;

-- Restore the original failure_reason constraint from 0001.
ALTER TABLE glow_up_jobs
    DROP CONSTRAINT IF EXISTS glow_up_jobs_failure_reason_check;
ALTER TABLE glow_up_jobs
    ADD CONSTRAINT glow_up_jobs_failure_reason_check
    CHECK (failure_reason IN (
        'FACE_VALIDATION_FAILED','GENERATION_TIMEOUT','NSFW_QUARANTINE',
        'IDENTITY_PRESERVATION_FAILED','PROVIDER_ERROR','UNKNOWN'
    ) OR failure_reason IS NULL);

ALTER TABLE glow_up_jobs
    DROP COLUMN IF EXISTS estimated_cost_usd,
    DROP COLUMN IF EXISTS candidate_count,
    DROP COLUMN IF EXISTS wow_score,
    DROP COLUMN IF EXISTS generation_params,
    DROP COLUMN IF EXISTS model_used,
    DROP COLUMN IF EXISTS negative_prompt_text,
    DROP COLUMN IF EXISTS prompt_text,
    DROP COLUMN IF EXISTS prompt_mode,
    DROP COLUMN IF EXISTS generated_image_id,
    DROP COLUMN IF EXISTS original_image_id;
