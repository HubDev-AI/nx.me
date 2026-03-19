-- Admin ban columns for account suspension
ALTER TABLE users ADD COLUMN is_banned BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN banned_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN ban_reason TEXT;
CREATE INDEX idx_users_banned ON users(is_banned) WHERE is_banned = TRUE;
