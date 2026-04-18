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
        """Idempotently record an orphaned analysis id.

        First call inserts a row with ``attempts = 0``. Subsequent calls
        for the same ``analysis_id`` bump ``attempts`` and refresh
        ``last_attempt_at`` so the sweeper can tell repeat-failure rows
        apart from never-retried ones.

        Concurrency posture: read-then-write is race-prone under truly
        simultaneous first-writers (both SELECT miss, both INSERT, one
        hits ``UNIQUE(analysis_id)`` and the violation is swallowed by
        the outer except — that writer's bump is lost). Acceptable on
        this error path: the row still lands, the sweeper still finds
        it, and a lost bump just means one sweeper cycle thinks a row
        is fresher than it is. Not worth an RPC+trigger round-trip to
        close.

        supabase-py does not expose ``ON CONFLICT DO UPDATE SET column =
        column + 1`` so the increment is done Python-side in two steps.
        Two round-trips are fine here — this is an error path, not a
        hot loop.

        Never raises — failure here would mask the primary error the
        caller is already swallow-logging (mirrors
        ``OrphanedStorageKeyRepository.record``).
        """
        try:
            existing = (
                self._sb.table("orphaned_analyses")
                .select("id, attempts")
                .eq("analysis_id", analysis_id)
                .maybe_single()
                .execute()
            )
            if existing and existing.data:
                # Row already present — bump attempts, refresh last_attempt_at.
                current_attempts = int(existing.data.get("attempts", 0))
                now_iso = datetime.now(tz=timezone.utc).isoformat()
                (
                    self._sb.table("orphaned_analyses")
                    .update(
                        {
                            "attempts": current_attempts + 1,
                            "last_attempt_at": now_iso,
                            "reason": reason,
                        }
                    )
                    .eq("analysis_id", analysis_id)
                    .execute()
                )
            else:
                (
                    self._sb.table("orphaned_analyses")
                    .insert(
                        {
                            "analysis_id": analysis_id,
                            "reason": reason,
                        }
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

    def list_pending(self, limit: int) -> list[dict[str, Any]]:
        """Return up to ``limit`` DLQ rows, oldest first.

        No ``max_attempts`` filter yet — the sweeper ships in a follow-up
        PR and can add ceiling logic there. Present now so tests can
        sanity-check that ``record`` actually landed a row.
        """
        result = (
            self._sb.table("orphaned_analyses")
            .select("id, analysis_id, reason, attempts, inserted_at, last_attempt_at")
            .order("inserted_at", desc=False)
            .limit(limit)
            .execute()
        )
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

        Distinct from ``record``: ``record`` is called on the write-path
        failure, ``mark_attempt`` by the reclaim worker after a retry
        didn't clear. Same two-step read-then-write for the same
        supabase-py column-arithmetic reason documented on ``record``.
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
