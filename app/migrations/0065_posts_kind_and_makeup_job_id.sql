-- 0065_posts_kind_and_makeup_job_id.sql
-- Extends the posts table for the makeup data model.
-- All statements execute inside the migration runner's implicit transaction
-- (app/migrations/run.py sets autocommit=False with a single commit at end).
-- No explicit BEGIN/COMMIT needed or allowed inside this file.
--
-- Statement order is load-bearing:
--   1. DROP NOT NULL on glow_up_job_id first — required before the XOR CHECK
--      below can allow glow_up_job_id=NULL on makeup rows.
--   2. ADD COLUMN kind — DEFAULT 'glowup' backfills existing rows instantly
--      (non-volatile constant, no table rewrite in PG11+).
--   3. ADD COLUMN makeup_job_id — NULL for all existing rows, no scan needed.
--   4. ADD COLUMN public_index_opt_in — DEFAULT false.
--   5. ADD COLUMN publish_rev — DEFAULT 1.
--   6. ADD CONSTRAINT posts_job_xor NOT VALID then VALIDATE — avoids
--      ACCESS EXCLUSIVE full-table scan; VALIDATE takes SHARE UPDATE EXCLUSIVE
--      (non-blocking for concurrent readers/writers). Existing rows have
--      non-null glow_up_job_id and null makeup_job_id so validation is a
--      no-op pass.
--   7. CREATE UNIQUE INDEX — plain (non-CONCURRENTLY) matching the codebase
--      convention at 0046 (CONCURRENTLY is prohibited inside a transaction).

-- 1. Allow glow_up_job_id to be NULL so makeup rows can omit it
ALTER TABLE posts ALTER COLUMN glow_up_job_id DROP NOT NULL;

-- 2. Discriminator column — DEFAULT handles all existing rows as 'glowup'
ALTER TABLE posts
    ADD COLUMN IF NOT EXISTS kind text NOT NULL DEFAULT 'glowup'
        CHECK (kind IN ('glowup', 'makeup'));

-- 3. Makeup FK — NULL for all existing glowup rows
ALTER TABLE posts
    ADD COLUMN IF NOT EXISTS makeup_job_id uuid
        REFERENCES jobs(id) ON DELETE CASCADE;

-- 4. Social graph opt-in flag
ALTER TABLE posts
    ADD COLUMN IF NOT EXISTS public_index_opt_in boolean NOT NULL DEFAULT false;

-- 5. Optimistic-lock revision counter
ALTER TABLE posts
    ADD COLUMN IF NOT EXISTS publish_rev integer NOT NULL DEFAULT 1;

-- 6a. Add XOR constraint without validating (avoids ACCESS EXCLUSIVE full scan)
ALTER TABLE posts
    DROP CONSTRAINT IF EXISTS posts_job_xor;

ALTER TABLE posts
    ADD CONSTRAINT posts_job_xor
        CHECK ((glow_up_job_id IS NOT NULL) <> (makeup_job_id IS NOT NULL))
        NOT VALID;

-- 6b. Validate under SHARE UPDATE EXCLUSIVE — non-blocking
ALTER TABLE posts VALIDATE CONSTRAINT posts_job_xor;

-- 7. Unique index for live makeup posts (mirrors 0046's glowup index shape)
CREATE UNIQUE INDEX IF NOT EXISTS idx_posts_live_makeup_job_id
    ON posts (makeup_job_id)
    WHERE makeup_job_id IS NOT NULL
      AND is_deleted = FALSE
      AND is_hidden = FALSE;
