-- 0064_jobs_makeup_lookup_index.sql
-- Extends the jobs table with makeup-specific nullable columns,
-- constraints, and a lookup index parallel to 0063's glowup index.
--
-- All new columns are nullable so non-makeup rows (glowup_analysis) need
-- no backfill. makeup_failure_reason and intensity carry CHECK constraints
-- scoped only to their allowed value sets. preset_slug is free-text
-- (validated at enqueue via preset_registry — a DB CHECK would couple to
-- the YAML and require a migration per preset change).
--
-- Body-hash idempotency: idempotency_key_body_hash stores a SHA-256 hex
-- digest over (preset_slug, intensity, upload_id) so a client replay of
-- the SAME Idempotency-Key header with a DIFFERENT body gets a 409
-- IDEMPOTENCY_KEY_CONFLICT instead of silently returning the original
-- result. Reuses the existing idx_jobs_user_idempotency index from 0034.
--
-- fal_idempotency_key is the worker-generated key passed to fal's
-- X-Fal-Idempotency-Key header for crash-recovery reconciliation.

-- Nullable makeup columns on jobs
ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS fal_request_id         text,
    ADD COLUMN IF NOT EXISTS fal_url                text,
    ADD COLUMN IF NOT EXISTS output_key             text,
    ADD COLUMN IF NOT EXISTS preset_slug            text,
    ADD COLUMN IF NOT EXISTS intensity              text,
    ADD COLUMN IF NOT EXISTS makeup_failure_reason  text,
    ADD COLUMN IF NOT EXISTS fal_idempotency_key    text,
    ADD COLUMN IF NOT EXISTS idempotency_key_body_hash text,
    ADD COLUMN IF NOT EXISTS consent_version_at_enqueue text;

-- Intensity allowlist (makeup rows only; NULL for glowup rows)
ALTER TABLE jobs
    DROP CONSTRAINT IF EXISTS jobs_intensity_check,
    ADD CONSTRAINT jobs_intensity_check
        CHECK (intensity IS NULL OR intensity IN ('subtle', 'light', 'medium', 'bold'));

-- Makeup failure reason allowlist (distinct from glowup's failure_reason column)
ALTER TABLE jobs
    DROP CONSTRAINT IF EXISTS jobs_makeup_failure_reason_check,
    ADD CONSTRAINT jobs_makeup_failure_reason_check
        CHECK (makeup_failure_reason IS NULL
            OR makeup_failure_reason IN ('refused', 'non_retryable', 'retryable'));

-- Unique index for fal-side idempotency key (worker-generated, per-call)
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_fal_idempotency_key
    ON jobs (fal_idempotency_key)
    WHERE fal_idempotency_key IS NOT NULL;

-- Covering index for makeup job history lookup (parallel to 0063's glowup index)
CREATE INDEX IF NOT EXISTS idx_jobs_makeup_user_completed
    ON jobs (user_id, completed_at DESC)
    WHERE source_type = 'makeup_session';
