-- Add 'finalizing' to glow_up_jobs status CHECK constraint.
-- The worker transitions jobs to 'finalizing' after generation succeeds
-- but before the final DB update (identity check, image storage).

ALTER TABLE glow_up_jobs
    DROP CONSTRAINT IF EXISTS glow_up_jobs_status_check;

ALTER TABLE glow_up_jobs
    ADD CONSTRAINT glow_up_jobs_status_check
    CHECK (status IN (
        'pending', 'queued', 'processing', 'finalizing',
        'completed', 'failed', 'cancelled'
    ));
