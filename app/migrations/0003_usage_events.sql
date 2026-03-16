-- 0003_usage_events.sql
-- Amendment A-5: append-only usage events log.
-- Source of truth for rolling-window limit checks by EntitlementService.

CREATE TABLE usage_events (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    action     TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'committed',
    job_id     TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_usage_events_job_id ON usage_events(job_id) WHERE job_id IS NOT NULL;
CREATE INDEX idx_usage_events_user_action_time ON usage_events(user_id, action, created_at DESC);

-- DOWN:

DROP TABLE IF EXISTS usage_events CASCADE;
