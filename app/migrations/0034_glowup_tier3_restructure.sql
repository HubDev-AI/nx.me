-- 0034_glowup_tier3_restructure.sql
-- Tier 3 architecture refactor for the Glow Up feature. Restructures the
-- schema to become the shared foundation the upcoming Makeup feature will
-- drop into. Rename analyses -> uploads (shared primitive), split the
-- face-analysis payload into a dedicated glowup_analyses table, and rename
-- glow_up_jobs -> jobs with polymorphic source_type + source_id.
--
-- Pre-launch: no production data to preserve. Dev seed data is wiped on
-- apply — teams must re-seed their local stack after running this.
--
-- Plan: docs/plans/glowup-tier3-refactor.md (Phase 1).

-- 1. Drop RLS policies on legacy tables before the tables themselves.
DROP POLICY IF EXISTS analyses_own ON analyses;
DROP POLICY IF EXISTS glow_up_jobs_own ON glow_up_jobs;

-- 2. Drop FK constraints from dependent tables so legacy drops cleanly.
--    CASCADE on DROP TABLE would leave these columns orphaned with dangling
--    UUIDs rather than removing the FKs; explicit is clearer.
ALTER TABLE credit_reservations   DROP CONSTRAINT IF EXISTS fk_credit_reservations_job_id;
ALTER TABLE posts                 DROP CONSTRAINT IF EXISTS posts_glow_up_job_id_fkey;
ALTER TABLE prompt_experiments    DROP CONSTRAINT IF EXISTS prompt_experiments_job_id_fkey;

-- 3. Wipe dependent rows whose job_id / glow_up_job_id values are about to
--    point at dropped rows. posts.glow_up_job_id and prompt_experiments.job_id
--    are NOT NULL, so TRUNCATE is the only path. credit_reservations.job_id
--    is nullable; null out orphans so the table keeps its non-job rows.
TRUNCATE posts, prompt_experiments CASCADE;
UPDATE  credit_reservations SET job_id = NULL WHERE job_id IS NOT NULL;

-- 4. Drop legacy tables. CASCADE cleans up any indexes / sequences we missed.
DROP TABLE IF EXISTS glow_up_jobs CASCADE;
DROP TABLE IF EXISTS analyses      CASCADE;

-- 5. uploads — shared upload primitive replacing the old analyses entry point.
CREATE TABLE uploads (
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    image_url         TEXT         NOT NULL,
    nsfw_result       TEXT         NOT NULL,
    face_detected     BOOLEAN      NOT NULL DEFAULT FALSE,
    last_accessed_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    mst_bin           SMALLINT     NULL,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_uploads_user_id_created ON uploads (user_id, created_at DESC);
CREATE INDEX idx_uploads_last_accessed   ON uploads (last_accessed_at);

-- 6. glowup_analyses — Glow Up face analysis payload, one per upload.
CREATE TABLE glowup_analyses (
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    upload_id         UUID         NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    face_shape        TEXT,
    symmetry_score    REAL,
    recommendations   JSONB,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT glowup_analyses_face_shape_check
        CHECK (face_shape IS NULL OR face_shape IN ('oval','round','square','heart','oblong')),
    CONSTRAINT glowup_analyses_symmetry_score_check
        CHECK (symmetry_score IS NULL OR (symmetry_score >= 0.0 AND symmetry_score <= 1.0))
);
CREATE UNIQUE INDEX idx_glowup_analyses_upload_id ON glowup_analyses (upload_id);

-- 7. jobs — polymorphic generation job. source_type + source_id point at either
--    a glowup_analyses row (today) or a makeup_sessions row (deferred to Makeup
--    milestone). PostgreSQL cannot express a polymorphic FK; integrity is
--    enforced at the application layer.
CREATE TABLE jobs (
    id                      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_type             TEXT         NOT NULL,
    source_id               UUID         NOT NULL,
    status                  TEXT         NOT NULL DEFAULT 'queued',
    before_image_url        TEXT,
    after_image_url         TEXT,
    failure_reason          TEXT,
    saved_at                TIMESTAMPTZ  NULL,
    user_tier_at_enqueue    TEXT,
    idempotency_key         TEXT,
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT jobs_source_type_check
        CHECK (source_type IN ('glowup_analysis','makeup_session')),
    CONSTRAINT jobs_status_check
        CHECK (status IN ('queued','processing','finalizing','completed','failed','cancelled')),
    CONSTRAINT jobs_failure_reason_check
        CHECK (failure_reason IS NULL OR failure_reason IN (
            'FACE_VALIDATION_FAILED','GENERATION_TIMEOUT','NSFW_QUARANTINE',
            'IDENTITY_PRESERVATION_FAILED','PROVIDER_ERROR','UNKNOWN',
            'NSFW_CONTENT_DETECTED','CANCELLED','QUEUE_FULL'
        )),
    CONSTRAINT jobs_user_tier_at_enqueue_check
        CHECK (user_tier_at_enqueue IS NULL OR user_tier_at_enqueue IN ('TRIAL','CREDIT_HOLDER','PREMIUM'))
);
CREATE UNIQUE INDEX idx_jobs_user_idempotency ON jobs (user_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;
CREATE        INDEX idx_jobs_source             ON jobs (source_type, source_id);
CREATE        INDEX idx_jobs_status_updated     ON jobs (status, updated_at)
    WHERE status IN ('queued','processing','finalizing');
CREATE        INDEX idx_jobs_saved_at           ON jobs (saved_at)
    WHERE saved_at IS NOT NULL;
CREATE        INDEX idx_jobs_user_id_created    ON jobs (user_id, created_at DESC);

-- 8. Rewire dependent table FKs to the new jobs table.
ALTER TABLE credit_reservations
    ADD CONSTRAINT fk_credit_reservations_job_id
    FOREIGN KEY (job_id) REFERENCES jobs(id);

ALTER TABLE posts
    ADD CONSTRAINT posts_glow_up_job_id_fkey
    FOREIGN KEY (glow_up_job_id) REFERENCES jobs(id);

ALTER TABLE prompt_experiments
    ADD CONSTRAINT prompt_experiments_job_id_fkey
    FOREIGN KEY (job_id) REFERENCES jobs(id);

-- 9. users.face_mod_consent_at — Q17 face-modification consent, DB-backed.
ALTER TABLE users
    ADD COLUMN face_mod_consent_at TIMESTAMPTZ NULL;

-- 10. Row-level security on the new tables. Matches the policy shape used for
--     the legacy analyses/glow_up_jobs tables (0013_row_level_security.sql) —
--     authenticated users see only their own rows.
ALTER TABLE uploads          ENABLE ROW LEVEL SECURITY;
ALTER TABLE uploads          FORCE  ROW LEVEL SECURITY;
ALTER TABLE glowup_analyses  ENABLE ROW LEVEL SECURITY;
ALTER TABLE glowup_analyses  FORCE  ROW LEVEL SECURITY;
ALTER TABLE jobs             ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs             FORCE  ROW LEVEL SECURITY;

CREATE POLICY uploads_own ON uploads
    FOR ALL TO authenticated
    USING      (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

-- glowup_analyses has no user_id column; scope via the owning upload.
CREATE POLICY glowup_analyses_own ON glowup_analyses
    FOR ALL TO authenticated
    USING      (upload_id IN (SELECT id FROM uploads WHERE user_id = auth.uid()))
    WITH CHECK (upload_id IN (SELECT id FROM uploads WHERE user_id = auth.uid()));

CREATE POLICY jobs_own ON jobs
    FOR ALL TO authenticated
    USING      (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

-- DOWN: intentionally omitted. Pre-launch refactor; rolling back would require
-- re-seeding legacy schemas that no longer match the running application code.
-- Restore from an earlier migration point or rebuild from scratch instead.
