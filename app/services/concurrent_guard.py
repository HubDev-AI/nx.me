"""Concurrent generation guard — standalone slot management module.

Uses an atomic Lua script (check-and-increment) so the check and the
increment are a single Redis round trip with no TOCTOU window.

Callers (e.g. app/api/glowup.py) must call ``release_slot`` in their
``except`` / ``finally`` block whenever ``acquire_slot`` returned ``True``
and the generation ultimately did not complete.
"""

from __future__ import annotations

import redis.asyncio as aioredis

from app.config import settings

# Lua script: atomic check-then-increment.
# Returns 1 if the slot was acquired (counter < limit), 0 if at capacity.
_ACQUIRE_SCRIPT = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
if current >= tonumber(ARGV[1]) then
    return 0
end
redis.call('INCR', KEYS[1])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
return 1
"""

# Module-level SHA cache — loaded lazily on first acquire call per process.
_acquire_sha: str | None = None


def _concurrent_key(user_id: str) -> str:
    return f"concurrent:{user_id}"


async def acquire_slot(
    redis: aioredis.Redis,
    user_id: str,
    ttl_seconds: int,
) -> bool:
    """Atomically acquire a concurrent generation slot for ``user_id``.

    Returns ``True`` if the slot was acquired; ``False`` if the user is
    already at ``MAX_CONCURRENT_GENERATIONS_PER_USER``.

    The TTL is set on the Redis counter so stale slots auto-expire if the
    worker crashes before calling ``release_slot``.
    """
    global _acquire_sha  # noqa: PLW0603

    if _acquire_sha is None:
        _acquire_sha = await redis.script_load(_ACQUIRE_SCRIPT)

    acquired = await redis.evalsha(
        _acquire_sha,
        1,
        _concurrent_key(user_id),
        str(settings.MAX_CONCURRENT_GENERATIONS_PER_USER),
        str(ttl_seconds),
    )
    return bool(acquired)


async def release_slot(redis: aioredis.Redis, user_id: str) -> None:
    """Decrement the concurrent slot counter for ``user_id``.

    Safe to call even if the counter is already 0 — ``DECR`` on a
    non-existent key sets it to -1, but the acquire script treats any
    value < limit as available, so the counter self-corrects on the next
    acquire.
    """
    await redis.decr(_concurrent_key(user_id))
