"""Tests for ``app.workers.fingerprint_purge.run_fingerprint_purge``.

Covers:
  - Happy path: old rows are deleted, fresh rows are retained.
  - Zero rows deleted: no crash, log emitted.
  - Repository failure: logged, exception re-raised so ARQ retries.
  - Cutoff is approximately 365 days ago (within tolerance).
"""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.workers.fingerprint_purge import run_fingerprint_purge, _FINGERPRINT_TTL_DAYS


def _make_ctx(*, purge_returns: int = 0, purge_raises: Exception | None = None) -> dict:
    """Build a minimal ARQ ctx dict with a mock Supabase client."""
    sb = MagicMock()

    # Mock the SignupGrantRepository.purge_older_than call
    repo_mock = MagicMock()
    if purge_raises:
        repo_mock.purge_older_than.side_effect = purge_raises
    else:
        repo_mock.purge_older_than.return_value = purge_returns

    return {"supabase": sb, "_repo_mock": repo_mock}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestRunFingerprintPurge:
    @pytest.mark.asyncio
    async def test_purges_old_rows(self, caplog):
        """Worker should call purge_older_than and log the deleted count."""
        import logging

        ctx = {"supabase": MagicMock()}

        with patch("app.workers.fingerprint_purge.SignupGrantRepository") as MockRepo:
            MockRepo.return_value.purge_older_than.return_value = 42

            with caplog.at_level(logging.INFO, logger="app.workers.fingerprint_purge"):
                await run_fingerprint_purge(ctx)

        MockRepo.return_value.purge_older_than.assert_called_once()
        assert any("deleted=42" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_cutoff_is_approximately_365_days_ago(self):
        """Cutoff passed to purge_older_than must be ~365 days before now."""
        ctx = {"supabase": MagicMock()}
        captured_cutoffs: list[datetime] = []

        with patch("app.workers.fingerprint_purge.SignupGrantRepository") as MockRepo:

            def _capture(cutoff: datetime) -> int:
                captured_cutoffs.append(cutoff)
                return 0

            MockRepo.return_value.purge_older_than.side_effect = _capture

            await run_fingerprint_purge(ctx)

        assert len(captured_cutoffs) == 1
        cutoff = captured_cutoffs[0]
        now = datetime.now(tz=timezone.utc)
        expected = now - timedelta(days=_FINGERPRINT_TTL_DAYS)

        # Allow ±5 seconds of drift for test execution time.
        delta = abs((cutoff - expected).total_seconds())
        assert delta < 5, f"Cutoff {cutoff} too far from expected {expected}"

    @pytest.mark.asyncio
    async def test_zero_rows_deleted_no_crash(self, caplog):
        """Zero rows deleted must not crash; a log entry must still appear."""
        import logging

        ctx = {"supabase": MagicMock()}

        with patch("app.workers.fingerprint_purge.SignupGrantRepository") as MockRepo:
            MockRepo.return_value.purge_older_than.return_value = 0

            with caplog.at_level(logging.INFO, logger="app.workers.fingerprint_purge"):
                await run_fingerprint_purge(ctx)

        assert any("deleted=0" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_fresh_rows_not_deleted(self):
        """The worker must not delete rows within the TTL window.

        This is enforced by the cutoff value — verified via the argument
        captured from purge_older_than: any row with issued_at > cutoff
        survives because the repo's DELETE uses ``lt(issued_at, cutoff)``.
        """
        ctx = {"supabase": MagicMock()}
        captured_cutoffs: list[datetime] = []

        with patch("app.workers.fingerprint_purge.SignupGrantRepository") as MockRepo:

            def _capture(cutoff: datetime) -> int:
                captured_cutoffs.append(cutoff)
                return 0

            MockRepo.return_value.purge_older_than.side_effect = _capture
            await run_fingerprint_purge(ctx)

        # A row issued yesterday must be strictly after the cutoff
        yesterday = datetime.now(tz=timezone.utc) - timedelta(days=1)
        assert yesterday > captured_cutoffs[0], (
            "Yesterday's row would be purged — cutoff is too recent"
        )


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestRunFingerprintPurgeErrors:
    @pytest.mark.asyncio
    async def test_repo_failure_raises(self):
        """Repository errors must be re-raised so ARQ can retry the job."""
        ctx = {"supabase": MagicMock()}

        with patch("app.workers.fingerprint_purge.SignupGrantRepository") as MockRepo:
            MockRepo.return_value.purge_older_than.side_effect = RuntimeError(
                "DB timeout"
            )

            with pytest.raises(RuntimeError, match="DB timeout"):
                await run_fingerprint_purge(ctx)

    @pytest.mark.asyncio
    async def test_repo_failure_is_logged(self, caplog):
        """Repository errors must produce a log entry for ops visibility."""
        import logging

        ctx = {"supabase": MagicMock()}

        with patch("app.workers.fingerprint_purge.SignupGrantRepository") as MockRepo:
            MockRepo.return_value.purge_older_than.side_effect = RuntimeError(
                "network error"
            )

            with caplog.at_level(logging.ERROR, logger="app.workers.fingerprint_purge"):
                with pytest.raises(RuntimeError):
                    await run_fingerprint_purge(ctx)

        assert any(
            "purge_older_than" in r.message or "fingerprint_purge" in r.message
            for r in caplog.records
        )
