"""Rate limiters for registration and login endpoints.

Both limiters use a Redis INCR + EXPIRE pattern (fixed window anchored to
the first attempt within the window).  All thresholds and window sizes are
sourced from app.config.settings — never hardcoded.

Limiters:
- Per-device fingerprint: REGISTRATION_FINGERPRINT_LIMIT / REGISTRATION_FINGERPRINT_WINDOW_SECONDS
- Per-IP address (reg):   REGISTRATION_IP_LIMIT / REGISTRATION_IP_WINDOW_SECONDS
- Per-IP address (login): LOGIN_IP_LIMIT / LOGIN_IP_WINDOW_SECONDS

Return values (LE-1):
- Each check function returns a tuple (allowed: bool, ttl: int).
  When allowed is False, ttl holds the Redis TTL in seconds so callers can
  include a ``Retry-After`` header in the 429 response.
  When allowed is True, ttl is 0.
"""

import logging

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)


async def check_registration_rate_limit(
    fingerprint: str,
    r: aioredis.Redis,
) -> tuple[bool, int]:
    """Increment attempt counter and return (allowed, ttl).

    allowed is False when the device has exceeded REGISTRATION_FINGERPRINT_LIMIT
    registration attempts within REGISTRATION_FINGERPRINT_WINDOW_SECONDS
    (Story 2-1 AC-3).  ttl is the remaining window seconds when denied.

    Uses a Redis pipeline so INCR and EXPIRE are sent atomically in a single
    round-trip.  ``EXPIRE … NX`` sets the TTL only when the key has none,
    which anchors the window to the *first* attempt rather than the most recent
    and eliminates the permanent-lockout risk of a separate EXPIRE call.
    """
    key = f"reg_attempts:{fingerprint}"
    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, settings.REGISTRATION_FINGERPRINT_WINDOW_SECONDS, nx=True)
    results = await pipe.execute()
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(
                "Redis pipeline command %d failed in check_registration_rate_limit: %s",
                i,
                result,
            )
    count: int = results[0]
    if count <= settings.REGISTRATION_FINGERPRINT_LIMIT:
        return True, 0
    ttl: int = await r.ttl(key)
    return False, max(ttl, 0)


async def check_ip_registration_rate_limit(
    ip: str,
    r: aioredis.Redis,
) -> tuple[bool, int]:
    """Increment per-IP attempt counter and return (allowed, ttl).

    allowed is False when the IP has exceeded REGISTRATION_IP_LIMIT registration
    attempts within REGISTRATION_IP_WINDOW_SECONDS (Story 2-2 AC-4).
    ttl is the remaining window seconds when denied.

    See ``check_registration_rate_limit`` for the atomic pipeline rationale.
    """
    key = f"reg_ip_limit:{ip}"
    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, settings.REGISTRATION_IP_WINDOW_SECONDS, nx=True)
    results = await pipe.execute()
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(
                "Redis pipeline command %d failed in check_ip_registration_rate_limit: %s",
                i,
                result,
            )
    count: int = results[0]
    if count <= settings.REGISTRATION_IP_LIMIT:
        return True, 0
    ttl: int = await r.ttl(key)
    return False, max(ttl, 0)


async def check_login_rate_limit(
    ip: str,
    r: aioredis.Redis,
) -> tuple[bool, int]:
    """Per-IP rate limit for POST /login (CS-1 AC-4, LE-5).

    Uses LOGIN_IP_LIMIT and LOGIN_IP_WINDOW_SECONDS (independent from
    registration — LE-5).  Returns (allowed, ttl); ttl is the remaining
    window seconds when denied so the caller can send a Retry-After header.
    """
    key = f"login_ip_limit:{ip}"
    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, settings.LOGIN_IP_WINDOW_SECONDS, nx=True)
    results = await pipe.execute()
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(
                "Redis pipeline command %d failed in check_login_rate_limit: %s",
                i,
                result,
            )
    count: int = results[0]
    if count <= settings.LOGIN_IP_LIMIT:
        return True, 0
    ttl: int = await r.ttl(key)
    return False, max(ttl, 0)


# ---------------------------------------------------------------------------
# Per-user rate limit for DELETE /auth/account (SEC-005)
# ---------------------------------------------------------------------------

# 3 attempts per 10 minutes — generous enough for honest retry after a
# transient 502, tight enough to prevent a stolen JWT from grinding the
# paginated reads.
_DELETE_ACCOUNT_WINDOW_SECONDS = 600  # 10 minutes
_DELETE_ACCOUNT_MAX_ATTEMPTS = 3


async def check_delete_account_rate_limit(
    user_id: str, r: aioredis.Redis
) -> tuple[bool, int]:
    """Return (allowed, retry_after_seconds).

    Uses the same INCR + EXPIRE NX pattern as the other limiters in this
    module. Key: ``delete_account_rate:{user_id}``.
    """
    key = f"delete_account_rate:{user_id}"
    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, _DELETE_ACCOUNT_WINDOW_SECONDS, nx=True)
    results = await pipe.execute()
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(
                "Redis pipeline command %d failed in check_delete_account_rate_limit: %s",
                i,
                result,
            )
    count: int = results[0]
    if count <= _DELETE_ACCOUNT_MAX_ATTEMPTS:
        return True, 0
    ttl: int = await r.ttl(key)
    return False, max(ttl, 1)


# ---------------------------------------------------------------------------
# Per-caller rate limit for DELETE /v1/jobs/{job_id} (Unit 5, Plan §R3)
# ---------------------------------------------------------------------------

# 10 deletes per minute per caller. Tight enough to defuse a stolen-token
# sweep (which would otherwise pound blob storage and inflate the orphan
# DLQ), loose enough that a user cleaning up 5-6 old glow-ups back-to-back
# never feels it. Keyed on the claim ``sub`` (the authenticated user UUID).
_DELETE_GLOWUP_WINDOW_SECONDS = 60
_DELETE_GLOWUP_MAX_ATTEMPTS = 10


async def check_delete_glowup_rate_limit(
    user_id: str, r: aioredis.Redis
) -> tuple[bool, int]:
    """Return ``(allowed, retry_after_seconds)`` for DELETE /jobs/{id}.

    Mirrors :func:`check_delete_account_rate_limit` — same INCR + EXPIRE NX
    pattern, separate key namespace and separate constants so the two
    limits don't share a counter. Key: ``delete_glowup_rate:{user_id}``.

    **Call-site contract (real deletes only):** this function INCRements
    the counter on every call, so ``app/api/jobs.py::delete_job`` invokes
    it AFTER the fetch + owner check — only when the request is about to
    do real destructive work. No-op 204s (missing job, wrong owner,
    already deleted) must bypass this helper; otherwise a stolen token
    looping stale IDs could DoS the real owner out of their own budget
    via the idempotent-204 path. Budget applies to "actual deletes", not
    "DELETE requests".
    """
    key = f"delete_glowup_rate:{user_id}"
    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, _DELETE_GLOWUP_WINDOW_SECONDS, nx=True)
    results = await pipe.execute()
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(
                "Redis pipeline command %d failed in check_delete_glowup_rate_limit: %s",
                i,
                result,
            )
    count: int = results[0]
    if count <= _DELETE_GLOWUP_MAX_ATTEMPTS:
        return True, 0
    ttl: int = await r.ttl(key)
    return False, max(ttl, 1)
