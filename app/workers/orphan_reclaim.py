"""Nightly reclaim worker — drains ``orphaned_storage_keys`` DLQ.

Rows in the DLQ are blobs whose primary DB insert failed AND whose inline
cleanup delete also failed (see ``app/image_pipeline/pipeline.py``). This
worker retries the storage delete with a capped attempt budget so orphan
blobs do not accumulate forever.

Scheduling: nightly cron (configured in ``app/worker_settings.py``).

Failure modes handled:

- Delete succeeds → DLQ row is removed.
- Delete raises → ``attempts`` is incremented; row stays for the next run.
- Row's attempts already at ceiling → ignored by this worker (left for
  operator review via the existing logs).
"""

from __future__ import annotations

import logging

from app.config import settings
from app.repositories.image_repo import ImageRepository
from app.repositories.orphaned_storage_repo import OrphanedStorageKeyRepository

logger = logging.getLogger(__name__)


async def reclaim_orphaned_blobs(ctx: dict) -> None:
    """ARQ cron: retry pending DLQ rows up to the configured ceiling."""
    supabase = ctx.get("supabase")
    if supabase is None:
        logger.warning("orphan reclaim skipped — no supabase client in ctx")
        return

    orphan_repo = OrphanedStorageKeyRepository(supabase)
    image_repo = ImageRepository(supabase)

    max_attempts = settings.ORPHAN_RECLAIM_MAX_ATTEMPTS
    batch_size = settings.ORPHAN_RECLAIM_BATCH_SIZE

    pending = orphan_repo.list_pending(max_attempts=max_attempts, limit=batch_size)

    reclaimed = 0
    failed = 0
    for row in pending:
        row_id = row["id"]
        bucket = row["bucket"]
        storage_key = row["storage_key"]
        try:
            image_repo.remove(bucket, [storage_key])
            orphan_repo.delete(row_id)
            reclaimed += 1
        except Exception:  # noqa: BLE001 — per-row defence; continue with next row
            logger.exception(
                "Orphan reclaim failed for %s/%s (row=%s)",
                bucket,
                storage_key,
                row_id,
            )
            orphan_repo.mark_attempt(row_id)
            failed += 1

    exhausted = orphan_repo.count_exhausted(max_attempts=max_attempts)
    logger.info(
        "orphan reclaim: reclaimed=%d failed=%d exhausted=%d",
        reclaimed,
        failed,
        exhausted,
    )
