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
import redis.asyncio as aioredis

from app.config import settings


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
    count: int = results[0]
    if count <= settings.LOGIN_IP_LIMIT:
        return True, 0
    ttl: int = await r.ttl(key)
    return False, max(ttl, 0)
