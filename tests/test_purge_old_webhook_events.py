"""Tests for ``app.workers.purge_old_webhook_events.purge_old_webhook_events``.

Covers:
  - Happy path: deletes events with inserted_at < 30 days ago; retains fresh rows.
  - Zero rows deleted: no crash, log emitted.
  - DB failure: logged, worker returns cleanly.
  - Cutoff is approximately 30 days ago (within tolerance).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.workers.purge_old_webhook_events import (
    purge_old_webhook_events,
    _WEBHOOK_EVENT_RETENTION_DAYS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(*, deleted_count: int = 0, raises: Exception | None = None) -> dict:
    """Build a minimal ARQ ctx with a mock Supabase client."""
    sb = MagicMock()
    chain = sb.table.return_value.delete.return_value.lt.return_value
    if raises:
        chain.execute.side_effect = raises
    else:
        chain.execute.return_value = MagicMock(
            data=[{}] * deleted_count if deleted_count else []
        )
    return {"supabase": sb}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestPurgeOldWebhookEvents:
    @pytest.mark.asyncio
    async def test_deletes_old_events_and_logs_count(self, caplog):
        """Worker should issue DELETE and log the deleted count."""
        ctx = _make_ctx(deleted_count=7)

        with caplog.at_level(
            logging.INFO, logger="app.workers.purge_old_webhook_events"
        ):
            await purge_old_webhook_events(ctx)

        assert any("deleted=7" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_cutoff_is_approximately_30_days_ago(self):
        """The cutoff passed to .lt() must be ~30 days before now."""
        captured_cutoffs: list[str] = []

        sb = MagicMock()

        def _capture_cutoff(col, cutoff_str):
            captured_cutoffs.append(cutoff_str)
            mock = MagicMock()
            mock.execute.return_value = MagicMock(data=[])
            return mock

        sb.table.return_value.delete.return_value.lt.side_effect = _capture_cutoff

        ctx = {"supabase": sb}
        await purge_old_webhook_events(ctx)

        assert len(captured_cutoffs) == 1
        cutoff = datetime.fromisoformat(captured_cutoffs[0])
        now = datetime.now(tz=timezone.utc)
        expected = now - timedelta(days=_WEBHOOK_EVENT_RETENTION_DAYS)
        delta = abs((cutoff - expected).total_seconds())
        assert delta < 5, f"Cutoff {cutoff} is too far from expected {expected}"

    @pytest.mark.asyncio
    async def test_fresh_events_not_in_delete_range(self):
        """The cutoff must be in the past — a row from yesterday must survive."""
        captured_cutoffs: list[str] = []

        sb = MagicMock()

        def _capture_cutoff(col, cutoff_str):
            captured_cutoffs.append(cutoff_str)
            mock = MagicMock()
            mock.execute.return_value = MagicMock(data=[])
            return mock

        sb.table.return_value.delete.return_value.lt.side_effect = _capture_cutoff

        ctx = {"supabase": sb}
        await purge_old_webhook_events(ctx)

        cutoff = datetime.fromisoformat(captured_cutoffs[0])
        yesterday = datetime.now(tz=timezone.utc) - timedelta(days=1)
        assert yesterday > cutoff, (
            "Yesterday's row would be purged — cutoff is too recent"
        )

    @pytest.mark.asyncio
    async def test_zero_deleted_no_crash(self, caplog):
        """Zero rows deleted must not crash; a log entry must still appear."""
        ctx = _make_ctx(deleted_count=0)

        with caplog.at_level(
            logging.INFO, logger="app.workers.purge_old_webhook_events"
        ):
            await purge_old_webhook_events(ctx)

        assert any("deleted=0" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestPurgeOldWebhookEventsErrors:
    @pytest.mark.asyncio
    async def test_db_failure_does_not_raise(self):
        """DB errors must be caught — worker must not crash."""
        ctx = _make_ctx(raises=RuntimeError("DB timeout"))
        await purge_old_webhook_events(ctx)  # must not raise

    @pytest.mark.asyncio
    async def test_db_failure_is_logged(self, caplog):
        """DB errors must produce an exception log entry."""
        ctx = _make_ctx(raises=RuntimeError("connection refused"))

        with caplog.at_level(
            logging.ERROR, logger="app.workers.purge_old_webhook_events"
        ):
            await purge_old_webhook_events(ctx)

        assert any(
            "DELETE" in r.message or "purge_old_webhook_events" in r.message
            for r in caplog.records
        )
