"""Tests for the concurrent-generation counter reclaim paths.

Covers:

- ``_release_concurrent_counter`` calls the cleanup script with the right
  key + TTL on first use, and re-uses the cached SHA afterwards.
- It never re-raises, even if Redis is down.
- ``watchdog_stuck_jobs`` releases the counter for every stuck job's user
  AFTER it calls ``_fail_job``.
- Watchdog gracefully skips the release when there's no Redis in ctx (defensive).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.generation import worker as worker_mod


@pytest.fixture(autouse=True)
def _reset_concurrent_sha_cache():
    """Module-level SHA cache would leak across tests and make ordering
    load-bearing. Reset before AND after every test in this module."""
    worker_mod._concurrent_cleanup_sha_cache = None
    yield
    worker_mod._concurrent_cleanup_sha_cache = None


@pytest.mark.asyncio
class TestReleaseConcurrentCounter:
    async def test_loads_script_on_first_use_and_caches(self):
        redis = MagicMock()
        redis.script_load = AsyncMock(return_value="sha-xyz")
        redis.evalsha = AsyncMock(return_value=0)

        await worker_mod._release_concurrent_counter(redis, "user-1")
        # First call: script_load happened.
        redis.script_load.assert_awaited_once()
        redis.evalsha.assert_awaited_once()
        args = redis.evalsha.await_args.args
        assert args[0] == "sha-xyz"
        assert args[1] == 1
        assert args[2] == "concurrent:user-1"

        # Second call: uses cached SHA, no second script_load.
        await worker_mod._release_concurrent_counter(redis, "user-2")
        assert redis.script_load.await_count == 1
        assert redis.evalsha.await_count == 2

    async def test_never_re_raises(self):
        redis = MagicMock()
        redis.script_load = AsyncMock(side_effect=RuntimeError("redis down"))

        # Must NOT raise — the helper is called from exception handlers and
        # from cron paths that must keep processing remaining items.
        await worker_mod._release_concurrent_counter(redis, "user-1")


@pytest.mark.asyncio
class TestWatchdogReclaim:
    async def test_watchdog_releases_counter_for_each_stuck_job(self):
        # Pre-seed the SHA cache so evalsha doesn't need a preceding script_load.
        worker_mod._concurrent_cleanup_sha_cache = "pre-cached"

        redis = MagicMock()
        redis.evalsha = AsyncMock(return_value=0)

        supabase = MagicMock()
        ctx = {"supabase": supabase, "redis": redis}

        fake_jobs = [
            {"id": "job-1", "user_id": "user-a"},
            {"id": "job-2", "user_id": "user-b"},
        ]

        job_repo_mock = MagicMock()
        job_repo_mock.get_stuck_jobs.return_value = fake_jobs

        with patch.object(
            worker_mod, "JobRepository", lambda _sb: job_repo_mock
        ), patch.object(worker_mod, "_fail_job", new=AsyncMock()) as fail_job_mock:
            await worker_mod.watchdog_stuck_jobs(ctx)

        # Two jobs stuck → two _fail_job calls + two counter releases.
        assert fail_job_mock.await_count == 2
        assert redis.evalsha.await_count == 2
        released_keys = [
            call.args[2] for call in redis.evalsha.await_args_list
        ]
        assert "concurrent:user-a" in released_keys
        assert "concurrent:user-b" in released_keys

    async def test_watchdog_skips_release_without_redis(self):
        """Defensive: no redis in ctx must not crash the cron."""
        supabase = MagicMock()
        ctx = {"supabase": supabase}  # no redis

        job_repo_mock = MagicMock()
        job_repo_mock.get_stuck_jobs.return_value = [
            {"id": "job-1", "user_id": "user-a"}
        ]

        with patch.object(
            worker_mod, "JobRepository", lambda _sb: job_repo_mock
        ), patch.object(worker_mod, "_fail_job", new=AsyncMock()) as fail_job_mock:
            await worker_mod.watchdog_stuck_jobs(ctx)

        # _fail_job still runs — reclaim silently skipped.
        fail_job_mock.assert_awaited_once()

    async def test_watchdog_skips_release_when_user_id_missing(self):
        redis = MagicMock()
        redis.evalsha = AsyncMock(return_value=0)
        ctx = {"supabase": MagicMock(), "redis": redis}

        job_repo_mock = MagicMock()
        job_repo_mock.get_stuck_jobs.return_value = [
            {"id": "job-1"}  # no user_id
        ]

        with patch.object(
            worker_mod, "JobRepository", lambda _sb: job_repo_mock
        ), patch.object(worker_mod, "_fail_job", new=AsyncMock()):
            await worker_mod.watchdog_stuck_jobs(ctx)

        # Release skipped because user_id missing — no evalsha call.
        redis.evalsha.assert_not_called()
