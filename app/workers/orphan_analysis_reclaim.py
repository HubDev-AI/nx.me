"""Nightly reclaim worker — drains ``orphaned_analyses`` DLQ.

Rows in the DLQ are ``glowup_analyses`` ids whose best-effort delete
inside ``DELETE /v1/jobs/{job_id}`` failed after the ``DELETE FROM jobs``
cascade already committed (see ``app/api/jobs.py``). This worker retries
the analysis delete with a capped attempt budget so orphan rows do not
accumulate forever.

Scheduling: nightly cron (configured in ``app/worker_settings.py``).

Shape mirrors ``app/workers/orphan_reclaim.py`` deliberately — grep for
DLQ-sweeper patterns should surface both workers. Divergences:

- ``jobs.source_id`` → ``glowup_analyses.id`` is a plain UUID (no FK).
  By the time a DLQ row exists, the jobs row is already cascaded away,
  so the only retry blockers are transient DB issues or RLS — both
  resolve naturally or hit ``MAX_ATTEMPTS``. See
  ``JobRepository.delete_analysis_by_id`` docstring.
- ``OrphanedAnalysesRepository.list_pending(limit, max_attempts)``
  filters exhausted rows DB-side (aligned with its blob sibling) to
  avoid oldest-first ORDER BY pinning exhausted rows at the head of
  the batch forever. The client-side ``if attempts >= MAX`` guard
  stays as defence-in-depth.
- ``delete`` / ``mark_attempt`` are keyed on ``analysis_id``, not on the
  surrogate row id — per the repo's docstring, callers already hold the
  analysis id so a PK lookup adds nothing.

Failure modes handled:

- Delete succeeds → DLQ row is removed.
- Delete raises → ``attempts`` is incremented; row stays for the next run.
- Row's attempts already at ceiling → ignored by this worker (left for
  operator review via the WARN log emitted on the last recorded attempt).
"""

from __future__ import annotations

import logging

from app.config import settings
from app.repositories.job_repo import JobRepository
from app.repositories.orphaned_analyses_repo import OrphanedAnalysesRepository

logger = logging.getLogger(__name__)


async def reclaim_orphaned_analyses(ctx: dict) -> None:
    """ARQ cron: retry pending DLQ rows up to the configured ceiling."""
    supabase = ctx.get("supabase")
    if supabase is None:
        logger.warning("orphan analysis reclaim skipped — no supabase client in ctx")
        return

    orphan_repo = OrphanedAnalysesRepository(supabase)
    job_repo = JobRepository(supabase)

    max_attempts = settings.ORPHAN_ANALYSIS_RECLAIM_MAX_ATTEMPTS
    batch_size = settings.ORPHAN_ANALYSIS_RECLAIM_BATCH_SIZE

    # DB-side attempts filter keeps the oldest-first ORDER BY from
    # pinning exhausted rows at the head of the batch. Aligned with
    # OrphanedStorageKeyRepository.list_pending's signature. The
    # client-side guard below stays as defence-in-depth (a test forces
    # list_pending to return an exhausted row to verify the skip).
    pending = orphan_repo.list_pending(limit=batch_size, max_attempts=max_attempts)

    reclaimed = 0
    failed = 0
    skipped_exhausted = 0

    for row in pending:
        analysis_id = row["analysis_id"]
        attempts = int(row.get("attempts", 0))

        if attempts >= max_attempts:
            skipped_exhausted += 1
            continue

        try:
            job_repo.delete_analysis_by_id(analysis_id)
            orphan_repo.delete(analysis_id)
            reclaimed += 1
        except Exception:  # noqa: BLE001 — per-row defence; continue with next row
            logger.exception(
                "Orphan analysis reclaim failed for analysis_id=%s",
                analysis_id,
            )
            orphan_repo.mark_attempt(analysis_id)
            failed += 1

            # Operator-review signal: surface rows as they cross the
            # ceiling so they don't silently rot in the DLQ.
            if attempts + 1 >= max_attempts:
                logger.warning(
                    "Orphan analysis %s hit attempt ceiling (%d) — manual "
                    "cleanup required",
                    analysis_id,
                    max_attempts,
                )

    logger.info(
        "orphan analysis reclaim: reclaimed=%d failed=%d skipped_exhausted=%d",
        reclaimed,
        failed,
        skipped_exhausted,
    )
