-- 0028_feed_user_profile.sql
-- Join users table into feed view and SQL functions so feed posts
-- include username, display_name, and avatar_storage_key.
-- Also add a SELECT RLS policy on users for public profile reads
-- (needed for PostgREST relation embeds on comments).

-- UP

-- 1. Add public SELECT policy on users for profile-safe columns.
-- PostgREST embeds (e.g., comments -> users(display_name)) need
-- row-level read access even when the service role client is used,
-- because embedded relations can be evaluated in a sub-query context.
CREATE POLICY users_public_read ON users
  FOR SELECT TO anon, authenticated
  USING (deleted_at IS NULL);

-- 2. Recreate v_feed_posts view with user profile columns.
CREATE OR REPLACE VIEW v_feed_posts AS
SELECT
    p.id,
    p.user_id,
    p.caption,
    p.before_image_url,
    p.after_image_url,
    p.reaction_count,
    p.comment_count,
    p.created_at,
    p.before_image_id,
    p.after_image_id,
    u.username,
    u.display_name,
    u.avatar_storage_key
FROM posts p
JOIN images bi ON bi.id = p.before_image_id AND bi.status = 'cleared'
JOIN images ai ON ai.id = p.after_image_id AND ai.status = 'cleared'
JOIN users u  ON u.id = p.user_id
WHERE NOT p.is_deleted
  AND NOT p.is_hidden
  AND u.deleted_at IS NULL;


-- 3. Drop + recreate feed_trending (return type changes require DROP first).
DROP FUNCTION IF EXISTS feed_trending(double precision, timestamptz, uuid, int);
CREATE OR REPLACE FUNCTION feed_trending(
    p_cursor_score  DOUBLE PRECISION DEFAULT NULL,
    p_cursor_created TIMESTAMPTZ      DEFAULT NULL,
    p_cursor_id      UUID             DEFAULT NULL,
    p_limit          INT              DEFAULT 11
)
RETURNS TABLE (
    id               UUID,
    user_id          UUID,
    caption          TEXT,
    before_image_url TEXT,
    after_image_url  TEXT,
    reaction_count   INT,
    comment_count    INT,
    created_at       TIMESTAMPTZ,
    before_image_id  UUID,
    after_image_id   UUID,
    username         TEXT,
    display_name     TEXT,
    avatar_storage_key TEXT,
    trending_score   DOUBLE PRECISION
)
LANGUAGE sql STABLE
AS $$
    WITH scored AS (
        SELECT
            fp.*,
            fp.reaction_count::double precision
              / POWER(EXTRACT(EPOCH FROM (NOW() - fp.created_at)) / 3600.0 + 2, 1.5)
              AS trending_score
        FROM v_feed_posts fp
        WHERE fp.created_at >= NOW() - INTERVAL '7 days'
    )
    SELECT s.*
    FROM scored s
    WHERE (p_cursor_score IS NULL)
       OR (s.trending_score < p_cursor_score)
       OR (s.trending_score = p_cursor_score AND s.created_at < p_cursor_created)
       OR (s.trending_score = p_cursor_score AND s.created_at = p_cursor_created AND s.id > p_cursor_id)
    ORDER BY s.trending_score DESC, s.created_at DESC, s.id ASC
    LIMIT p_limit;
$$;


-- 4. Drop + recreate feed_biggest_improvements (return type changes require DROP first).
DROP FUNCTION IF EXISTS feed_biggest_improvements(int, timestamptz, uuid, int);
CREATE OR REPLACE FUNCTION feed_biggest_improvements(
    p_cursor_reactions INT         DEFAULT NULL,
    p_cursor_created   TIMESTAMPTZ DEFAULT NULL,
    p_cursor_id        UUID        DEFAULT NULL,
    p_limit            INT         DEFAULT 11
)
RETURNS TABLE (
    id               UUID,
    user_id          UUID,
    caption          TEXT,
    before_image_url TEXT,
    after_image_url  TEXT,
    reaction_count   INT,
    comment_count    INT,
    created_at       TIMESTAMPTZ,
    before_image_id  UUID,
    after_image_id   UUID,
    username         TEXT,
    display_name     TEXT,
    avatar_storage_key TEXT
)
LANGUAGE sql STABLE
AS $$
    SELECT fp.*
    FROM v_feed_posts fp
    WHERE (p_cursor_reactions IS NULL)
       OR (fp.reaction_count < p_cursor_reactions)
       OR (fp.reaction_count = p_cursor_reactions AND fp.created_at < p_cursor_created)
       OR (fp.reaction_count = p_cursor_reactions AND fp.created_at = p_cursor_created AND fp.id > p_cursor_id)
    ORDER BY fp.reaction_count DESC, fp.created_at DESC, fp.id ASC
    LIMIT p_limit;
$$;


-- DOWN:

DROP POLICY IF EXISTS users_public_read ON users;

-- Restore original view without user columns
CREATE OR REPLACE VIEW v_feed_posts AS
SELECT
    p.id,
    p.user_id,
    p.caption,
    p.before_image_url,
    p.after_image_url,
    p.reaction_count,
    p.comment_count,
    p.created_at,
    p.before_image_id,
    p.after_image_id
FROM posts p
JOIN images bi ON bi.id = p.before_image_id AND bi.status = 'cleared'
JOIN images ai ON ai.id = p.after_image_id AND ai.status = 'cleared'
WHERE NOT p.is_deleted
  AND NOT p.is_hidden;

-- Restore original feed_trending without user columns
DROP FUNCTION IF EXISTS feed_trending(double precision, timestamptz, uuid, int);
CREATE OR REPLACE FUNCTION feed_trending(
    p_cursor_score  DOUBLE PRECISION DEFAULT NULL,
    p_cursor_created TIMESTAMPTZ      DEFAULT NULL,
    p_cursor_id      UUID             DEFAULT NULL,
    p_limit          INT              DEFAULT 11
)
RETURNS TABLE (
    id               UUID,
    user_id          UUID,
    caption          TEXT,
    before_image_url TEXT,
    after_image_url  TEXT,
    reaction_count   INT,
    comment_count    INT,
    created_at       TIMESTAMPTZ,
    before_image_id  UUID,
    after_image_id   UUID,
    trending_score   DOUBLE PRECISION
)
LANGUAGE sql STABLE
AS $$
    WITH scored AS (
        SELECT
            fp.*,
            fp.reaction_count::double precision
              / POWER(EXTRACT(EPOCH FROM (NOW() - fp.created_at)) / 3600.0 + 2, 1.5)
              AS trending_score
        FROM v_feed_posts fp
        WHERE fp.created_at >= NOW() - INTERVAL '7 days'
    )
    SELECT s.*
    FROM scored s
    WHERE (p_cursor_score IS NULL)
       OR (s.trending_score < p_cursor_score)
       OR (s.trending_score = p_cursor_score AND s.created_at < p_cursor_created)
       OR (s.trending_score = p_cursor_score AND s.created_at = p_cursor_created AND s.id > p_cursor_id)
    ORDER BY s.trending_score DESC, s.created_at DESC, s.id ASC
    LIMIT p_limit;
$$;

-- Restore original feed_biggest_improvements without user columns
DROP FUNCTION IF EXISTS feed_biggest_improvements(int, timestamptz, uuid, int);
CREATE OR REPLACE FUNCTION feed_biggest_improvements(
    p_cursor_reactions INT         DEFAULT NULL,
    p_cursor_created   TIMESTAMPTZ DEFAULT NULL,
    p_cursor_id        UUID        DEFAULT NULL,
    p_limit            INT         DEFAULT 11
)
RETURNS TABLE (
    id               UUID,
    user_id          UUID,
    caption          TEXT,
    before_image_url TEXT,
    after_image_url  TEXT,
    reaction_count   INT,
    comment_count    INT,
    created_at       TIMESTAMPTZ,
    before_image_id  UUID,
    after_image_id   UUID
)
LANGUAGE sql STABLE
AS $$
    SELECT fp.*
    FROM v_feed_posts fp
    WHERE (p_cursor_reactions IS NULL)
       OR (fp.reaction_count < p_cursor_reactions)
       OR (fp.reaction_count = p_cursor_reactions AND fp.created_at < p_cursor_created)
       OR (fp.reaction_count = p_cursor_reactions AND fp.created_at = p_cursor_created AND fp.id > p_cursor_id)
    ORDER BY fp.reaction_count DESC, fp.created_at DESC, fp.id ASC
    LIMIT p_limit;
$$;
