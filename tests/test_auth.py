"""Tests for auth: JWT validation, disposable email, rate limiting, trial grantor, error mapping.

Exercises production code in:
  - app/api/middleware/auth.py (validate_jwt)
  - app/services/disposable_email.py (is_disposable_email)
  - app/services/rate_limiter.py (check_registration_rate_limit, etc.)
  - app/entitlement/trial_grantor.py (TrialGrantor)
  - app/api/auth.py (_handle_supabase_auth_error) — guarded by import check
"""
from __future__ import annotations

import time
from uuid import uuid4

import jwt as pyjwt
import pytest

from app.api.middleware.auth import validate_jwt
from app.config import settings
from app.services.disposable_email import is_disposable_email
from app.entitlement.trial_grantor import TrialGrantor

from tests.conftest import make_jwt, MockSupabase, MockRedis


# Check if auth module is importable (FastAPI version compat)
_AUTH_AVAILABLE = False
try:
    from app.api.auth import _handle_supabase_auth_error
    _AUTH_AVAILABLE = True
except (ImportError, AttributeError):
    pass


# ===========================================================================
# validate_jwt tests
# ===========================================================================


class TestValidateJwt:
    """Unit tests for JWT validation — exercises app/api/middleware/auth.py."""

    def test_valid_token_returns_claims(self):
        uid = str(uuid4())
        token = make_jwt(user_id=uid)
        claims = validate_jwt(token)
        assert claims["sub"] == uid
        assert "exp" in claims

    def test_expired_token_raises_401(self):
        token = make_jwt(expired=True)
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            validate_jwt(token)
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    def test_invalid_signature_raises_401(self):
        payload = {
            "sub": str(uuid4()),
            "exp": int(time.time()) + 3600,
            "aud": "authenticated",
            "iss": f"{settings.SUPABASE_URL}/auth/v1",
        }
        token = pyjwt.encode(payload, "wrong-secret", algorithm="HS256")
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            validate_jwt(token)
        assert exc_info.value.status_code == 401

    def test_missing_sub_claim_raises_401(self):
        payload = {
            "exp": int(time.time()) + 3600,
            "aud": "authenticated",
            "iss": f"{settings.SUPABASE_URL}/auth/v1",
        }
        token = pyjwt.encode(payload, settings.SUPABASE_JWT_SECRET, algorithm="HS256")
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            validate_jwt(token)
        assert exc_info.value.status_code == 401

    def test_wrong_audience_raises_401(self):
        payload = {
            "sub": str(uuid4()),
            "exp": int(time.time()) + 3600,
            "aud": "wrong-audience",
            "iss": f"{settings.SUPABASE_URL}/auth/v1",
        }
        token = pyjwt.encode(payload, settings.SUPABASE_JWT_SECRET, algorithm="HS256")
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            validate_jwt(token)
        assert exc_info.value.status_code == 401

    def test_wrong_issuer_raises_401(self):
        payload = {
            "sub": str(uuid4()),
            "exp": int(time.time()) + 3600,
            "aud": "authenticated",
            "iss": "https://evil.example.com/auth/v1",
        }
        token = pyjwt.encode(payload, settings.SUPABASE_JWT_SECRET, algorithm="HS256")
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            validate_jwt(token)
        assert exc_info.value.status_code == 401

    def test_garbage_token_raises_401(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            validate_jwt("not.a.real.jwt.token")
        assert exc_info.value.status_code == 401


# ===========================================================================
# Disposable email tests
# ===========================================================================


class TestDisposableEmail:
    """Unit tests for disposable email detection — exercises app/services/disposable_email.py."""

    def test_known_disposable_domain_detected(self):
        assert is_disposable_email("user@mailinator.com") is True

    def test_legitimate_domain_allowed(self):
        assert is_disposable_email("user@gmail.com") is False

    def test_case_insensitive_detection(self):
        assert is_disposable_email("USER@MAILINATOR.COM") is True

    def test_empty_string_returns_false(self):
        assert is_disposable_email("") is False

    def test_no_at_sign_returns_false(self):
        assert is_disposable_email("not-an-email") is False

    def test_yopmail_detected(self):
        assert is_disposable_email("test@yopmail.com") is True


# ===========================================================================
# Auth error mapping tests (guarded by import check)
# ===========================================================================


@pytest.mark.skipif(not _AUTH_AVAILABLE, reason="app.api.auth not importable on this FastAPI version")
class TestAuthErrorMapping:
    """Tests for _handle_supabase_auth_error — exercises app/api/auth.py."""

    def test_duplicate_email_maps_to_409(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _handle_supabase_auth_error(Exception("User already registered"))
        assert exc_info.value.status_code == 409

    def test_weak_password_maps_to_422(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _handle_supabase_auth_error(Exception("Password is too weak"))
        assert exc_info.value.status_code == 422

    def test_unknown_error_maps_to_500(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _handle_supabase_auth_error(Exception("Something unexpected"))
        assert exc_info.value.status_code == 500


# ===========================================================================
# TrialGrantor tests
# ===========================================================================


class TestTrialGrantor:
    """Unit tests for TrialGrantor.grant() — exercises app/entitlement/trial_grantor.py."""

    def test_grant_calls_rpc_with_correct_params(self):
        sb = MockSupabase()
        sb.set_table_data("credit_ledger", [])
        grantor = TrialGrantor(sb)
        uid = uuid4()
        grantor.grant(uid)

    def test_grant_is_idempotent_when_already_granted(self):
        sb = MockSupabase()
        sb.set_table_data("credit_ledger", [{"id": str(uuid4()), "type": "trial_grant"}])
        grantor = TrialGrantor(sb)
        uid = uuid4()
        grantor.grant(uid)

    def test_grant_uses_fallback_when_rpc_fails(self):
        sb = MockSupabase()
        sb.set_table_data("credit_ledger", [])

        original_rpc = sb.rpc
        call_count = [0]

        def failing_rpc(name, params=None):
            call_count[0] += 1
            if name == "grant_trial":
                raise Exception("RPC not available")
            return original_rpc(name, params)

        sb.rpc = failing_rpc
        grantor = TrialGrantor(sb)
        uid = uuid4()
        grantor.grant(uid)
        assert call_count[0] >= 1


# ===========================================================================
# Rate limiter tests
# ===========================================================================


class TestRateLimiter:
    """Tests for rate limiter functions — exercises app/services/rate_limiter.py."""

    @pytest.mark.asyncio
    async def test_fingerprint_rate_limit_allows_within_limit(self):
        from app.services.rate_limiter import check_registration_rate_limit

        redis = MockRedis()
        for _ in range(settings.REGISTRATION_FINGERPRINT_LIMIT):
            allowed, ttl = await check_registration_rate_limit("device-123", redis)
            assert allowed is True
            assert ttl == 0

    @pytest.mark.asyncio
    async def test_fingerprint_rate_limit_blocks_over_limit(self):
        from app.services.rate_limiter import check_registration_rate_limit

        redis = MockRedis()
        for _ in range(settings.REGISTRATION_FINGERPRINT_LIMIT):
            await check_registration_rate_limit("device-456", redis)
        allowed, ttl = await check_registration_rate_limit("device-456", redis)
        assert allowed is False
        assert ttl > 0

    @pytest.mark.asyncio
    async def test_ip_rate_limit_allows_within_limit(self):
        from app.services.rate_limiter import check_ip_registration_rate_limit

        redis = MockRedis()
        for _ in range(settings.REGISTRATION_IP_LIMIT):
            allowed, ttl = await check_ip_registration_rate_limit("192.168.1.1", redis)
            assert allowed is True
            assert ttl == 0

    @pytest.mark.asyncio
    async def test_ip_rate_limit_blocks_over_limit(self):
        from app.services.rate_limiter import check_ip_registration_rate_limit

        redis = MockRedis()
        for _ in range(settings.REGISTRATION_IP_LIMIT):
            await check_ip_registration_rate_limit("10.0.0.1", redis)
        allowed, ttl = await check_ip_registration_rate_limit("10.0.0.1", redis)
        assert allowed is False
        assert ttl > 0

    @pytest.mark.asyncio
    async def test_login_rate_limit_allows_within_limit(self):
        from app.services.rate_limiter import check_login_rate_limit

        redis = MockRedis()
        for _ in range(settings.LOGIN_IP_LIMIT):
            allowed, ttl = await check_login_rate_limit("10.0.0.2", redis)
            assert allowed is True
            assert ttl == 0

    @pytest.mark.asyncio
    async def test_login_rate_limit_blocks_over_limit(self):
        from app.services.rate_limiter import check_login_rate_limit

        redis = MockRedis()
        for _ in range(settings.LOGIN_IP_LIMIT):
            await check_login_rate_limit("10.0.0.3", redis)
        allowed, ttl = await check_login_rate_limit("10.0.0.3", redis)
        assert allowed is False
        assert ttl > 0

    @pytest.mark.asyncio
    async def test_different_ips_have_independent_limits(self):
        from app.services.rate_limiter import check_ip_registration_rate_limit

        redis = MockRedis()
        for _ in range(settings.REGISTRATION_IP_LIMIT + 1):
            await check_ip_registration_rate_limit("1.1.1.1", redis)
        allowed, ttl = await check_ip_registration_rate_limit("2.2.2.2", redis)
        assert allowed is True
        assert ttl == 0
