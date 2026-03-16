"""Rate limiters for registration endpoints.

Both limiters use a Redis INCR + EXPIRE pattern (fixed window anchored to
the first attempt within the window).  All thresholds and window sizes are
sourced from app.config.settings — never hardcoded.

Limiters:
- Per-device fingerprint: REGISTRATION_FINGERPRINT_LIMIT / REGISTRATION_FINGERPRINT_WINDOW_SECONDS
- Per-IP address:         REGISTRATION_IP_LIMIT / REGISTRATION_IP_WINDOW_SECONDS
"""
import redis.asyncio as aioredis

from app.config import settings


async def check_registration_rate_limit(
    fingerprint: str,
    r: aioredis.Redis,
) -> bool:
    """Increment attempt counter and return True if request is allowed.

    Returns False when the device has exceeded REGISTRATION_FINGERPRINT_LIMIT
    registration attempts within REGISTRATION_FINGERPRINT_WINDOW_SECONDS
    (Story 2-1 AC-3).

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
    return count <= settings.REGISTRATION_FINGERPRINT_LIMIT


async def check_ip_registration_rate_limit(
    ip: str,
    r: aioredis.Redis,
) -> bool:
    """Increment per-IP attempt counter and return True if request is allowed.

    Returns False when the IP has exceeded REGISTRATION_IP_LIMIT registration
    attempts within REGISTRATION_IP_WINDOW_SECONDS (Story 2-2 AC-4).

    See ``check_registration_rate_limit`` for the atomic pipeline rationale.
    """
    key = f"reg_ip_limit:{ip}"
    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, settings.REGISTRATION_IP_WINDOW_SECONDS, nx=True)
    results = await pipe.execute()
    count: int = results[0]
    return count <= settings.REGISTRATION_IP_LIMIT


async def check_login_rate_limit(
    ip: str,
    r: aioredis.Redis,
) -> bool:
    """Per-IP rate limit for POST /login (CS-1 AC-4).

    Reuses the same window/limit as registration IP rate limiting.
    Returns False when the IP has exceeded REGISTRATION_IP_LIMIT login
    attempts within REGISTRATION_IP_WINDOW_SECONDS.
    """
    key = f"login_ip_limit:{ip}"
    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, settings.REGISTRATION_IP_WINDOW_SECONDS, nx=True)
    results = await pipe.execute()
    count: int = results[0]
    return count <= settings.REGISTRATION_IP_LIMIT
