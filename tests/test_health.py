"""Tests for health check endpoints.

Exercises production code in:
  - app/api/health.py (health, readiness)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


# Check if router imports work (FastAPI/Pydantic compat)
try:
    from app.api.health import health as _health_check  # noqa: F401
    _HEALTH_AVAILABLE = True
except (ImportError, AttributeError):
    _HEALTH_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _HEALTH_AVAILABLE, reason="health module unavailable"
)


class TestHealthEndpoint:
    """Tests for GET /health — exercises app/api/health.py."""

    @pytest.mark.asyncio
    async def test_health_returns_ok(self):
        from app.api.health import health
        result = await health()
        assert result == {"status": "ok"}


class TestReadinessEndpoint:
    """Tests for GET /readiness — exercises app/api/health.py."""

    @pytest.mark.asyncio
    async def test_readiness_all_healthy(self):
        from app.api.health import readiness

        redis_mock = AsyncMock()
        redis_mock.ping = AsyncMock(return_value=True)

        supabase_mock = MagicMock()
        mock_result = MagicMock()
        mock_result.data = [{"id": "tier-1"}]
        supabase_mock.table.return_value.select.return_value.limit.return_value.execute.return_value = mock_result

        with patch("app.api.health.run_sync", side_effect=_run_sync_passthrough):
            result = await readiness(r=redis_mock, supabase=supabase_mock)

        assert result["status"] == "ok"
        assert result["checks"]["redis"] == "ok"
        assert result["checks"]["supabase"] == "ok"

    @pytest.mark.asyncio
    async def test_readiness_redis_down(self):
        from app.api.health import readiness

        redis_mock = AsyncMock()
        redis_mock.ping = AsyncMock(side_effect=ConnectionError("Connection refused"))

        supabase_mock = MagicMock()
        mock_result = MagicMock()
        mock_result.data = [{"id": "tier-1"}]
        supabase_mock.table.return_value.select.return_value.limit.return_value.execute.return_value = mock_result

        with patch("app.api.health.run_sync", side_effect=_run_sync_passthrough):
            with pytest.raises(HTTPException) as exc_info:
                await readiness(r=redis_mock, supabase=supabase_mock)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail["redis"] == "unavailable"

    @pytest.mark.asyncio
    async def test_readiness_supabase_down(self):
        from app.api.health import readiness

        redis_mock = AsyncMock()
        redis_mock.ping = AsyncMock(return_value=True)

        supabase_mock = MagicMock()
        supabase_mock.table.side_effect = Exception("Supabase unreachable")

        with patch("app.api.health.run_sync", side_effect=_run_sync_passthrough):
            with pytest.raises(HTTPException) as exc_info:
                await readiness(r=redis_mock, supabase=supabase_mock)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail["supabase"] == "unavailable"

    @pytest.mark.asyncio
    async def test_readiness_both_down(self):
        from app.api.health import readiness

        redis_mock = AsyncMock()
        redis_mock.ping = AsyncMock(side_effect=ConnectionError("down"))

        supabase_mock = MagicMock()
        supabase_mock.table.side_effect = Exception("down")

        with patch("app.api.health.run_sync", side_effect=_run_sync_passthrough):
            with pytest.raises(HTTPException) as exc_info:
                await readiness(r=redis_mock, supabase=supabase_mock)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail["redis"] == "unavailable"
        assert exc_info.value.detail["supabase"] == "unavailable"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run_sync_passthrough(fn, *args, **kwargs):
    """Call the sync function and return its result — replaces run_sync in tests."""
    return fn(*args, **kwargs)
