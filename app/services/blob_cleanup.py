"""Shared blob-wipe helper with orphan-DLQ fallback.

Extracts the try/``image_repo.remove``/except/log/``orphan_repo.record``/
inner-except shape that was duplicated between
:func:`app.api.jobs.delete_job` and :func:`app.workers.retention.run_retention`.

The helper keeps the three invariants both call sites rely on:

- Delete the blob via :meth:`ImageRepository.remove` on the happy path.
- On storage failure, fall through to
  :meth:`OrphanedStorageKeyRepository.record` with the caller's reason
  so the nightly reclaim worker drains it later.
- Never raise. The primary request path must not fail when a single
  blob wipe misses — the FK cascade / DB row is already gone and the
  DLQ is the durable recovery handle.
"""

from __future__ import annotations

import logging

from app.db.async_helpers import run_sync
from app.repositories.image_repo import ImageRepository
from app.repositories.orphaned_storage_repo import OrphanedStorageKeyRepository

logger = logging.getLogger(__name__)


async def wipe_blob_or_record_orphan(
    image_repo: ImageRepository,
    orphan_repo: OrphanedStorageKeyRepository,
    bucket: str,
    storage_key: str,
    reason: str,
) -> bool:
    """Delete ``bucket/storage_key`` or record it to the orphan DLQ.

    Returns ``True`` when the storage delete succeeded, ``False`` when
    the blob landed in the DLQ instead. Callers can use the return
    value to increment wipe/DLQ counters for observability (the
    retention worker already does; the delete_job endpoint logs only).

    The DLQ write is itself defensive — :meth:`OrphanedStorageKeyRepository.record`
    swallow-logs any exception — but we wrap it in a broad try/except
    anyway so a theoretical regression in the repo can never propagate
    into the caller's request path.
    """
    try:
        await run_sync(image_repo.remove, bucket, [storage_key])
        return True
    except Exception as exc:  # noqa: BLE001 — wide net on purpose
        logger.warning(
            "blob wipe failed for %s/%s: %s — recording to DLQ",
            bucket,
            storage_key,
            exc,
        )
        try:
            await run_sync(orphan_repo.record, bucket, storage_key, reason)
        except Exception as record_exc:  # noqa: BLE001 — defensive last-ditch
            logger.warning(
                "DLQ record also failed for %s/%s: %s",
                bucket,
                storage_key,
                record_exc,
            )
        return False


def wipe_blob_or_record_orphan_sync(
    image_repo: ImageRepository,
    orphan_repo: OrphanedStorageKeyRepository,
    bucket: str,
    storage_key: str,
    reason: str,
) -> bool:
    """Sync variant of :func:`wipe_blob_or_record_orphan`.

    Exists because the nightly retention worker (``ARQ`` task body
    already-async) still calls directly into the sync Supabase client
    without :func:`run_sync`. Keeping a parallel sync helper avoids an
    awkward ``asyncio.run`` hop inside the worker.
    """
    try:
        image_repo.remove(bucket, [storage_key])
        return True
    except Exception as exc:  # noqa: BLE001 — wide net on purpose
        logger.warning(
            "blob wipe failed for %s/%s: %s — recording to DLQ",
            bucket,
            storage_key,
            exc,
        )
        try:
            orphan_repo.record(bucket, storage_key, reason)
        except Exception as record_exc:  # noqa: BLE001 — defensive last-ditch
            logger.warning(
                "DLQ record also failed for %s/%s: %s",
                bucket,
                storage_key,
                record_exc,
            )
        return False
