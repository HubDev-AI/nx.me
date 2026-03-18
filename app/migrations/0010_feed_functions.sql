-- Migration: feed_functions
-- Move feed ranking/filtering into SQL for performance.
-- Replaces Python-side image filtering and trending score computation.

-- 1. Helper view: posts with both images cleared (AC-D7)
-- Not a materialized view — just a filter pushdown so every feed query
-- doesn't repeat the same JOIN logic.
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
WHERE NOT p.is_deleted;


-- 2. RPC: trending feed with HN-style decay scored in SQL
--    score = reaction_count / POWER(hours_since_post + 2, 1.5)
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


-- 3. RPC: biggest improvements with proper cursor pagination
--    ORDER BY reaction_count DESC, created_at DESC, id ASC
--    Cursor = (reaction_count, created_at, id) tuple comparison
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


-- 4. Index to support image-status JOIN in the view
-- (status is low-cardinality so a partial index on 'cleared' is ideal)
CREATE INDEX IF NOT EXISTS idx_images_cleared
    ON images (id) WHERE status = 'cleared';

-- DOWN (rollback)
-- DROP INDEX IF EXISTS idx_images_cleared;
-- DROP FUNCTION IF EXISTS feed_biggest_improvements;
-- DROP FUNCTION IF EXISTS feed_trending;
-- DROP VIEW IF EXISTS v_feed_posts;
