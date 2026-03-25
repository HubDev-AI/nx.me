"""JWT validation middleware.

Supports both HS256 (production Supabase) and ES256 (local Supabase CLI v2+).

ES256 keys are fetched from the Supabase JWKS endpoint using httpx (not
PyJWKClient, which uses blocking urllib internally and can fail inside an
asyncio event loop).  The key is pre-fetched at app startup via
``prefetch_jwks_key()`` and cached with a configurable TTL so that key
rotations are picked up automatically.
"""
from __future__ import annotations

import logging
import sys
import threading
import time

if sys.version_info >= (3, 11):
    from typing import Required, TypedDict
else:
    from typing import TypedDict
    from typing_extensions import Required

import httpx
import jwt
from jwt import PyJWK
from fastapi import HTTPException

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ES256 JWKS key cache
# ---------------------------------------------------------------------------
_JWKS_CACHE_TTL_SECONDS = 300  # Re-fetch JWKS every 5 minutes

_es256_key_lock = threading.Lock()
_es256_key = None  # Cached cryptographic key object
_es256_key_fetched_at: float = 0.0  # Monotonic timestamp of last fetch


class UserClaims(TypedDict, total=False):
    sub: Required[str]
    exp: Required[int]
    email: str
    iat: int
    role: str
    aud: str


# ---------------------------------------------------------------------------
# JWKS key fetching (httpx-based, no urllib)
# ---------------------------------------------------------------------------

def _jwks_url() -> str:
    return f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"


def _fetch_es256_key_sync() -> object:
    """Fetch the ES256 signing key from the JWKS endpoint using httpx.

    This is a synchronous call meant for use in startup or from a
    thread-pool.  It does NOT use PyJWKClient (which relies on urllib).
    """
    url = _jwks_url()
    resp = httpx.get(url, timeout=5.0)
    resp.raise_for_status()
    jwks = resp.json()

    # Find the ES256 signing key in the JWKS key set
    for key_data in jwks.get("keys", []):
        if key_data.get("kty") == "EC" and key_data.get("use", "sig") == "sig":
            return PyJWK(key_data).key

    raise ValueError("No EC signing key found in JWKS endpoint")


async def prefetch_jwks_key() -> None:
    """Pre-fetch the ES256 JWKS key at application startup.

    Called from the FastAPI lifespan handler so the key is ready before
    the first request arrives.  Uses httpx.AsyncClient for a clean async
    fetch.
    """
    global _es256_key, _es256_key_fetched_at

    url = _jwks_url()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=5.0)
            resp.raise_for_status()
            jwks = resp.json()

        for key_data in jwks.get("keys", []):
            if key_data.get("kty") == "EC" and key_data.get("use", "sig") == "sig":
                _es256_key = PyJWK(key_data).key
                _es256_key_fetched_at = time.monotonic()
                logger.info("ES256 JWKS key pre-fetched from %s", url)
                return

        logger.warning("No EC signing key found at %s — ES256 tokens will fail", url)
    except Exception as exc:
        # Non-fatal at startup: HS256 tokens will still work, and the key
        # will be fetched lazily on the first ES256 request.
        logger.warning("Failed to pre-fetch JWKS key from %s: %s", url, exc)


def _get_es256_key() -> object:
    """Return the cached ES256 key, refreshing if stale or missing.

    Thread-safe.  Uses a short lock to prevent thundering-herd on
    concurrent cache misses.
    """
    global _es256_key, _es256_key_fetched_at

    now = time.monotonic()
    if _es256_key is not None and (now - _es256_key_fetched_at) < _JWKS_CACHE_TTL_SECONDS:
        return _es256_key

    with _es256_key_lock:
        # Double-check after acquiring lock
        now = time.monotonic()
        if _es256_key is not None and (now - _es256_key_fetched_at) < _JWKS_CACHE_TTL_SECONDS:
            return _es256_key

        try:
            _es256_key = _fetch_es256_key_sync()
            _es256_key_fetched_at = now
            logger.info("ES256 JWKS key refreshed")
        except Exception as exc:
            if _es256_key is not None:
                # Stale key is better than no key — log and reuse
                logger.warning("JWKS refresh failed, using stale key: %s", exc)
                _es256_key_fetched_at = now  # Reset TTL to avoid retry storm
            else:
                raise

    return _es256_key


# ---------------------------------------------------------------------------
# JWT validation
# ---------------------------------------------------------------------------

def validate_jwt(token: str) -> UserClaims:
    """Validate a Supabase JWT and return the decoded claims.

    Supports HS256 (production) and ES256 (local Supabase CLI v2+).
    Raises ``HTTPException(401)`` on any validation failure.
    """
    decode_opts = dict(
        options={"require": ["sub", "exp"]},
        audience="authenticated",
        issuer=f"{settings.SUPABASE_URL}/auth/v1",
    )

    # Peek at the header to determine algorithm
    try:
        header = jwt.get_unverified_header(token)
    except jwt.DecodeError:
        raise HTTPException(status_code=401, detail="Invalid token")

    alg = header.get("alg", "HS256")

    try:
        if alg == "HS256":
            return jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                **decode_opts,
            )
        else:
            # ES256 — use cached JWKS key (pre-fetched at startup)
            key = _get_es256_key()
            return jwt.decode(token, key, algorithms=["ES256"], **decode_opts)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        logger.debug("JWT validation failed: %s", exc)
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
