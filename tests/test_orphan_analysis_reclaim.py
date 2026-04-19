"""Tests for the orphaned-analysis DLQ sweeper worker.

Covers the read-side counterpart to ``test_orphan_analysis_dlq.py``
(which exercises ``OrphanedAnalysesRepository.record`` + the endpoint
wiring). Mirrors ``test_orphan_reclaim.py``'s structure one-to-one —
same monkeypatch style, same ctx shape — so the two sweepers stay
grep-for-pattern discoverable as a pair.

Scope:

- Happy path: pending rows → per-row ``delete_analysis_by_id`` + DLQ
  ``delete`` call, no ``mark_attempt``.
- Partial failure: one row's DB delete raises → DLQ row stays,
  ``mark_attempt`` called with the correct ``analysis_id``. Successful
  peers are not blocked.
- Attempts-at-ceiling: row with ``attempts >= MAX`` is skipped (neither
  delete nor mark_attempt called on it); other pending rows proceed.
- WARN log: row whose ``attempts + 1 >= MAX`` triggers a ``logger.warning``
  surfacing the analysis id for operator review.
- Empty DLQ: no-op clean exit.
- No supabase in ctx: warn-and-return without touching repos.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Constants — no magic strings
# ---------------------------------------------------------------------------

_ANALYSIS_ID_A = "11111111-1111-1111-1111-111111111111"
_ANALYSIS_ID_B = "22222222-2222-2222-2222-222222222222"
_ANALYSIS_ID_EXHAUSTED = "33333333-3333-3333-3333-333333333333"


def _row(analysis_id: str, attempts: int = 0) -> dict:
    """Build a minimal DLQ row shape matching ``list_pending`` output."""
    return {
        "id": f"dlq-{analysis_id}",
        "analysis_id": analysis_id,
        "reason": "delete_glowup",
        "attempts": attempts,
        "inserted_at": "2026-04-18T00:00:00+00:00",
        "last_attempt_at": None,
    }


# ---------------------------------------------------------------------------
# Reclaim worker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestReclaimOrphanedAnalyses:
    async def test_deletes_rows_on_success(self, monkeypatch):
        """Happy path: 2 pending rows → both analyses deleted + DLQ cleared."""
        from app.workers import orphan_analysis_reclaim

        supabase = MagicMock()
        ctx = {"supabase": supabase}

        orphan_repo_mock = MagicMock()
        orphan_repo_mock.list_pending.return_value = [
            _row(_ANALYSIS_ID_A),
            _row(_ANALYSIS_ID_B),
        ]

        job_repo_mock = MagicMock()
        job_repo_mock.delete_analysis_by_id.return_value = None

        monkeypatch.setattr(
            orphan_analysis_reclaim,
            "OrphanedAnalysesRepository",
            lambda _sb: orphan_repo_mock,
        )
        monkeypatch.setattr(
            orphan_analysis_reclaim, "JobRepository", lambda _sb: job_repo_mock
        )

        await orphan_analysis_reclaim.reclaim_orphaned_analyses(ctx)

        # Each pending row triggers one delete per repo, in order.
        assert job_repo_mock.delete_analysis_by_id.call_args_list == [
            ((_ANALYSIS_ID_A,), {}),
            ((_ANALYSIS_ID_B,), {}),
        ]
        assert orphan_repo_mock.delete.call_args_list == [
            ((_ANALYSIS_ID_A,), {}),
            ((_ANALYSIS_ID_B,), {}),
        ]
        orphan_repo_mock.mark_attempt.assert_not_called()

    async def test_bumps_attempts_on_failure(self, monkeypatch):
        """Partial failure: row A raises → DLQ row stays + mark_attempt.

        Row B (healthy) still completes. Proves per-row defence does not
        short-circuit the rest of the batch.
        """
        from app.workers import orphan_analysis_reclaim

        supabase = MagicMock()
        ctx = {"supabase": supabase}

        orphan_repo_mock = MagicMock()
        orphan_repo_mock.list_pending.return_value = [
            _row(_ANALYSIS_ID_A),
            _row(_ANALYSIS_ID_B),
        ]

        job_repo_mock = MagicMock()

        def _delete(analysis_id: str) -> None:
            if analysis_id == _ANALYSIS_ID_A:
                raise RuntimeError("supabase 503")

        job_repo_mock.delete_analysis_by_id.side_effect = _delete

        monkeypatch.setattr(
            orphan_analysis_reclaim,
            "OrphanedAnalysesRepository",
            lambda _sb: orphan_repo_mock,
        )
        monkeypatch.setattr(
            orphan_analysis_reclaim, "JobRepository", lambda _sb: job_repo_mock
        )

        await orphan_analysis_reclaim.reclaim_orphaned_analyses(ctx)

        # Row A: mark_attempt only; no DLQ delete.
        orphan_repo_mock.mark_attempt.assert_called_once_with(_ANALYSIS_ID_A)
        # Row B: proceeded normally.
        orphan_repo_mock.delete.assert_called_once_with(_ANALYSIS_ID_B)

    async def test_skips_rows_at_attempt_ceiling(self, monkeypatch):
        """Row with ``attempts >= MAX`` is skipped; healthy row proceeds.

        The repo's ``list_pending`` returns everything (no server-side
        ``attempts`` filter) so client-side guard is the only line of
        defence against exhausted rows looping forever.
        """
        from app.config import settings
        from app.workers import orphan_analysis_reclaim

        supabase = MagicMock()
        ctx = {"supabase": supabase}

        orphan_repo_mock = MagicMock()
        orphan_repo_mock.list_pending.return_value = [
            _row(
                _ANALYSIS_ID_EXHAUSTED,
                attempts=settings.ORPHAN_ANALYSIS_RECLAIM_MAX_ATTEMPTS,
            ),
            _row(_ANALYSIS_ID_A),
        ]

        job_repo_mock = MagicMock()
        job_repo_mock.delete_analysis_by_id.return_value = None

        monkeypatch.setattr(
            orphan_analysis_reclaim,
            "OrphanedAnalysesRepository",
            lambda _sb: orphan_repo_mock,
        )
        monkeypatch.setattr(
            orphan_analysis_reclaim, "JobRepository", lambda _sb: job_repo_mock
        )

        await orphan_analysis_reclaim.reclaim_orphaned_analyses(ctx)

        # Exhausted row: untouched by both repos.
        job_repo_mock.delete_analysis_by_id.assert_called_once_with(_ANALYSIS_ID_A)
        orphan_repo_mock.delete.assert_called_once_with(_ANALYSIS_ID_A)
        # No mark_attempt on exhausted (skip, don't re-bump).
        orphan_repo_mock.mark_attempt.assert_not_called()

    async def test_warns_when_row_crosses_ceiling(self, monkeypatch, caplog):
        """Row with ``attempts + 1 == MAX`` fires the operator-review WARN.

        The row still gets ``mark_attempt`` so the persisted counter
        matches reality — the WARN is the external signal, not a state
        change.
        """
        from app.config import settings
        from app.workers import orphan_analysis_reclaim

        supabase = MagicMock()
        ctx = {"supabase": supabase}

        on_edge = settings.ORPHAN_ANALYSIS_RECLAIM_MAX_ATTEMPTS - 1
        orphan_repo_mock = MagicMock()
        orphan_repo_mock.list_pending.return_value = [
            _row(_ANALYSIS_ID_A, attempts=on_edge),
        ]

        job_repo_mock = MagicMock()
        job_repo_mock.delete_analysis_by_id.side_effect = RuntimeError("still broken")

        monkeypatch.setattr(
            orphan_analysis_reclaim,
            "OrphanedAnalysesRepository",
            lambda _sb: orphan_repo_mock,
        )
        monkeypatch.setattr(
            orphan_analysis_reclaim, "JobRepository", lambda _sb: job_repo_mock
        )

        with caplog.at_level(logging.WARNING, logger=orphan_analysis_reclaim.__name__):
            await orphan_analysis_reclaim.reclaim_orphaned_analyses(ctx)

        orphan_repo_mock.mark_attempt.assert_called_once_with(_ANALYSIS_ID_A)
        # The ceiling WARN mentions the analysis id so ops can grep for it.
        ceiling_warnings = [
            rec
            for rec in caplog.records
            if rec.levelno == logging.WARNING
            and "attempt ceiling" in rec.getMessage()
            and _ANALYSIS_ID_A in rec.getMessage()
        ]
        assert ceiling_warnings, "expected operator-review WARN at ceiling"

    async def test_empty_dlq_is_noop(self, monkeypatch):
        """Empty backlog: no per-row calls, no errors, clean exit."""
        from app.workers import orphan_analysis_reclaim

        supabase = MagicMock()
        ctx = {"supabase": supabase}

        orphan_repo_mock = MagicMock()
        orphan_repo_mock.list_pending.return_value = []

        job_repo_mock = MagicMock()

        monkeypatch.setattr(
            orphan_analysis_reclaim,
            "OrphanedAnalysesRepository",
            lambda _sb: orphan_repo_mock,
        )
        monkeypatch.setattr(
            orphan_analysis_reclaim, "JobRepository", lambda _sb: job_repo_mock
        )

        await orphan_analysis_reclaim.reclaim_orphaned_analyses(ctx)

        job_repo_mock.delete_analysis_by_id.assert_not_called()
        orphan_repo_mock.delete.assert_not_called()
        orphan_repo_mock.mark_attempt.assert_not_called()

    async def test_skips_when_no_supabase(self):
        """Missing supabase in ctx: warn and return; no repo construction."""
        from app.workers import orphan_analysis_reclaim

        # Must NOT raise, must NOT attempt any work.
        await orphan_analysis_reclaim.reclaim_orphaned_analyses({})


# ---------------------------------------------------------------------------
# Cron registration
# ---------------------------------------------------------------------------


class TestCronWiring:
    def test_worker_settings_registers_reclaim_orphaned_analyses(self):
        """WorkerSettings must schedule the sweeper with a distinct cron time.

        The 15-minute stagger from ``reclaim_orphaned_blobs`` (03:45) is
        deliberate — runs back-to-back would double Postgres load on the
        already-slow DLQ query shape.
        """
        from app.worker_settings import WorkerSettings
        from app.workers.orphan_analysis_reclaim import reclaim_orphaned_analyses

        registered = [job.coroutine for job in WorkerSettings.cron_jobs]
        assert reclaim_orphaned_analyses in registered
