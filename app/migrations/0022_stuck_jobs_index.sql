-- Composite index for watchdog stuck job query (L-7)
CREATE INDEX IF NOT EXISTS idx_glow_up_jobs_status_updated
  ON glow_up_jobs (status, updated_at)
  WHERE status IN ('processing', 'finalizing');

-- DOWN:
DROP INDEX IF EXISTS idx_glow_up_jobs_status_updated;
