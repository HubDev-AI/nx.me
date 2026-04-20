-- 0063_jobs_glowup_lookup_index.sql
-- Covering index for the chat-seeds + /next-step glow-up lookup.
--
-- `AdvisorRepository.get_latest_completed_glowup_id` runs on every
-- GET /v1/advisor/chat-seeds BEFORE the Redis cache check (the cache key
-- is scoped by glowup_id). The query filters by
-- (user_id, source_type='glowup_analysis', status='completed') and
-- orders by updated_at DESC LIMIT 1. At pre-launch scale the table is
-- tiny, but the structural gap ships alongside this PR so it doesn't
-- regress when the table grows.
--
-- Idempotent: CREATE INDEX IF NOT EXISTS.

CREATE INDEX IF NOT EXISTS idx_jobs_user_source_status_updated_at
    ON jobs (user_id, source_type, status, updated_at DESC);
