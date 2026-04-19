"""Repository for the ``orphaned_analyses`` DLQ table.

When the ``DELETE /v1/jobs/{job_id}`` cascade finishes the ``DELETE FROM
jobs`` step but the follow-up ``DELETE FROM glowup_analyses`` raises,
the orphaned analysis id is recorded here so a future reclaim worker
can try again. See migration ``0047_orphaned_analyses.sql``.

Mirrors ``OrphanedStorageKeyRepository`` (DLQ for storage blobs) so the
sweeper — added in a follow-up PR — can treat both DLQs uniformly.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from supabase import Client

logger = logging.getLogger(__name__)


class OrphanedAnalysesRepository:
    """Thin wrapper around the DLQ table — callers are sync, use run_sync."""

    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record(self, analysis_id: str, reason: str) -> None:
        """Idempotently record an orphaned analysis id via UPSERT.

        Semantics: this is a first-insert-or-noop path. The UNIQUE
        constraint on ``analysis_id`` makes the upsert race-free —
        two concurrent first-writers cannot both succeed with
        incremented attempts. ``attempts`` is bumped exclusively by
        ``mark_attempt`` (called by the reclaim worker after a failed
        retry), not by ``record`` — this avoids the read-then-write
        race the prior implementation had between SELECT and INSERT/
        UPDATE. A repeated ``record`` call is a no-op update of
        ``reason`` only — ``attempts`` is NOT in the upsert payload,
        so ``ON CONFLICT DO UPDATE`` leaves it untouched. This means a
        re-record cannot accidentally erase a ``mark_attempt``
        increment made by the reclaim worker.

        Mirrors ``OrphanedStorageKeyRepository.record`` — same shape,
        same never-raise posture, same reason-string hygiene.
        """
        try:
            (
                self._sb.table("orphaned_analyses")
                .upsert(
                    {
                        "analysis_id": analysis_id,
                        "reason": reason,
                    },
                    on_conflict="analysis_id",
                )
                .execute()
            )
        except Exception:  # noqa: BLE001 — defensive last-ditch logging
            logger.exception(
                "Failed to record orphaned analysis %s (reason=%s) — row may "
                "leak until manual cleanup",
                analysis_id,
                reason,
            )

    # ------------------------------------------------------------------
    # Read (reclaim worker)
    # ------------------------------------------------------------------

    def list_pending(
        self, limit: int, max_attempts: int | None = None
    ) -> list[dict[str, Any]]:
        """Return up to ``limit`` DLQ rows, oldest first.

        When ``max_attempts`` is provided, rows whose ``attempts`` column
        is at or above the ceiling are filtered out at the DB layer.
        Without this filter the oldest-first ORDER BY would pin exhausted
        rows to the head of the batch forever, starving the sweeper of
        retryable work (the ``test_skips_rows_at_attempt_ceiling`` client-
        side guard still covers the defence-in-depth case).

        Aligns the signature with
        :meth:`OrphanedStorageKeyRepository.list_pending`.
        """
        query = self._sb.table("orphaned_analyses").select(
            "id, analysis_id, reason, attempts, inserted_at, last_attempt_at"
        )
        if max_attempts is not None:
            query = query.lt("attempts", max_attempts)
        result = query.order("inserted_at", desc=False).limit(limit).execute()
        return result.data or []

    # ------------------------------------------------------------------
    # Update / delete
    # ------------------------------------------------------------------

    def delete(self, analysis_id: str) -> None:
        """Remove a DLQ row once the analysis delete succeeded.

        Keyed on ``analysis_id`` (not the surrogate ``id``) because
        callers at the sweeper sight already hold the analysis id; an
        extra join to resolve the PK would add nothing.
        """
        (
            self._sb.table("orphaned_analyses")
            .delete()
            .eq("analysis_id", analysis_id)
            .execute()
        )

    def mark_attempt(self, analysis_id: str) -> None:
        """Bump ``attempts`` and set ``last_attempt_at`` after a failed retry.

        Sole bump path: ``record`` is race-free upsert (first-insert-or-
        noop; attempts=0), so the attempt counter only moves here. The
        reclaim worker calls this after a retry didn't clear. Read-then-
        write because supabase-py does not expose column arithmetic on
        update; the nightly sweeper can absorb the extra round-trip.
        """
        now = datetime.now(tz=timezone.utc).isoformat()
        current = (
            self._sb.table("orphaned_analyses")
            .select("attempts")
            .eq("analysis_id", analysis_id)
            .maybe_single()
            .execute()
        )
        if not current or not current.data:
            return
        next_attempts = int(current.data.get("attempts", 0)) + 1
        (
            self._sb.table("orphaned_analyses")
            .update({"attempts": next_attempts, "last_attempt_at": now})
            .eq("analysis_id", analysis_id)
            .execute()
        )
