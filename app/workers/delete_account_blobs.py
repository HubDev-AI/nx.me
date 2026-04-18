"""ARQ job: wipe a deleted user's blobs in chunked batches.

Invoked by DELETE /auth/account when the user's total blob count exceeds
the inline-wipe threshold (~500). Chunks each bucket into batches of
_CHUNK_SIZE keys; failed batches enqueue every key in the orphan DLQ so
the nightly reclaim worker can retry.

``image_repo.remove`` and ``orphan_repo.record`` are sync Supabase client
calls. They're wrapped in ``asyncio.to_thread`` so the ARQ worker's
event loop can still service other jobs while the Supabase round-trip
is in flight — without that, a single wipe blocks the pool for every
chunk's HTTP call.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 250


async def wipe_deleted_user_blobs(
    ctx: dict,
    *,
    user_id: str,
    keys_by_bucket: dict[str, list[str]],
) -> None:
    image_repo = ctx["image_repo"]
    orphan_repo = ctx["orphan_repo"]

    wiped = 0
    failed = 0
    for bucket, keys in keys_by_bucket.items():
        for start in range(0, len(keys), _CHUNK_SIZE):
            chunk = keys[start : start + _CHUNK_SIZE]
            try:
                await asyncio.to_thread(image_repo.remove, bucket, chunk)
                wiped += len(chunk)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "wipe_deleted_user_blobs: bucket %s chunk [%d:%d] failed for %s: %s",
                    bucket,
                    start,
                    start + len(chunk),
                    user_id,
                    exc,
                )
                for key in chunk:
                    await asyncio.to_thread(
                        orphan_repo.record, bucket, key, "delete_account"
                    )
                failed += len(chunk)

    logger.info(
        "wipe_deleted_user_blobs: user=%s wiped=%d failed=%d",
        user_id,
        wiped,
        failed,
    )
