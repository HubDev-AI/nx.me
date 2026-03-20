-- 0027_post_share_hash.sql
-- Adds a short share hash to posts for shareable card URLs.
-- URL format: /{username}/glow-up/{share_hash}

ALTER TABLE posts ADD COLUMN share_hash TEXT UNIQUE;

-- Backfill existing posts with 8-char hex hash derived from their UUID
UPDATE posts SET share_hash = left(md5(id::text), 8) WHERE share_hash IS NULL;

-- Make non-nullable after backfill
ALTER TABLE posts ALTER COLUMN share_hash SET NOT NULL;
ALTER TABLE posts ALTER COLUMN share_hash SET DEFAULT left(md5(gen_random_uuid()::text), 8);

CREATE INDEX idx_posts_share_hash ON posts (share_hash);

-- DOWN:
-- DROP INDEX IF EXISTS idx_posts_share_hash;
-- ALTER TABLE posts DROP COLUMN IF EXISTS share_hash;
