"""Device-fingerprint rate limiter for registration endpoints.

Uses a Redis INCR + EXPIRE pattern:
- Key: reg_attempts:{fingerprint}
- TTL: 24 hours (86400 seconds)
- The TTL is set only on first creation to avoid resetting the window
  on each attempt (no sliding window — fixed 24h from first attempt).
"""
import redis.asyncio as aioredis

_REGISTRATION_LIMIT = 3
_WINDOW_SECONDS = 86_400  # 24 h


async def check_registration_rate_limit(
    fingerprint: str,
    r: aioredis.Redis,
) -> bool:
    """Increment attempt counter and return True if request is allowed.

    Returns False when the device has exceeded _REGISTRATION_LIMIT
    registration attempts within the 24-hour window.
    """
    key = f"reg_attempts:{fingerprint}"
    count = await r.incr(key)
    if count == 1:
        # Set TTL only on the first increment so the window is anchored
        # to the first attempt, not the most recent one.
        await r.expire(key, _WINDOW_SECONDS)
    return count <= _REGISTRATION_LIMIT
