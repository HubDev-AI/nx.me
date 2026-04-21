"""Tests for app.entitlement.consent — has_consent and require_consent."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.entitlement.consent import (
    MAKEUP_CONSENT_VERSION,
    has_consent,
    require_consent,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_supabase(consent_version: str | None = None):
    """Build a minimal Supabase mock returning one makeup_analyses row."""
    execute_result = MagicMock()
    if consent_version is not None:
        execute_result.data = {"consent_version": consent_version}
    else:
        execute_result.data = None

    builder = MagicMock()
    builder.select.return_value = builder
    builder.eq.return_value = builder
    builder.order.return_value = builder
    builder.limit.return_value = builder
    builder.maybe_single.return_value = builder
    builder.execute.return_value = execute_result

    sb = MagicMock()
    sb.table.return_value = builder
    return sb


# ---------------------------------------------------------------------------
# has_consent — unit tests
# ---------------------------------------------------------------------------


class TestHasConsent:
    def test_returns_true_when_version_matches(self):
        sb = _make_supabase("1.0")
        assert has_consent("user-1", "makeup_v1", "1.0", supabase=sb) is True

    def test_returns_true_when_stored_version_greater(self):
        sb = _make_supabase("2.0")
        assert has_consent("user-1", "makeup_v1", "1.0", supabase=sb) is True

    def test_returns_false_when_stored_version_older(self):
        sb = _make_supabase("0.9")
        assert has_consent("user-1", "makeup_v1", "1.0", supabase=sb) is False

    def test_returns_false_when_no_analysis_row(self):
        sb = _make_supabase(None)
        assert has_consent("user-1", "makeup_v1", "1.0", supabase=sb) is False

    def test_returns_false_for_unknown_consent_key(self):
        sb = _make_supabase("1.0")
        assert has_consent("user-1", "unknown_key", "1.0", supabase=sb) is False

    def test_queries_makeup_analyses_table(self):
        sb = _make_supabase("1.0")
        has_consent("user-1", "makeup_v1", "1.0", supabase=sb)
        sb.table.assert_called_once_with("makeup_analyses")

    def test_filters_by_user_id(self):
        sb = _make_supabase("1.0")
        has_consent("user-42", "makeup_v1", "1.0", supabase=sb)
        # The builder's .eq() must have been called with user_id
        builder = sb.table.return_value
        builder.eq.assert_called_once_with("user_id", "user-42")


# ---------------------------------------------------------------------------
# MAKEUP_CONSENT_VERSION constant
# ---------------------------------------------------------------------------


class TestMakeupConsentVersion:
    def test_version_is_string(self):
        assert isinstance(MAKEUP_CONSENT_VERSION, str)

    def test_version_parseable_as_tuple(self):
        parts = tuple(int(x) for x in MAKEUP_CONSENT_VERSION.split("."))
        assert parts >= (1, 0)


# ---------------------------------------------------------------------------
# require_consent — FastAPI dep raises 403 when no consent
# ---------------------------------------------------------------------------


class TestRequireConsent:
    @pytest.mark.asyncio
    async def test_passes_when_consent_present(self):
        dep = require_consent("makeup_v1")
        supabase = _make_supabase("1.0")
        claims = {"sub": "user-1"}

        with patch("app.entitlement.consent.run_sync", new=AsyncMock(return_value=True)):
            await dep(supabase=supabase, claims=claims)
        # No exception raised → test passes

    @pytest.mark.asyncio
    async def test_raises_403_when_no_consent(self):
        from fastapi import HTTPException

        dep = require_consent("makeup_v1")
        supabase = _make_supabase(None)
        claims = {"sub": "user-1"}

        with patch("app.entitlement.consent.run_sync", new=AsyncMock(return_value=False)):
            with pytest.raises(HTTPException) as exc_info:
                await dep(supabase=supabase, claims=claims)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["error"]["code"] == "CONSENT_REQUIRED"

    @pytest.mark.asyncio
    async def test_error_detail_includes_consent_key(self):
        from fastapi import HTTPException

        dep = require_consent("makeup_v1")
        claims = {"sub": "user-1"}

        with patch("app.entitlement.consent.run_sync", new=AsyncMock(return_value=False)):
            with pytest.raises(HTTPException) as exc_info:
                await dep(supabase=MagicMock(), claims=claims)

        assert exc_info.value.detail["error"]["detail"]["consent_key"] == "makeup_v1"
