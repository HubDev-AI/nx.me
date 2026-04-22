"""Tests for the makeup biometric purge ARQ cron task.

Covers:
  - Happy path: run_makeup_purge calls nullify_biometric_fields_older_than(90)
  - Exception propagates (ARQ will retry)
  - MakeupAnalysisRepository.nullify_biometric_fields_older_than CAS predicate
    (filters mst_bin IS NOT NULL)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestRunMakeupPurge:
    @pytest.mark.asyncio
    async def test_calls_nullify_with_90_day_ttl(self):
        from app.workers.makeup_purge import run_makeup_purge

        mock_repo = MagicMock()
        mock_repo.nullify_biometric_fields_older_than.return_value = 5

        async def _run_sync(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        ctx = {"supabase": MagicMock()}

        with (
            patch(
                "app.workers.makeup_purge.MakeupAnalysisRepository",
                return_value=mock_repo,
            ),
            patch("app.workers.makeup_purge.run_sync", side_effect=_run_sync),
        ):
            await run_makeup_purge(ctx)

        mock_repo.nullify_biometric_fields_older_than.assert_called_once_with(90)

    @pytest.mark.asyncio
    async def test_exception_propagates_for_arq_retry(self):
        from app.workers.makeup_purge import run_makeup_purge

        mock_repo = MagicMock()
        mock_repo.nullify_biometric_fields_older_than.side_effect = RuntimeError(
            "db down"
        )

        async def _run_sync(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        ctx = {"supabase": MagicMock()}

        with (
            patch(
                "app.workers.makeup_purge.MakeupAnalysisRepository",
                return_value=mock_repo,
            ),
            patch("app.workers.makeup_purge.run_sync", side_effect=_run_sync),
        ):
            with pytest.raises(RuntimeError, match="db down"):
                await run_makeup_purge(ctx)


class TestNullifyBiometricFieldsOlderThan:
    def test_cas_predicate_skips_already_nullified_rows(self):
        """nullify_biometric_fields_older_than uses filter(mst_bin not.is null)."""
        from app.repositories.makeup_analysis_repo import MakeupAnalysisRepository
        import inspect

        src = inspect.getsource(
            MakeupAnalysisRepository.nullify_biometric_fields_older_than
        )
        assert "not.is" in src, (
            "CAS predicate must use filter('mst_bin', 'not.is', 'null') to skip "
            "already-nullified rows"
        )
        assert "mst_bin" in src

    def test_returns_count_of_updated_rows(self):
        """Returns len(result.data) so callers can log how many rows were touched."""
        mock_sb = MagicMock()
        mock_result = MagicMock()
        mock_result.data = [{"id": "a"}, {"id": "b"}]

        (
            mock_sb.table.return_value.update.return_value.lt.return_value.filter.return_value.execute.return_value
        ) = mock_result

        from app.repositories.makeup_analysis_repo import MakeupAnalysisRepository

        repo = MakeupAnalysisRepository(mock_sb)
        count = repo.nullify_biometric_fields_older_than(90)
        assert count == 2

    def test_returns_zero_when_no_rows_updated(self):
        mock_sb = MagicMock()
        mock_result = MagicMock()
        mock_result.data = []

        (
            mock_sb.table.return_value.update.return_value.lt.return_value.filter.return_value.execute.return_value
        ) = mock_result

        from app.repositories.makeup_analysis_repo import MakeupAnalysisRepository

        repo = MakeupAnalysisRepository(mock_sb)
        count = repo.nullify_biometric_fields_older_than(90)
        assert count == 0
