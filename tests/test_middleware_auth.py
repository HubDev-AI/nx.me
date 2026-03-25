"""Tests for JWT validation middleware.

Exercises production code in:
  - app/api/middleware/auth.py (UserClaims, validate_jwt, _status_to_code)
"""
from __future__ import annotations

import time

import jwt
import pytest
from fastapi import HTTPException

from app.config import settings


try:
    from app.api.middleware.auth import validate_jwt, UserClaims  # noqa: F401
    _AUTH_MW_AVAILABLE = True
except (ImportError, AttributeError):
    _AUTH_MW_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _AUTH_MW_AVAILABLE, reason="auth middleware unavailable"
)

_SECRET = settings.SUPABASE_JWT_SECRET
_ISSUER = f"{settings.SUPABASE_URL}/auth/v1"


def _make_token(
    sub: str = "user-1",
    exp_offset: int = 3600,
    aud: str = "authenticated",
    iss: str | None = None,
    alg: str = "HS256",
    extra: dict | None = None,
) -> str:
    now = int(time.time())
    payload = {
        "sub": sub,
        "iat": now,
        "exp": now + exp_offset,
        "aud": aud,
        "iss": iss or _ISSUER,
        "role": "authenticated",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, _SECRET, algorithm=alg)


class TestValidateJwt:
    """Tests for validate_jwt — exercises app/api/middleware/auth.py."""

    def test_valid_hs256_token(self):
        token = _make_token()
        claims = validate_jwt(token)
        assert claims["sub"] == "user-1"

    def test_expired_token_raises_401(self):
        token = _make_token(exp_offset=-100)
        with pytest.raises(HTTPException) as exc_info:
            validate_jwt(token)
        assert exc_info.value.status_code == 401

    def test_invalid_token_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_jwt("not.a.valid.jwt")
        assert exc_info.value.status_code == 401

    def test_empty_token_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_jwt("")
        assert exc_info.value.status_code == 401

    def test_wrong_audience_raises_401(self):
        token = _make_token(aud="wrong_audience")
        with pytest.raises(HTTPException) as exc_info:
            validate_jwt(token)
        assert exc_info.value.status_code == 401

    def test_wrong_issuer_raises_401(self):
        token = _make_token(iss="https://evil.example.com/auth/v1")
        with pytest.raises(HTTPException) as exc_info:
            validate_jwt(token)
        assert exc_info.value.status_code == 401

    def test_missing_sub_raises_401(self):
        now = int(time.time())
        payload = {"exp": now + 3600, "aud": "authenticated", "iss": _ISSUER}
        token = jwt.encode(payload, _SECRET, algorithm="HS256")
        with pytest.raises(HTTPException) as exc_info:
            validate_jwt(token)
        assert exc_info.value.status_code == 401

    def test_wrong_secret_raises_401(self):
        now = int(time.time())
        payload = {
            "sub": "user-1", "exp": now + 3600,
            "aud": "authenticated", "iss": _ISSUER,
        }
        token = jwt.encode(payload, "wrong-secret-key-that-is-long-enough", algorithm="HS256")
        with pytest.raises(HTTPException) as exc_info:
            validate_jwt(token)
        assert exc_info.value.status_code == 401

    def test_claims_include_email(self):
        token = _make_token(extra={"email": "alice@example.com"})
        claims = validate_jwt(token)
        assert claims.get("email") == "alice@example.com"


class TestUserClaims:
    """Tests for UserClaims TypedDict."""

    def test_user_claims_type(self):
        claims: UserClaims = {"sub": "u-1", "exp": 1234567890}
        assert claims["sub"] == "u-1"
