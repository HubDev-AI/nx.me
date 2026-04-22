"""Tests for the require_tier_feature FastAPI dependency factory."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


class TestRequireTierFeature:
    """require_tier_feature() raises 403 TIER_REQUIRED when user lacks Pro."""

    def _make_claims(self, user_id: str = "user-abc") -> dict:
        return {"sub": user_id, "role": "authenticated"}

    @pytest.mark.asyncio
    async def test_passes_when_user_has_active_pro(self):
        from app.api.deps import require_tier_feature

        dep = require_tier_feature("makeup")
        mock_sb = MagicMock()

        with patch("app.api.deps.run_sync", new=AsyncMock(return_value=True)):
            result = await dep(supabase=mock_sb, claims=self._make_claims())

        assert result is None

    @pytest.mark.asyncio
    async def test_raises_403_when_user_lacks_pro(self):
        from app.api.deps import require_tier_feature

        dep = require_tier_feature("makeup")
        mock_sb = MagicMock()

        with patch("app.api.deps.run_sync", new=AsyncMock(return_value=False)):
            with pytest.raises(HTTPException) as exc_info:
                await dep(supabase=mock_sb, claims=self._make_claims())

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["error"]["code"] == "TIER_REQUIRED"

    @pytest.mark.asyncio
    async def test_error_shape_matches_api_contract(self):
        """Error detail must follow the standard API error envelope."""
        from app.api.deps import require_tier_feature

        dep = require_tier_feature("makeup")
        mock_sb = MagicMock()

        with patch("app.api.deps.run_sync", new=AsyncMock(return_value=False)):
            with pytest.raises(HTTPException) as exc_info:
                await dep(supabase=mock_sb, claims=self._make_claims())

        detail = exc_info.value.detail
        assert "error" in detail
        assert set(detail["error"].keys()) == {"code", "message", "detail"}
        assert detail["error"]["detail"]["capability"] == "makeup"

    @pytest.mark.asyncio
    async def test_capability_name_in_error_detail(self):
        """The capability argument is echoed in the 403 error detail."""
        from app.api.deps import require_tier_feature

        dep = require_tier_feature("some_other_capability")
        mock_sb = MagicMock()

        with patch("app.api.deps.run_sync", new=AsyncMock(return_value=False)):
            with pytest.raises(HTTPException) as exc_info:
                await dep(supabase=mock_sb, claims=self._make_claims())

        assert (
            exc_info.value.detail["error"]["detail"]["capability"]
            == "some_other_capability"
        )

    @pytest.mark.asyncio
    async def test_passes_user_id_from_claims_to_has_active_pro(self):
        """user_id extracted from claims['sub'] must reach has_active_pro."""
        from app.api.deps import require_tier_feature

        dep = require_tier_feature("makeup")
        mock_sb = MagicMock()

        with patch(
            "app.api.deps.run_sync", new=AsyncMock(return_value=True)
        ) as mock_run:
            await dep(supabase=mock_sb, claims={"sub": "specific-user-id"})

        # run_sync is called as run_sync(has_active_pro, user_id, supabase)
        call_args = mock_run.call_args[0]
        assert call_args[1] == "specific-user-id"
        assert call_args[2] is mock_sb
