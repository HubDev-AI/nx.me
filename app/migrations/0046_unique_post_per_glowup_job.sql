-- 0046_unique_post_per_glowup_job.sql
--
-- Add a partial UNIQUE index on posts.glow_up_job_id so at most one LIVE
-- post (is_deleted = FALSE AND is_hidden = FALSE) can exist per glow-up
-- job. Prevents the client race where a double-tap on Publish produces
-- two public posts for the same job, which would then both appear in the
-- feed under the same user.
--
-- The index is PARTIAL on purpose — if the first post is soft-deleted or
-- auto-hidden (report threshold), the user can re-publish. Otherwise a
-- moderation hit would permanently block that job from the feed with no
-- path forward, and a user who hit Delete would be unable to Publish a
-- different job variant.
--
-- Unit 2 (follow-up) teaches POST /v1/posts to catch unique_violation on
-- this index and return the existing live post as caller-idempotency.
-- Pre-launch per `feedback_pre_launch_destructive_ok` — no live users,
-- so the dedup below is defensive (should be a no-op in dev).
--
-- FK invariants relied on by the delete cascade plan (verified live in
-- the accompanying tests, not re-declared here — they already exist):
--   posts.glow_up_job_id → jobs(id) ON DELETE CASCADE (migration 0045)
--   reactions.post_id    → posts(id) ON DELETE CASCADE (migration 0001)
--   comments.post_id     → posts(id) ON DELETE CASCADE (migration 0001)
--   reports.post_id      → posts(id) ON DELETE CASCADE (migration 0045)

-- UP

-- Defensive: if duplicate LIVE posts exist for the same glow_up_job_id,
-- keep the earliest-created one and soft-delete the rest before creating
-- the unique index. Pre-launch — expected no-op in dev.
WITH ranked AS (
    SELECT
        id,
        row_number() OVER (
            PARTITION BY glow_up_job_id
            ORDER BY created_at ASC, id ASC
        ) AS rn
    FROM posts
    WHERE is_deleted = FALSE
      AND is_hidden = FALSE
)
UPDATE posts
   SET is_deleted = TRUE,
       updated_at = NOW()
 WHERE id IN (SELECT id FROM ranked WHERE rn > 1);

-- Partial UNIQUE index: at most one live post per glow-up job.
-- Soft-deleted / auto-hidden posts do not participate, permitting
-- re-publish after moderation or user-initiated post-delete.
CREATE UNIQUE INDEX idx_posts_live_glow_up_job_id
    ON posts (glow_up_job_id)
    WHERE is_deleted = FALSE AND is_hidden = FALSE;

-- DOWN:
DO $$
BEGIN
    RAISE EXCEPTION
        'migration 0046 is destructive and has no down path — use `make nuke` and re-run forward migrations';
END
$$;
