-- Migration: 0005_username_reserved_until
-- Adds username_reserved_until to users so that deleted usernames are
-- held for 180 days before becoming available to new registrations.
-- Story 2-2 (AC-FR5): username reservation on account deletion.

-- === UP ===
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS username_reserved_until TIMESTAMPTZ;

-- Index to speed up "is this username available?" queries during registration.
CREATE INDEX IF NOT EXISTS idx_users_username_reserved
    ON users (username, deleted_at, username_reserved_until)
    WHERE deleted_at IS NOT NULL;

-- DOWN:
DROP INDEX IF EXISTS idx_users_username_reserved;
ALTER TABLE users DROP COLUMN IF EXISTS username_reserved_until;
