-- 0067_makeup_analyses_table.sql
-- Creates the makeup_analyses table storing per-user analyzer output:
-- Monk Skin Tone bin, undertone, region anchors, and preset ranking.
-- Biometric fields (mst_bin, undertone, region_anchors) are purged at
-- 90 days via a scheduled sweeper; consent fields are retained per
-- privacy policy.
--
-- Indexes:
--   (user_id, created_at DESC) — latest-per-user lookup in Unit 6
--   (created_at)               — purge sweeper range scan

CREATE TABLE IF NOT EXISTS makeup_analyses (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id          uuid        REFERENCES jobs(id) ON DELETE CASCADE,
    mst_bin         smallint,
    undertone       text,
    region_anchors  jsonb,
    preset_ranking  jsonb,
    consent_version text        NOT NULL,
    consent_at      timestamptz NOT NULL DEFAULT now(),
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_makeup_analyses_user_created_at
    ON makeup_analyses (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_makeup_analyses_created_at
    ON makeup_analyses (created_at);
