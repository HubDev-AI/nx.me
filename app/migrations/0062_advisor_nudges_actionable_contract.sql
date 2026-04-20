-- 0062_advisor_nudges_actionable_contract.sql
-- Nudges v2: actionable nudges + novelty dedup.
--
-- Reshapes advisor_nudges for the new {body, next_step.{label, seed}} contract.
-- Pre-launch (zero production data): TRUNCATE in place, then drop/add columns.
-- No backfill, no nullable shim, no dual-contract window. See
-- docs/plans/2026-04-20-001-feat-nudges-v2-actionable-plan.md Unit 1.
--
-- Changes:
--   - TRUNCATE advisor_nudges.
--   - Drop columns: observation_tag, trigger.
--   - Rename content -> body, enforce VARCHAR(160) length cap.
--   - Add next_step_label VARCHAR(24) NOT NULL.
--   - Add next_step_seed VARCHAR(140) NOT NULL.
--   - Add body_hash VARCHAR(64) NOT NULL.
--   - Add index (user_id, body_hash) for the 30-day dedup lookup.
--
-- Idempotent: every step guards against re-application. Originally numbered
-- 0059; renamed to 0062 after a merge with dev added three new migrations
-- in the 0059-0061 slots. Environments that already applied the 0059
-- version can re-run this as 0062 without error.

TRUNCATE TABLE advisor_nudges;

ALTER TABLE advisor_nudges
    DROP COLUMN IF EXISTS observation_tag,
    DROP COLUMN IF EXISTS trigger;

-- Rename content -> body (idempotent via column-existence check).
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM   information_schema.columns
        WHERE  table_name  = 'advisor_nudges'
          AND  column_name = 'content'
    ) THEN
        ALTER TABLE advisor_nudges RENAME COLUMN content TO body;
    END IF;
END$$;

ALTER TABLE advisor_nudges
    ALTER COLUMN body TYPE VARCHAR(160);

ALTER TABLE advisor_nudges
    ADD COLUMN IF NOT EXISTS next_step_label VARCHAR(24),
    ADD COLUMN IF NOT EXISTS next_step_seed  VARCHAR(140),
    ADD COLUMN IF NOT EXISTS body_hash       VARCHAR(64);

-- NOT NULL applied in a second pass so IF NOT EXISTS + NOT NULL both hold.
-- The TRUNCATE above leaves the table empty, so no backfill is needed.
ALTER TABLE advisor_nudges
    ALTER COLUMN next_step_label SET NOT NULL,
    ALTER COLUMN next_step_seed  SET NOT NULL,
    ALTER COLUMN body_hash       SET NOT NULL;

CREATE INDEX IF NOT EXISTS ix_advisor_nudges_user_body_hash
    ON advisor_nudges (user_id, body_hash);

-- DOWN:
-- Pre-launch destructive migration; DOWN restores schema shape but not data.
-- TRUNCATE TABLE advisor_nudges;
-- DROP INDEX IF EXISTS ix_advisor_nudges_user_body_hash;
-- ALTER TABLE advisor_nudges
--     DROP COLUMN IF EXISTS body_hash,
--     DROP COLUMN IF EXISTS next_step_seed,
--     DROP COLUMN IF EXISTS next_step_label;
-- ALTER TABLE advisor_nudges
--     ALTER COLUMN body TYPE TEXT;
-- ALTER TABLE advisor_nudges
--     RENAME COLUMN body TO content;
-- ALTER TABLE advisor_nudges
--     ADD COLUMN trigger TEXT NOT NULL DEFAULT 'post_glowup',
--     ADD COLUMN observation_tag TEXT;
