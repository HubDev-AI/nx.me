-- 0039_jobs_identity_preserved.sql
-- Migration 0034 restructured the jobs table via DROP+RECREATE and lost the
-- identity_preserved BOOLEAN column. Worker code (app/generation/worker.py)
-- still writes it on finalize, causing every generation to fail post-image
-- step with:
--
--   PGRST204 "Could not find the 'identity_preserved' column of 'jobs'"
--
-- and the job to get stuck in 'finalizing' forever — the mobile app polls
-- GET /v1/jobs/{id} indefinitely and never sees a result.
--
-- The column is intentional: we store the ArcFace identity-preservation
-- outcome alongside each job (see app/generation/identity_checker.py and
-- docs/architecture.md §D4). Restore it here.

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS identity_preserved BOOLEAN;

-- rollback:
-- ALTER TABLE jobs DROP COLUMN IF EXISTS identity_preserved;
