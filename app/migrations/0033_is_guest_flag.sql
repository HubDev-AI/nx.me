-- Add is_guest flag to users table for ephemeral guest user support.
-- Per-session guests are created when FEATURE_AUTH_REQUIRED=false.
-- Guest users have no credentials and get their own entitlement + jobs.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS is_guest BOOLEAN NOT NULL DEFAULT false;

-- Partial index for guest cleanup / analytics (most queries are non-guest).
CREATE INDEX IF NOT EXISTS idx_users_is_guest
    ON users (id)
    WHERE is_guest = true;

-- The fixed dev guest user (00000000-...-0001) is marked as guest so it's
-- queryable consistently. Idempotent — no-op if already true.
UPDATE users
    SET is_guest = true
    WHERE id = '00000000-0000-0000-0000-000000000001'::uuid
      AND is_guest = false;
