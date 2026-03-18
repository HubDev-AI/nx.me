-- Migration: drop legacy glow_up_jobs image columns
-- Resolves schema drift between 0001 (before_image_id / after_image_id)
-- and 0006 (original_image_id / generated_image_id).
-- All application code already uses original_image_id / generated_image_id.
-- The posts table retains its own before_image_id / after_image_id (unrelated).

-- ============================================================
-- UP
-- ============================================================

ALTER TABLE glow_up_jobs
    DROP COLUMN IF EXISTS before_image_id,
    DROP COLUMN IF EXISTS after_image_id;

-- DOWN (rollback):
-- ALTER TABLE glow_up_jobs
--     ADD COLUMN IF NOT EXISTS before_image_id UUID REFERENCES images(id),
--     ADD COLUMN IF NOT EXISTS after_image_id  UUID REFERENCES images(id);
