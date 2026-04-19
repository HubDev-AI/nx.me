"""Repository for the ``orphaned_storage_keys`` DLQ table.

When the image pipeline writes a blob to storage but the follow-up DB
insert fails AND the inline cleanup delete also fails, the blob is
recorded here so a nightly reclaim worker can try again. See migration
``0036_orphaned_storage_keys.sql`` and ``app/workers/orphan_reclaim.py``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from supabase import Client

logger = logging.getLogger(__name__)


class OrphanedStorageKeyRepository:
    """Thin wrapper around the DLQ table — callers are sync, use run_sync."""

    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record(self, bucket: str, storage_key: str, reason: str) -> None:
        """Idempotently record an orphaned blob.

        Safe to call from inline exception handlers — duplicate inserts
        silently succeed (the uniqueness constraint on bucket+storage_key
        makes retries a no-op). Never raises; failure here would mask the
        primary error the caller is already re-raising.
        """
        try:
            (
                self._sb.table("orphaned_storage_keys")
                .upsert(
                    {
                        "bucket": bucket,
                        "storage_key": storage_key,
                        "reason": reason,
                    },
                    on_conflict="bucket,storage_key",
                )
                .execute()
            )
        except Exception:  # noqa: BLE001 — defensive last-ditch logging
            logger.exception(
                "Failed to record orphaned storage key %s/%s (reason=%s) — blob may "
                "leak until manual cleanup",
                bucket,
                storage_key,
                reason,
            )

    # ------------------------------------------------------------------
    # Read (reclaim worker)
    # ------------------------------------------------------------------

    def list_pending(self, max_attempts: int, limit: int) -> list[dict[str, Any]]:
        """Return up to ``limit`` DLQ rows with ``attempts < max_attempts``, oldest first."""
        result = (
            self._sb.table("orphaned_storage_keys")
            .select("id, bucket, storage_key, reason, attempts")
            .lt("attempts", max_attempts)
            .order("inserted_at", desc=False)
            .limit(limit)
            .execute()
        )
        return result.data or []

    def count_exhausted(self, max_attempts: int) -> int:
        """Return the number of DLQ rows that have hit the attempt ceiling."""
        result = (
            self._sb.table("orphaned_storage_keys")
            .select("id", count="exact")
            .gte("attempts", max_attempts)
            .execute()
        )
        return int(result.count or 0)

    # ------------------------------------------------------------------
    # Update / delete
    # ------------------------------------------------------------------

    def delete(self, row_id: str) -> None:
        """Remove a DLQ row once the storage delete succeeded."""
        (self._sb.table("orphaned_storage_keys").delete().eq("id", row_id).execute())

    def delete_by_key(self, bucket: str, storage_key: str) -> None:
        """Remove a DLQ row by its ``(bucket, storage_key)`` pair.

        Used by publish-pending pre-records in ``POST /v1/posts`` — the
        caller records a row before committing the post insert so any
        TOCTOU / 409 / retry failure path leaves the upload in the DLQ.
        On successful insert the caller removes the row via this method.
        Safe on already-deleted keys (idempotent no-op delete).
        """
        (
            self._sb.table("orphaned_storage_keys")
            .delete()
            .eq("bucket", bucket)
            .eq("storage_key", storage_key)
            .execute()
        )

    def mark_attempt(self, row_id: str) -> None:
        """Bump ``attempts`` and set ``last_attempt_at`` after a failed retry."""
        now = datetime.now(tz=timezone.utc).isoformat()
        # Fetch current attempts first; Supabase-py doesn't expose column
        # arithmetic on update. Two round-trips are fine — reclaim is nightly.
        current = (
            self._sb.table("orphaned_storage_keys")
            .select("attempts")
            .eq("id", row_id)
            .maybe_single()
            .execute()
        )
        if not current or not current.data:
            return
        next_attempts = int(current.data.get("attempts", 0)) + 1
        (
            self._sb.table("orphaned_storage_keys")
            .update({"attempts": next_attempts, "last_attempt_at": now})
            .eq("id", row_id)
            .execute()
        )
