"""wipe_deleted_user_blobs — ARQ job that drains blob-wipe work for large users.

Invoked by delete_account when total blob count exceeds the inline threshold.
Chunks image_repo.remove into 250-key batches; failures go to the orphan DLQ.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.workers.delete_account_blobs import wipe_deleted_user_blobs


@pytest.mark.asyncio
async def test_chunks_remove_and_dlqs_failures():
    image_repo = MagicMock()
    orphan_repo = MagicMock()

    # 600 keys in raw-selfies; 200 in generated-images.
    # Chunk size 250 → raw-selfies yields 3 chunks (250, 250, 100),
    # generated-images yields 1 chunk (200). Total 4 remove() calls.
    # Fail the second raw-selfies chunk — 250 keys to DLQ.
    image_repo.remove.side_effect = [
        None,  # raw-selfies chunk 1 (250) succeeds
        RuntimeError("boom"),  # raw-selfies chunk 2 (250) fails → DLQ each
        None,  # raw-selfies chunk 3 (100) succeeds
        None,  # generated-images chunk 1 (200) succeeds
    ]

    ctx = {"image_repo": image_repo, "orphan_repo": orphan_repo}
    keys_by_bucket = {
        "raw-selfies": [f"u-1/raw/{i}.jpg" for i in range(600)],
        "generated-images": [f"u-1/gen/{i}.jpg" for i in range(200)],
        "post-images": [],
        "avatars": [],
    }

    await wipe_deleted_user_blobs(ctx, user_id="u-1", keys_by_bucket=keys_by_bucket)

    assert image_repo.remove.call_count == 4
    assert orphan_repo.record.call_count == 250
    # Verify every DLQ call records the correct bucket + reason + the
    # failed chunk's keys. A weaker assertion would accept a bucket
    # swap or missing reason, which would silently break the
    # nightly reclaim worker's filtering.
    first_call = orphan_repo.record.call_args_list[0]
    assert first_call.args[0] == "raw-selfies"
    assert first_call.args[1] == "u-1/raw/250.jpg"
    assert first_call.args[2] == "delete_account"
    # Bucket + reason should be consistent across every DLQ call for
    # this chunk, so any off-by-one in the loop body surfaces.
    for call in orphan_repo.record.call_args_list:
        assert call.args[0] == "raw-selfies"
        assert call.args[2] == "delete_account"


@pytest.mark.asyncio
async def test_empty_buckets_are_no_ops():
    image_repo = MagicMock()
    orphan_repo = MagicMock()

    ctx = {"image_repo": image_repo, "orphan_repo": orphan_repo}
    keys_by_bucket = {
        "raw-selfies": [],
        "generated-images": [],
        "post-images": [],
        "avatars": [],
    }

    await wipe_deleted_user_blobs(ctx, user_id="u-1", keys_by_bucket=keys_by_bucket)

    image_repo.remove.assert_not_called()
    orphan_repo.record.assert_not_called()


@pytest.mark.asyncio
async def test_partial_chunk_under_size_limit_still_removed():
    """A bucket with 50 keys < _CHUNK_SIZE should still issue one remove()."""
    image_repo = MagicMock()
    orphan_repo = MagicMock()

    ctx = {"image_repo": image_repo, "orphan_repo": orphan_repo}
    keys_by_bucket = {"avatars": [f"u-1/avatar/{i}.jpg" for i in range(50)]}

    await wipe_deleted_user_blobs(ctx, user_id="u-1", keys_by_bucket=keys_by_bucket)

    image_repo.remove.assert_called_once_with(
        "avatars", [f"u-1/avatar/{i}.jpg" for i in range(50)]
    )
    orphan_repo.record.assert_not_called()
