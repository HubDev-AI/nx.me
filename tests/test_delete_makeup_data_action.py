"""Tests for DELETE /v1/users/me/makeup-data handler.

Covers:
  - Happy path: 204 on successful biometric nullification
  - Redis cleanup called for quota + rate-limit keys
  - Redis failure is swallowed (non-fatal), 204 still returned
  - Unauthed calls raise 401 (via get_current_user dep — not tested here,
    covered by the shared auth middleware test suite)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def _make_request() -> MagicMock:
    req = MagicMock()
    req.app.state.supabase = MagicMock()
    return req


def _make_claims(user_id: str | None = None) -> dict:
    return {"sub": user_id or str(uuid4())}


@pytest.fixture(autouse=True)
def _patch_run_sync():
    async def _run_sync(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with patch("app.api.makeup_privacy.run_sync", side_effect=_run_sync):
        yield


class TestDeleteMakeupDataHappyPath:
    @pytest.mark.asyncio
    async def test_returns_204_and_calls_nullify(self):
        from app.api.makeup_privacy import delete_makeup_data

        user_id = str(uuid4())
        mock_repo = MagicMock()
        mock_repo.nullify_biometric_fields.return_value = None
        redis_client = AsyncMock()

        with patch(
            "app.api.makeup_privacy.MakeupAnalysisRepository",
            return_value=mock_repo,
        ):
            resp = await delete_makeup_data(
                request=_make_request(),
                claims=_make_claims(user_id),
                redis_client=redis_client,
            )

        assert resp.status_code == 204
        mock_repo.nullify_biometric_fields.assert_called_once_with(user_id)

    @pytest.mark.asyncio
    async def test_deletes_makeup_redis_keys(self):
        from app.api.makeup_privacy import delete_makeup_data

        user_id = str(uuid4())
        mock_repo = MagicMock()
        mock_repo.nullify_biometric_fields.return_value = None
        redis_client = AsyncMock()

        with patch(
            "app.api.makeup_privacy.MakeupAnalysisRepository",
            return_value=mock_repo,
        ):
            await delete_makeup_data(
                request=_make_request(),
                claims=_make_claims(user_id),
                redis_client=redis_client,
            )

        redis_client.delete.assert_awaited_once_with(
            f"makeup:quota:{user_id}",
            f"makeup:analyze_rate:{user_id}",
        )

    @pytest.mark.asyncio
    async def test_redis_failure_is_non_fatal(self):
        from app.api.makeup_privacy import delete_makeup_data

        user_id = str(uuid4())
        mock_repo = MagicMock()
        mock_repo.nullify_biometric_fields.return_value = None
        redis_client = AsyncMock()
        redis_client.delete.side_effect = Exception("redis down")

        with patch(
            "app.api.makeup_privacy.MakeupAnalysisRepository",
            return_value=mock_repo,
        ):
            resp = await delete_makeup_data(
                request=_make_request(),
                claims=_make_claims(user_id),
                redis_client=redis_client,
            )

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_idempotent_no_rows_to_null(self):
        """Calling with no existing biometric data still returns 204."""
        from app.api.makeup_privacy import delete_makeup_data

        user_id = str(uuid4())
        mock_repo = MagicMock()
        mock_repo.nullify_biometric_fields.return_value = None
        redis_client = AsyncMock()

        with patch(
            "app.api.makeup_privacy.MakeupAnalysisRepository",
            return_value=mock_repo,
        ):
            resp = await delete_makeup_data(
                request=_make_request(),
                claims=_make_claims(user_id),
                redis_client=redis_client,
            )

        assert resp.status_code == 204
        mock_repo.nullify_biometric_fields.assert_called_once_with(user_id)
