-- Migration: add is_hidden filter to v_feed_posts view
-- Ensures auto-hidden and admin-hidden posts are excluded from all feed queries
-- (trending, biggest improvements) that use this view.

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
