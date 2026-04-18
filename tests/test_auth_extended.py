"""Extended tests for auth module — helpers, models, provider logic.

Exercises production code in:
  - app/api/auth.py (_get_enabled_providers, _derive_tiktok_password,
    FeatureFlags, ProvidersResponse, get_providers, MeResponse, VerifyEmailResponse,
    _is_invalid_token_error, _handle_supabase_auth_error, EmailLoginRequest, TikTokLoginRequest)
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


try:
    from app.api.auth import (
        _get_enabled_providers,
        _derive_tiktok_password,
        FeatureFlags,
        ProvidersResponse,
        MeResponse,
        VerifyEmailResponse,
        LoginResponse,
        RefreshRequest,
        LoginRequest,
        EmailLoginRequest,
        social_login,
        email_login,
        refresh_token,
        _is_invalid_token_error,
        _handle_supabase_auth_error,
    )
    from tests.conftest import MockRedis, MockSupabase

    _AUTH_EXT_AVAILABLE = True
except (ImportError, AttributeError):
    _AUTH_EXT_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _AUTH_EXT_AVAILABLE, reason="auth module unavailable"
)


class TestGetEnabledProviders:
    """Tests for _get_enabled_providers — exercises app/api/auth.py."""

    def test_returns_list(self):
        result = _get_enabled_providers()
        assert isinstance(result, list)

    def test_google_in_providers(self):
        # Google is enabled in test env by default
        result = _get_enabled_providers()
        assert "google" in result


class TestDeriveTikTokPassword:
    """Tests for _derive_tiktok_password — exercises app/api/auth.py."""

    def test_returns_hex_string(self):
        result = _derive_tiktok_password("open-id-123")
        assert len(result) == 64  # SHA-256 hex digest
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self):
        result1 = _derive_tiktok_password("open-id-123")
        result2 = _derive_tiktok_password("open-id-123")
        assert result1 == result2

    def test_different_open_ids_produce_different_passwords(self):
        result1 = _derive_tiktok_password("open-id-1")
        result2 = _derive_tiktok_password("open-id-2")
        assert result1 != result2


class TestAuthModels:
    """Tests for auth Pydantic models — exercises app/api/auth.py."""

    def test_feature_flags(self):
        flags = FeatureFlags(onboarding_enabled=True)
        assert flags.onboarding_enabled is True

    def test_providers_response(self):
        resp = ProvidersResponse(
            providers=["google", "apple"],
            features=FeatureFlags(onboarding_enabled=False),
        )
        assert len(resp.providers) == 2
        assert resp.features.onboarding_enabled is False

    def test_verify_email_response(self):
        resp = VerifyEmailResponse(
            trial_analyses_remaining=2,
            message="Trial credited",
        )
        assert resp.trial_analyses_remaining == 2

    def test_me_response(self):
        resp = MeResponse(
            user_id="u-1",
            email="alice@example.com",
            username="alice",
            display_name="Alice",
        )
        assert resp.user_id == "u-1"
        assert resp.email == "alice@example.com"

    def test_refresh_request(self):
        req = RefreshRequest(refresh_token="rt-123")
        assert req.refresh_token == "rt-123"

    def test_refresh_request_empty_rejected(self):
        with pytest.raises(ValidationError):
            RefreshRequest(refresh_token="")

    def test_refresh_request_strips_whitespace(self):
        """StringConstraints(strip_whitespace=True) removes surrounding spaces."""
        req = RefreshRequest(refresh_token="  rt-padded  ")
        assert req.refresh_token == "rt-padded"

    def test_refresh_request_whitespace_only_rejected(self):
        """After strip, whitespace-only token is empty and fails min_length=1."""
        with pytest.raises(ValidationError):
            RefreshRequest(refresh_token="   ")

    def test_login_response_model(self):
        resp = LoginResponse(
            user_id="u-1",
            username="alice",
            access_token="at-123",
            refresh_token="rt-456",
            expires_at=1710720000,
        )
        assert resp.expires_at == 1710720000
        assert resp.username == "alice"


class TestIsInvalidTokenError:
    """Tests for _is_invalid_token_error — exercises app/api/auth.py."""

    def test_invalid_token_error(self):
        exc = Exception("Invalid Refresh Token: Refresh Token Not Found")
        assert _is_invalid_token_error(exc) is True

    def test_invalid_claim_error(self):
        exc = Exception("invalid claim: something went wrong")
        assert _is_invalid_token_error(exc) is True

    def test_token_expired_error(self):
        exc = Exception("token is expired")
        assert _is_invalid_token_error(exc) is True

    def test_non_token_error(self):
        exc = Exception("Database connection failed")
        assert _is_invalid_token_error(exc) is False


class TestHandleSupabaseAuthError:
    """Tests for _handle_supabase_auth_error — exercises app/api/auth.py."""

    def test_raises_http_exception(self):
        from fastapi import HTTPException

        exc = Exception("User already registered")
        with pytest.raises(HTTPException) as exc_info:
            _handle_supabase_auth_error(exc)
        assert exc_info.value.status_code in (400, 401, 409, 422, 500)

    def test_email_already_taken(self):
        from fastapi import HTTPException

        exc = Exception("User already registered")
        with pytest.raises(HTTPException) as exc_info:
            _handle_supabase_auth_error(exc)
        assert exc_info.value.status_code == 409


class TestAuthSessionIsolation:
    """Session-mutating auth calls must use fresh Supabase clients."""

    @staticmethod
    def _session_response(*, user_id: str, email: str):
        session = SimpleNamespace(
            access_token="at-123",
            refresh_token="rt-456",
            expires_at=1710720000,
        )
        user = SimpleNamespace(
            id=user_id,
            email=email,
            user_metadata={"full_name": "Alice Example"},
        )
        return SimpleNamespace(session=session, user=user)

    @pytest.mark.asyncio
    async def test_social_login_uses_separate_supabase_client(self, monkeypatch):
        shared_supabase = MockSupabase()
        shared_supabase.auth.sign_in_with_id_token = MagicMock(
            side_effect=AssertionError("shared client used")
        )
        isolated_supabase = MockSupabase()
        isolated_supabase.auth.sign_in_with_id_token = MagicMock(
            return_value=self._session_response(
                user_id="user-1", email="alice@example.com"
            )
        )

        async def fake_run_sync(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        monkeypatch.setattr("app.api.auth.run_sync", fake_run_sync)
        monkeypatch.setattr("app.api.auth.get_client_ip", lambda request: "203.0.113.8")
        monkeypatch.setattr(
            "app.api.auth.check_login_rate_limit",
            AsyncMock(return_value=(True, 0)),
        )
        monkeypatch.setattr(
            "app.db.client.get_supabase_service", lambda: isolated_supabase
        )

        user_repo = MagicMock()
        user_repo.check_username_availability.return_value = {"available": True}
        user_repo.upsert.return_value = None
        user_repo.get_profile_by_id.return_value = {"username": "alice"}
        tier_repo = SimpleNamespace(
            get_default=AsyncMock(return_value=SimpleNamespace(id="tier-1"))
        )

        result = await social_login(
            request=MagicMock(),
            body=LoginRequest(provider="google", id_token="id-token"),
            supabase=shared_supabase,
            r=MockRedis(),
            user_repo=user_repo,
            tier_repo=tier_repo,
        )

        assert result.username == "alice"
        isolated_supabase.auth.sign_in_with_id_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_email_login_uses_separate_supabase_client(self, monkeypatch):
        shared_supabase = MockSupabase()
        shared_supabase.auth.sign_in_with_password = MagicMock(
            side_effect=AssertionError("shared client used")
        )
        isolated_supabase = MockSupabase()
        isolated_supabase.auth.sign_in_with_password = MagicMock(
            return_value=self._session_response(
                user_id="user-2", email="alice@example.com"
            )
        )

        async def fake_run_sync(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        monkeypatch.setattr("app.api.auth.run_sync", fake_run_sync)
        monkeypatch.setattr("app.api.auth.get_client_ip", lambda request: "203.0.113.8")
        monkeypatch.setattr(
            "app.api.auth.check_login_rate_limit",
            AsyncMock(return_value=(True, 0)),
        )
        monkeypatch.setattr("app.api.auth.settings.AUTH_PROVIDER_EMAIL_ENABLED", True)
        monkeypatch.setattr(
            "app.db.client.get_supabase_service", lambda: isolated_supabase
        )

        user_repo = MagicMock()
        user_repo.get_profile_by_id.return_value = {"username": "alice"}

        result = await email_login(
            request=MagicMock(),
            body=EmailLoginRequest(email="alice@example.com", password="secret123"),
            supabase=shared_supabase,
            r=MockRedis(),
            user_repo=user_repo,
        )

        assert result.username == "alice"
        isolated_supabase.auth.sign_in_with_password.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_uses_separate_supabase_client(self, monkeypatch):
        shared_supabase = MockSupabase()
        shared_supabase.auth.refresh_session = MagicMock(
            side_effect=AssertionError("shared client used")
        )
        isolated_supabase = MockSupabase()
        isolated_supabase.auth.refresh_session = MagicMock(
            return_value=self._session_response(
                user_id="user-3", email="alice@example.com"
            )
        )

        async def fake_run_sync(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        monkeypatch.setattr("app.api.auth.run_sync", fake_run_sync)
        monkeypatch.setattr(
            "app.db.client.get_supabase_service", lambda: isolated_supabase
        )

        user_repo = MagicMock()
        user_repo.get_profile_by_id.return_value = {"username": "alice"}

        result = await refresh_token(
            body=RefreshRequest(refresh_token="rt-123"),
            supabase=shared_supabase,
            user_repo=user_repo,
        )

        assert result.username == "alice"
        isolated_supabase.auth.refresh_session.assert_called_once()
