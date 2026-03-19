-- Add is_hidden flag for content moderation (auto-hide on report threshold)
ALTER TABLE posts ADD COLUMN is_hidden BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX idx_posts_hidden ON posts(is_hidden) WHERE is_hidden = TRUE;
