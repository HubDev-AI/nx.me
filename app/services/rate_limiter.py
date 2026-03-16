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
    """
    key = f"reg_attempts:{fingerprint}"
    count = await r.incr(key)
    if count == 1:
        # Set TTL only on the first increment so the window is anchored
        # to the first attempt, not the most recent one.
        await r.expire(key, settings.REGISTRATION_FINGERPRINT_WINDOW_SECONDS)
    return count <= settings.REGISTRATION_FINGERPRINT_LIMIT


async def check_ip_registration_rate_limit(
    ip: str,
    r: aioredis.Redis,
) -> bool:
    """Increment per-IP attempt counter and return True if request is allowed.

    Returns False when the IP has exceeded REGISTRATION_IP_LIMIT registration
    attempts within REGISTRATION_IP_WINDOW_SECONDS (Story 2-2 AC-4).
    """
    key = f"reg_ip_limit:{ip}"
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, settings.REGISTRATION_IP_WINDOW_SECONDS)
    return count <= settings.REGISTRATION_IP_LIMIT
