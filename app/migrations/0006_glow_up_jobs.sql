-- Story 4-2: Generation Queue & ARQ Worker
-- glow_up_jobs table + prompt_experiments table

CREATE TABLE glow_up_jobs (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                   UUID NOT NULL REFERENCES users(id),
    analysis_id               UUID REFERENCES analyses(id),
    original_image_id         UUID NOT NULL REFERENCES images(id),
    generated_image_id        UUID REFERENCES images(id),
    credit_reservation_id     UUID REFERENCES credit_reservations(id),
    status                    TEXT NOT NULL DEFAULT 'pending'
                              CHECK (status IN ('pending', 'queued', 'processing', 'completed', 'failed', 'cancelled')),
    queue_lane                TEXT NOT NULL
                              CHECK (queue_lane IN ('generation:premium', 'generation:credit', 'generation:trial')),
    prompt_mode               TEXT CHECK (prompt_mode IN ('everyday', 'polished', 'editorial')),
    prompt_text               TEXT,
    negative_prompt_text      TEXT,
    model_used                TEXT,
    generation_params         JSONB,
    identity_similarity_score FLOAT,
    identity_preserved        BOOLEAN,
    wow_score                 FLOAT,
    candidate_count           INT DEFAULT 1,
    estimated_cost_usd        DECIMAL(6,4),
    failure_reason            TEXT,
    idempotency_key           TEXT UNIQUE,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_glow_up_jobs_user ON glow_up_jobs (user_id, created_at DESC);
CREATE INDEX idx_glow_up_jobs_status ON glow_up_jobs (status) WHERE status IN ('pending', 'queued', 'processing');
CREATE INDEX idx_glow_up_jobs_stuck ON glow_up_jobs (updated_at) WHERE status = 'processing';

-- Prompt A/B testing experiments
CREATE TABLE prompt_experiments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID NOT NULL REFERENCES glow_up_jobs(id),
    prompt_mode     TEXT NOT NULL,
    prompt_template TEXT NOT NULL,
    keyword_count   INT NOT NULL,
    arcface_score   FLOAT,
    wow_score       FLOAT,
    user_score      FLOAT,
    final_score     FLOAT,
    retry_count     INT NOT NULL DEFAULT 0,
    generation_ms   INT,
    estimated_cost  DECIMAL(6,4),
    model_used      TEXT NOT NULL,
    outcome         TEXT NOT NULL
                    CHECK (outcome IN ('success', 'identity_failed', 'nsfw_blocked', 'error')),
    feedback_actions TEXT[],
    feedback_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_prompt_exp_mode ON prompt_experiments (prompt_mode, created_at DESC);
