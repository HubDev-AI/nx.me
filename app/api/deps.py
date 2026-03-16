"""FastAPI dependency providers.

Shared dependencies injected into route handlers via Depends().
"""
from __future__ import annotations

import logging
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from supabase import Client

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Infrastructure deps
# ---------------------------------------------------------------------------


def get_supabase(request: Request) -> Client:
    """Return the Supabase service-role client attached to app state."""
    return request.app.state.supabase


def get_redis(request: Request) -> aioredis.Redis:
    """Return the async Redis client attached to app state."""
    return request.app.state.redis


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    supabase: Client = Depends(get_supabase),
) -> dict:
    """Validate the Bearer JWT and return the decoded claims.

    Raises HTTP 401 if the token is missing, expired, or invalid.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.removeprefix("Bearer ").strip()

    try:
        claims = jwt.decode(
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
