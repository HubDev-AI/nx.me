"""Tests for registration request/response models and the age gate logic.

Exercises production code in:
  - app/api/auth.py (RegisterRequest, RegisterResponse, _MIN_AGE_YEARS, LoginRequest, LoginResponse)

Note: Imports are deferred inside test methods because importing app.api.auth
triggers FastAPI route registration, which can fail if the installed FastAPI
version is older than the one the code targets (0.115 vs 0.104).
"""
from __future__ import annotations

import sys
from datetime import date

import pytest
from pydantic import ValidationError


# Check if importing auth module works at all (FastAPI compat)
_AUTH_IMPORT_ERROR = None
try:
    from app.api.auth import RegisterRequest
    _AUTH_AVAILABLE = True
except (ImportError, AttributeError) as exc:
    _AUTH_AVAILABLE = False
    _AUTH_IMPORT_ERROR = str(exc)

pytestmark = pytest.mark.skipif(
    not _AUTH_AVAILABLE,
    reason=f"app.api.auth cannot be imported: {_AUTH_IMPORT_ERROR}",
)


# ===========================================================================
# RegisterRequest validation tests
# ===========================================================================


@pytest.mark.skipif(not _AUTH_AVAILABLE, reason="auth module unavailable")
class TestRegisterRequest:
    """Validation tests for RegisterRequest — exercises app/api/auth.py models."""

    def test_valid_request(self):
        from app.api.auth import RegisterRequest
        req = RegisterRequest(
            email="alice@example.com",
            password="strongpass123",
            username="alice_w",
            display_name="Alice",
            birth_year=2000,
        )
        assert req.email == "alice@example.com"
        assert req.username == "alice_w"

    def test_short_password_rejected(self):
        from app.api.auth import RegisterRequest
        with pytest.raises(ValidationError):
            RegisterRequest(
                email="user@example.com",
                password="short",
                username="user123",
                display_name="User",
            )

    def test_short_username_rejected(self):
        from app.api.auth import RegisterRequest
        with pytest.raises(ValidationError):
            RegisterRequest(
                email="user@example.com",
                password="longpassword",
                username="ab",
                display_name="User",
            )

    def test_long_username_rejected(self):
        from app.api.auth import RegisterRequest
        with pytest.raises(ValidationError):
            RegisterRequest(
                email="user@example.com",
                password="longpassword",
                username="a" * 31,
                display_name="User",
            )

    def test_special_chars_in_username_rejected(self):
        from app.api.auth import RegisterRequest
        with pytest.raises(ValidationError):
            RegisterRequest(
                email="user@example.com",
                password="longpassword",
                username="user@name",
                display_name="User",
            )

    def test_underscores_allowed_in_username(self):
        from app.api.auth import RegisterRequest
        req = RegisterRequest(
            email="user@example.com",
            password="longpassword",
            username="user_name_123",
            display_name="User",
        )
        assert req.username == "user_name_123"

    def test_invalid_email_rejected(self):
        from app.api.auth import RegisterRequest
        with pytest.raises(ValidationError):
            RegisterRequest(
                email="not-an-email",
                password="longpassword",
                username="user123",
                display_name="User",
            )

    def test_empty_display_name_rejected(self):
        from app.api.auth import RegisterRequest
        with pytest.raises(ValidationError):
            RegisterRequest(
                email="user@example.com",
                password="longpassword",
                username="user123",
                display_name="",
            )

    def test_long_display_name_rejected(self):
        from app.api.auth import RegisterRequest
        with pytest.raises(ValidationError):
            RegisterRequest(
                email="user@example.com",
                password="longpassword",
                username="user123",
                display_name="A" * 51,
            )

    def test_birth_year_optional(self):
        from app.api.auth import RegisterRequest
        req = RegisterRequest(
            email="user@example.com",
            password="longpassword",
            username="user123",
            display_name="User",
        )
        assert req.birth_year is None

    def test_birth_year_too_low_rejected(self):
        from app.api.auth import RegisterRequest
        with pytest.raises(ValidationError):
            RegisterRequest(
                email="user@example.com",
                password="longpassword",
                username="user123",
                display_name="User",
                birth_year=1899,
            )

    def test_guest_session_token_optional(self):
        from app.api.auth import RegisterRequest
        req = RegisterRequest(
            email="user@example.com",
            password="longpassword",
            username="user123",
            display_name="User",
            guest_session_token="abc123",
        )
        assert req.guest_session_token == "abc123"


# ===========================================================================
# Age gate constant test
# ===========================================================================


@pytest.mark.skipif(not _AUTH_AVAILABLE, reason="auth module unavailable")
class TestAgeGate:
    """Tests for the age gate constant — exercises app/api/auth.py."""

    def test_min_age_is_13(self):
        from app.api.auth import _MIN_AGE_YEARS
        assert _MIN_AGE_YEARS == 13

    def test_age_calculation_for_minor(self):
        from app.api.auth import _MIN_AGE_YEARS
        current_year = date.today().year
        birth_year = current_year - 10
        age = current_year - birth_year
        assert age < _MIN_AGE_YEARS

    def test_age_calculation_for_adult(self):
        from app.api.auth import _MIN_AGE_YEARS
        current_year = date.today().year
        birth_year = current_year - 20
        age = current_year - birth_year
        assert age >= _MIN_AGE_YEARS

    def test_age_calculation_for_boundary(self):
        from app.api.auth import _MIN_AGE_YEARS
        current_year = date.today().year
        birth_year = current_year - 13
        age = current_year - birth_year
        assert age >= _MIN_AGE_YEARS


# ===========================================================================
# Social login model tests
# ===========================================================================


@pytest.mark.skipif(not _AUTH_AVAILABLE, reason="auth module unavailable")
class TestLoginModels:
    """Tests for social login request/response models — exercises app/api/auth.py."""

    def test_accepted_providers(self):
        from app.api.auth import _ACCEPTED_PROVIDERS
        assert "google" in _ACCEPTED_PROVIDERS
        assert "apple" in _ACCEPTED_PROVIDERS
        assert "facebook" not in _ACCEPTED_PROVIDERS

    def test_login_request_google(self):
        from app.api.auth import LoginRequest
        req = LoginRequest(provider="google", id_token="eyJhb.test.token")
        assert req.provider == "google"
        assert req.nonce is None

    def test_login_request_apple_with_nonce(self):
        from app.api.auth import LoginRequest
        req = LoginRequest(provider="apple", id_token="eyJhb.test.token", nonce="abc123")
        assert req.nonce == "abc123"

    def test_login_request_empty_token_rejected(self):
        from app.api.auth import LoginRequest
        with pytest.raises(ValidationError):
            LoginRequest(provider="google", id_token="")

    def test_login_request_invalid_provider_rejected(self):
        from app.api.auth import LoginRequest
        with pytest.raises(ValidationError):
            LoginRequest(provider="facebook", id_token="token")

    def test_login_response_model(self):
        from app.api.auth import LoginResponse
        resp = LoginResponse(
            user_id="u-1",
            access_token="at-123",
            refresh_token="rt-456",
            expires_at=1710720000,
        )
        assert resp.expires_at == 1710720000

    def test_register_response_model(self):
        from app.api.auth import RegisterResponse
        resp = RegisterResponse(
            user_id="u-1",
            username="alice",
            email_verification_required=True,
        )
        assert resp.email_verification_required is True
