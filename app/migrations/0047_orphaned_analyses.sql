-- 0047_orphaned_analyses.sql
--
-- Dead-letter queue for ``glowup_analyses`` rows whose best-effort delete
-- inside ``DELETE /v1/jobs/{job_id}`` failed. Mirrors migration 0036's
-- ``orphaned_storage_keys`` shape one-to-one, just swapping (bucket,
-- storage_key) for a single analysis_id foreign identifier. A future
-- reclaim worker drains it — out of scope here; this PR only adds the
-- write-side so the sweeper's job stays trivial when it lands.
--
-- Why a DLQ at all: the endpoint already swallow-logs analysis-delete
-- failures (an orphan analysis row is recoverable; aborting the request
-- mid-cascade after ``DELETE FROM jobs`` already committed would leave a
-- far uglier half-deleted state). But swallow-and-log alone gives
-- observability zero — the sweeper backstop needs a durable record.

CREATE TABLE IF NOT EXISTS orphaned_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID NOT NULL,
    reason TEXT NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TIMESTAMPTZ,
    CONSTRAINT orphaned_analyses_unique UNIQUE (analysis_id)
);

-- Reclaim worker picks up rows that still have budget — same index
-- pattern as ``orphaned_storage_keys`` so the sweeper's query shape is
-- identical across both DLQs.
CREATE INDEX IF NOT EXISTS orphaned_analyses_attempts_idx
    ON orphaned_analyses (attempts, inserted_at);

-- DOWN:
DO $$
BEGIN
    RAISE EXCEPTION
        'migration 0047 is destructive and has no down path — use `make nuke` and re-run forward migrations';
END
$$;
