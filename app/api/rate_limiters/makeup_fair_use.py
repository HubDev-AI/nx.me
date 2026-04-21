"""Makeup fair-use cap — per-user rolling 24h generation quota.

Wraps the Lua scripts as Python callables. Both functions load their script
via EVALSHA on first call and cache the SHA for subsequent calls.

Key layout:
  makeup:quota:{user_id}                    — rolling daily counter
  makeup:quota:txn:{user_id}:{namespaced}   — per-submission idempotency marker

The txn marker is the authoritative "this submission consumed quota" record.
Its presence makes the decrement safe to call multiple times (idempotent).
"""

from __future__ import annotations

import logging
from pathlib import Path

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_INCR_LUA = (Path(__file__).parent / "makeup_fair_use_incr.lua").read_text()
_DECR_LUA = (Path(__file__).parent / "makeup_fair_use_decr.lua").read_text()

_incr_sha: str | None = None
_decr_sha: str | None = None


async def _load_incr(r: aioredis.Redis) -> str:
    global _incr_sha
    if _incr_sha is None:
        _incr_sha = await r.script_load(_INCR_LUA)
    return _incr_sha


async def _load_decr(r: aioredis.Redis) -> str:
    global _decr_sha
    if _decr_sha is None:
        _decr_sha = await r.script_load(_DECR_LUA)
    return _decr_sha


async def fair_use_incr(
    r: aioredis.Redis,
    user_id: str,
    namespaced_key: str,
) -> tuple[bool, int]:
    """Charge one unit against the user's daily makeup cap.

    Returns ``(allowed, new_count)``.
    ``allowed`` is False when the cap would be exceeded — counter is rolled back
    and no txn marker is written.
    """
    counter_key = f"makeup:quota:{user_id}"
    cap = settings.MAKEUP_FAIR_USE_DAILY_CAP
    txn_ttl = 86400  # 24h, matches counter window

    sha = await _load_incr(r)
    result = await r.evalsha(
        sha,
        1,  # numkeys
        counter_key,
        namespaced_key,
        str(cap),
        str(txn_ttl),
        user_id,
    )
    new_count, already_charged = int(result[0]), int(result[1])
    if already_charged:
        # Marker already exists — idempotent replay from incr side.
        return True, new_count
    allowed = new_count >= 0
    return allowed, max(new_count, 0)


async def fair_use_decr(
    r: aioredis.Redis,
    user_id: str,
    namespaced_key: str,
) -> bool:
    """Return one unit to the user's daily cap on non-retryable terminal.

    Idempotent — safe to call multiple times; second call is a no-op.
    Returns True if a decrement happened, False if already a no-op.
    """
    counter_key = f"makeup:quota:{user_id}"
    sha = await _load_decr(r)
    result = await r.evalsha(sha, 1, counter_key, namespaced_key, user_id)
    return bool(result)
