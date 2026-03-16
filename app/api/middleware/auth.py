"""JWT validation middleware.

Interface Contract (Story 2-2):
  validate_jwt(token: str) -> UserClaims
  Location: api/middleware/auth.py

UserClaims is a TypedDict representing the decoded Supabase JWT payload.
"""
from __future__ import annotations

import logging
from typing import TypedDict

import jwt
from fastapi import HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)


class UserClaims(TypedDict, total=False):
    """Decoded Supabase JWT claims."""

    sub: str           # User UUID (required)
    email: str         # User email (optional — social login may omit)
    exp: int           # Expiry timestamp
    iat: int           # Issued-at timestamp
    role: str          # Supabase role (e.g. "authenticated")
    aud: str           # Audience


def validate_jwt(token: str) -> UserClaims:
    """Decode and validate a Supabase-issued Bearer JWT.

    Validates signature (HS256 + SUPABASE_JWT_SECRET), expiry, and
    presence of required ``sub`` and ``exp`` claims.

    Args:
        token: Raw JWT string (without "Bearer " prefix).

    Returns:
        Decoded claims dict as UserClaims.

    Raises:
        HTTPException 401: If the token is expired, has an invalid
            signature, or is missing required claims.
    """
    try:
        claims: UserClaims = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"require": ["sub", "exp"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        logger.debug("JWT validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return claims
