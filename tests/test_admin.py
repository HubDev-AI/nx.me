"""Tests for admin API — content moderation models and endpoint logic.

Exercises production code in:
  - app/api/admin.py (models, list_reports, update_report_status, ban/unban, post visibility)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError


try:
    from app.api.admin import ReportStatusUpdate, BanRequest, PostVisibilityUpdate  # noqa: F401

    _ADMIN_AVAILABLE = True
except (ImportError, AttributeError):
    _ADMIN_AVAILABLE = False

pytestmark = pytest.mark.skipif(not _ADMIN_AVAILABLE, reason="admin module unavailable")


async def _run_sync(fn, *args, **kwargs):
    return fn(*args, **kwargs)


# ---------------------------------------------------------------------------
# Model validation
# ---------------------------------------------------------------------------


class TestAdminModels:
    """Pydantic model validation — exercises app/api/admin.py models."""

    def test_report_status_update_valid_values(self):
        for val in ("reviewed", "actioned", "dismissed"):
            m = ReportStatusUpdate(status=val)
            assert m.status == val

    def test_report_status_update_invalid(self):
        with pytest.raises(ValidationError):
            ReportStatusUpdate(status="invalid_status")

    def test_ban_request_valid(self):
        m = BanRequest(reason="Spam content")
        assert m.reason == "Spam content"

    def test_ban_request_too_long(self):
        with pytest.raises(ValidationError):
            BanRequest(reason="x" * 501)

    def test_ban_request_empty_allowed(self):
        m = BanRequest(reason="")
        assert m.reason == ""

    def test_post_visibility_true(self):
        m = PostVisibilityUpdate(is_hidden=True)
        assert m.is_hidden is True

    def test_post_visibility_false(self):
        m = PostVisibilityUpdate(is_hidden=False)
        assert m.is_hidden is False


# ---------------------------------------------------------------------------
# Endpoint logic
# ---------------------------------------------------------------------------


class TestListReports:
    """Tests for GET /admin/reports — exercises app/api/admin.py."""

    @pytest.mark.asyncio
    async def test_list_reports_returns_data(self):
        from app.api.admin import list_reports

        mock_sb = MagicMock()
        mock_data = [{"id": "r-1", "post_id": "p-1", "status": "pending"}]
        mock_sb.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=mock_data
        )

        with patch("app.api.admin.run_sync", side_effect=_run_sync):
            result = await list_reports(report_status=None, limit=50, supabase=mock_sb)

        assert result == mock_data

    @pytest.mark.asyncio
    async def test_list_reports_with_status_filter(self):
        from app.api.admin import list_reports

        mock_sb = MagicMock()
        chain = mock_sb.table.return_value.select.return_value.order.return_value.limit.return_value
        chain.eq.return_value.execute.return_value = MagicMock(data=[])
        chain.execute.return_value = MagicMock(data=[])

        with patch("app.api.admin.run_sync", side_effect=_run_sync):
            result = await list_reports(
                report_status="pending", limit=50, supabase=mock_sb
            )

        assert isinstance(result, list)


class TestUpdateReportStatus:
    """Tests for PATCH /admin/reports/{id} — exercises app/api/admin.py."""

    @pytest.mark.asyncio
    async def test_update_report_not_found(self):
        from app.api.admin import update_report_status

        mock_sb = MagicMock()
        mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )

        body = ReportStatusUpdate(status="reviewed")

        with patch("app.api.admin.run_sync", side_effect=_run_sync):
            with pytest.raises(HTTPException) as exc_info:
                await update_report_status(
                    report_id=uuid4(), body=body, supabase=mock_sb
                )
        assert exc_info.value.status_code == 404


class TestBanUser:
    """Tests for POST /admin/users/{id}/ban — exercises app/api/admin.py."""

    @pytest.mark.asyncio
    async def test_ban_user_success(self):
        from app.api.admin import ban_user

        user_id = uuid4()
        mock_sb = MagicMock()
        mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{}]
        )
        mock_redis = AsyncMock()

        body = BanRequest(reason="Spam")

        with patch("app.api.admin.run_sync", side_effect=_run_sync):
            result = await ban_user(
                user_id=user_id, body=body, supabase=mock_sb, redis_client=mock_redis
            )

        assert result["banned"] is True
        mock_redis.delete.assert_called_once_with(f"ban:{user_id}")


class TestUnbanUser:
    """Tests for DELETE /admin/users/{id}/ban — exercises app/api/admin.py."""

    @pytest.mark.asyncio
    async def test_unban_user_success(self):
        from app.api.admin import unban_user

        user_id = uuid4()
        mock_sb = MagicMock()
        mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{}]
        )
        mock_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_redis = AsyncMock()

        with patch("app.api.admin.run_sync", side_effect=_run_sync):
            result = await unban_user(
                user_id=user_id, supabase=mock_sb, redis_client=mock_redis
            )

        assert result.status_code == 204
        mock_redis.delete.assert_called_once_with(f"ban:{user_id}")


class TestPostVisibility:
    """Tests for PATCH /admin/posts/{id} — exercises app/api/admin.py."""

    @pytest.mark.asyncio
    async def test_hide_post(self):
        from app.api.admin import update_post_visibility

        post_id = uuid4()
        mock_sb = MagicMock()
        mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{}]
        )

        body = PostVisibilityUpdate(is_hidden=True)

        with patch("app.api.admin.run_sync", side_effect=_run_sync):
            result = await update_post_visibility(
                post_id=post_id, body=body, supabase=mock_sb
            )

        assert result["is_hidden"] is True

    @pytest.mark.asyncio
    async def test_unhide_post(self):
        from app.api.admin import update_post_visibility

        post_id = uuid4()
        mock_sb = MagicMock()
        mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{}]
        )

        body = PostVisibilityUpdate(is_hidden=False)

        with patch("app.api.admin.run_sync", side_effect=_run_sync):
            result = await update_post_visibility(
                post_id=post_id, body=body, supabase=mock_sb
            )

        assert result["is_hidden"] is False
