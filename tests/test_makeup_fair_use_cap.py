"""Unit tests for fair_use_incr and fair_use_decr Python wrappers.

MockRedis does not support EVALSHA, so tests mock r.evalsha and r.script_load
directly to verify what the Python wrappers do with the Lua return values.

Lua return values:
  incr: [new_count, already_charged]  — already_charged=1 means txn marker existed
  decr: [decremented]                 — 1 if marker existed, 0 if no-op
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


async def _make_redis(evalsha_return: list) -> AsyncMock:
    """Return an AsyncMock Redis with script_load + evalsha pre-configured."""
    r = AsyncMock()
    r.script_load = AsyncMock(return_value="fake_sha_abc")
    r.evalsha = AsyncMock(return_value=evalsha_return)
    return r


# ---------------------------------------------------------------------------
# fair_use_incr
# ---------------------------------------------------------------------------


class TestFairUseIncr:
    @pytest.mark.asyncio
    async def test_allowed_when_under_cap(self):
        from app.api.rate_limiters.makeup_fair_use import fair_use_incr

        r = await _make_redis([1, 0])  # count=1, not already_charged
        allowed, count = await fair_use_incr(r, "user-1", "makeup:key-a")
        assert allowed is True
        assert count == 1

    @pytest.mark.asyncio
    async def test_denied_when_over_cap(self):
        """Lua returns -1 sentinel when cap would be exceeded."""
        from app.api.rate_limiters.makeup_fair_use import fair_use_incr

        r = await _make_redis([-1, 0])
        allowed, count = await fair_use_incr(r, "user-1", "makeup:key-b")
        assert allowed is False
        assert count == 0

    @pytest.mark.asyncio
    async def test_count_clamped_to_zero_when_denied(self):
        """Count must never be negative in the Python layer."""
        from app.api.rate_limiters.makeup_fair_use import fair_use_incr

        r = await _make_redis([-5, 0])
        allowed, count = await fair_use_incr(r, "user-1", "makeup:key-c")
        assert allowed is False
        assert count == 0

    @pytest.mark.asyncio
    async def test_already_charged_returns_allowed_true(self):
        """Replay: txn marker existed, counter NOT touched → allowed=True."""
        from app.api.rate_limiters.makeup_fair_use import fair_use_incr

        r = await _make_redis([5, 1])  # already_charged=1
        allowed, count = await fair_use_incr(r, "user-1", "makeup:key-d")
        assert allowed is True
        assert count == 5

    @pytest.mark.asyncio
    async def test_evalsha_receives_counter_key(self):
        """Counter key must be makeup:quota:{user_id} per key layout contract."""
        from app.api.rate_limiters.makeup_fair_use import fair_use_incr

        r = await _make_redis([1, 0])
        await fair_use_incr(r, "user-42", "makeup:test-key")

        # evalsha(sha, numkeys, KEYS[1], ARGV[1], ...)
        call_args = r.evalsha.call_args[0]
        counter_key = call_args[2]  # third positional = KEYS[1]
        assert counter_key == "makeup:quota:user-42"

    @pytest.mark.asyncio
    async def test_loads_script_when_sha_not_cached(self):
        from app.api.rate_limiters import makeup_fair_use
        from app.api.rate_limiters.makeup_fair_use import fair_use_incr

        original = makeup_fair_use._incr_sha
        try:
            makeup_fair_use._incr_sha = None
            r = await _make_redis([1, 0])
            await fair_use_incr(r, "user-1", "makeup:key-e")
            r.script_load.assert_awaited_once()
        finally:
            makeup_fair_use._incr_sha = original

    @pytest.mark.asyncio
    async def test_reuses_cached_sha_on_second_call(self):
        from app.api.rate_limiters.makeup_fair_use import fair_use_incr

        r = await _make_redis([1, 0])
        await fair_use_incr(r, "user-1", "makeup:key-f")
        await fair_use_incr(r, "user-1", "makeup:key-g")
        # script_load called at most once (SHA cached after first call)
        assert r.script_load.await_count <= 1


# ---------------------------------------------------------------------------
# fair_use_decr
# ---------------------------------------------------------------------------


class TestFairUseDecr:
    @pytest.mark.asyncio
    async def test_returns_true_when_decrement_happened(self):
        from app.api.rate_limiters.makeup_fair_use import fair_use_decr

        r = await _make_redis(1)  # Lua returns scalar 1 when marker existed
        result = await fair_use_decr(r, "user-1", "makeup:key-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_no_op(self):
        """Marker absent → no decrement → Lua returns 0 → False."""
        from app.api.rate_limiters.makeup_fair_use import fair_use_decr

        r = await _make_redis(0)  # Lua returns scalar 0 (no-op)
        result = await fair_use_decr(r, "user-1", "makeup:key-2")
        assert result is False

    @pytest.mark.asyncio
    async def test_idempotent_second_call_is_noop(self):
        """Calling decr twice for the same key: second call returns False."""
        from app.api.rate_limiters.makeup_fair_use import fair_use_decr

        r = await _make_redis(0)  # both calls are no-ops
        await fair_use_decr(r, "user-1", "makeup:key-3")
        result = await fair_use_decr(r, "user-1", "makeup:key-3")
        assert result is False

    @pytest.mark.asyncio
    async def test_evalsha_receives_counter_key(self):
        """Counter key passed to decr Lua must be makeup:quota:{user_id}."""
        from app.api.rate_limiters.makeup_fair_use import fair_use_decr

        r = await _make_redis(1)
        await fair_use_decr(r, "user-99", "makeup:key-4")

        call_args = r.evalsha.call_args[0]
        counter_key = call_args[2]  # KEYS[1]
        assert counter_key == "makeup:quota:user-99"

    @pytest.mark.asyncio
    async def test_loads_script_when_sha_not_cached(self):
        from app.api.rate_limiters import makeup_fair_use
        from app.api.rate_limiters.makeup_fair_use import fair_use_decr

        original = makeup_fair_use._decr_sha
        try:
            makeup_fair_use._decr_sha = None
            r = await _make_redis(1)
            await fair_use_decr(r, "user-1", "makeup:key-5")
            r.script_load.assert_awaited_once()
        finally:
            makeup_fair_use._decr_sha = original
