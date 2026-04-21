"""Unit tests for check_makeup_analyze_rate_limit.

Uses MockRedis (pipeline/incr/expire, no EVALSHA) — mirrors the
check_delete_glowup_rate_limit tests in style and coverage.

Constants: 10 requests per 60-second window, key = makeup_analyze_rate:{user_id}.
"""

from __future__ import annotations

import pytest

from tests.conftest import MockRedis


class TestCheckMakeupAnalyzeRateLimit:
    @pytest.mark.asyncio
    async def test_allows_first_request(self):
        from app.services.rate_limiter import check_makeup_analyze_rate_limit

        r = MockRedis()
        allowed, ttl = await check_makeup_analyze_rate_limit("user-1", r)
        assert allowed is True
        assert ttl == 0

    @pytest.mark.asyncio
    async def test_allows_up_to_limit(self):
        from app.services.rate_limiter import check_makeup_analyze_rate_limit

        r = MockRedis()
        for i in range(10):
            allowed, _ = await check_makeup_analyze_rate_limit("user-1", r)
            assert allowed is True, f"request {i + 1} should be allowed"

    @pytest.mark.asyncio
    async def test_denies_eleventh_request(self):
        from app.services.rate_limiter import check_makeup_analyze_rate_limit

        r = MockRedis()
        for _ in range(10):
            await check_makeup_analyze_rate_limit("user-1", r)

        allowed, _ = await check_makeup_analyze_rate_limit("user-1", r)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_retry_after_at_least_one_when_denied(self):
        from app.services.rate_limiter import check_makeup_analyze_rate_limit

        r = MockRedis()
        for _ in range(11):
            await check_makeup_analyze_rate_limit("user-1", r)

        _, ttl = await check_makeup_analyze_rate_limit("user-1", r)
        assert ttl >= 1

    @pytest.mark.asyncio
    async def test_different_users_are_independent(self):
        from app.services.rate_limiter import check_makeup_analyze_rate_limit

        r = MockRedis()
        for _ in range(11):
            await check_makeup_analyze_rate_limit("user-1", r)

        allowed, _ = await check_makeup_analyze_rate_limit("user-2", r)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_key_namespaced_per_user(self):
        from app.services.rate_limiter import check_makeup_analyze_rate_limit

        r = MockRedis()
        await check_makeup_analyze_rate_limit("user-A", r)

        assert "makeup_analyze_rate:user-A" in r._store
        assert any("user-B" in k for k in r._store) is False

    @pytest.mark.asyncio
    async def test_returns_tuple_bool_int(self):
        from app.services.rate_limiter import check_makeup_analyze_rate_limit

        r = MockRedis()
        result = await check_makeup_analyze_rate_limit("user-x", r)
        allowed, ttl = result
        assert isinstance(allowed, bool)
        assert isinstance(ttl, int)

    @pytest.mark.asyncio
    async def test_ttl_zero_when_allowed(self):
        from app.services.rate_limiter import check_makeup_analyze_rate_limit

        r = MockRedis()
        _, ttl = await check_makeup_analyze_rate_limit("user-1", r)
        assert ttl == 0
