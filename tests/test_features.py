"""Tests for feature flag registry and require_app_feature dep.

Exercises:
  - app/features/__init__.py — get_features(), is_enabled()
  - app/api/deps.py — require_app_feature()
  - app/api/features.py — GET /v1/features response shape
  - app/db/guest.py — create_guest_user, resolve_guest_by_token
  - app/api/auth.py — POST /auth/guest endpoint (config gating)
"""
from __future__ import annotations

from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi import HTTPException

from app.features import FeatureFlags, get_features, is_enabled


# ===========================================================================
# FeatureFlags registry tests
# ===========================================================================


class TestGetFeatures:
    """get_features() reads from settings and returns a FeatureFlags object."""

    def test_returns_feature_flags_instance(self):
        features = get_features()
        assert isinstance(features, FeatureFlags)

    def test_all_five_flags_present(self):
        features = get_features()
        for flag in ("auth_required", "social_enabled", "share_enabled",
                     "onboarding_enabled", "advisor_enabled"):
            assert hasattr(features, flag), f"missing {flag}"
            assert isinstance(getattr(features, flag), bool)

    def test_reads_auth_required_from_settings(self):
        from app.config import settings as real_settings
        with patch.object(real_settings, "FEATURE_AUTH_REQUIRED", False):
            features = get_features()
        assert features.auth_required is False

    def test_reads_advisor_from_legacy_setting(self):
        """advisor_enabled maps to the pre-existing ADVISOR_ENABLED setting."""
        from app.config import settings as real_settings
        with patch.object(real_settings, "ADVISOR_ENABLED", False):
            features = get_features()
        assert features.advisor_enabled is False


class TestIsEnabled:
    """is_enabled() looks up a flag by name and returns its bool."""

    def test_returns_bool_for_known_flag(self):
        result = is_enabled("social_enabled")
        assert isinstance(result, bool)

    def test_raises_value_error_for_unknown_flag(self):
        with pytest.raises(ValueError, match="Unknown feature flag"):
            is_enabled("nonexistent_flag")

    def test_raises_with_typo(self):
        with pytest.raises(ValueError):
            is_enabled("social")  # missing _enabled suffix


# ===========================================================================
# require_app_feature dep tests
# ===========================================================================


class TestRequireAppFeature:
    """require_app_feature() returns a dep that raises 403 when flag is off."""

    @pytest.mark.asyncio
    async def test_passes_when_flag_enabled(self):
        from app.api.deps import require_app_feature
        from app.config import settings as real_settings

        dep = require_app_feature("share_enabled")
        with patch.object(real_settings, "FEATURE_SHARE_ENABLED", True):
            # Should not raise
            result = await dep()
        assert result is None

    @pytest.mark.asyncio
    async def test_raises_403_when_flag_disabled(self):
        from app.api.deps import require_app_feature
        from app.config import settings as real_settings

        dep = require_app_feature("social_enabled")
        with patch.object(real_settings, "FEATURE_SOCIAL_ENABLED", False):
            with pytest.raises(HTTPException) as exc_info:
                await dep()
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["error"]["code"] == "FEATURE_DISABLED"
        assert exc_info.value.detail["error"]["detail"]["feature"] == "social_enabled"

    @pytest.mark.asyncio
    async def test_typed_error_shape(self):
        """Error detail must follow the existing API error contract."""
        from app.api.deps import require_app_feature
        from app.config import settings as real_settings

        dep = require_app_feature("social_enabled")
        with patch.object(real_settings, "FEATURE_SOCIAL_ENABLED", False):
            with pytest.raises(HTTPException) as exc_info:
                await dep()
        detail = exc_info.value.detail
        assert "error" in detail
        assert set(detail["error"].keys()) == {"code", "message", "detail"}


# ===========================================================================
# Guest user helpers
# ===========================================================================


class TestGuestHelpers:
    """Unit tests for app/db/guest.py — no real Supabase required."""

    def test_generate_guest_token_shape(self):
        from app.db.guest import _generate_guest_token

        token = _generate_guest_token()
        assert len(token) == 64
        assert all(c in "0123456789abcdef" for c in token)

    def test_generate_guest_token_unique(self):
        from app.db.guest import _generate_guest_token

        tokens = {_generate_guest_token() for _ in range(50)}
        assert len(tokens) == 50  # vanishingly rare to collide

    def test_create_guest_user_inserts_correct_row(self):
        from app.db.guest import create_guest_user
        from unittest.mock import MagicMock

        # Hand-rolled spy: record the dict passed to insert().
        inserted: list[dict] = []
        supabase = MagicMock()
        builder = MagicMock()

        def capture_insert(row):
            inserted.append(row)
            return builder

        builder.insert = capture_insert
        builder.execute = MagicMock(return_value=None)
        supabase.table.return_value = builder

        user_id, token = create_guest_user(supabase)

        assert isinstance(user_id, UUID)
        assert len(token) == 64
        assert len(inserted) == 1
        row = inserted[0]
        assert row["is_guest"] is True
        assert row["guest_session_token"] == token
        assert row["display_name"] == "Guest"
        assert row["tier_id"] == "a0000000-0000-0000-0000-000000000001"
        assert row["username"].startswith("guest-")
