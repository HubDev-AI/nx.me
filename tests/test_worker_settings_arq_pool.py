"""Regression test for the ARQ dispatch pool lifecycle.

Bug #4 (2026-04-19): ``app/worker_settings.py::startup`` did not populate
``ctx["arq_pool"]``. Every in-worker ``arq_pool.enqueue_job(...)`` call
silently hit the None branch — post-glow-up nudges never fired. This
test pins the startup contract so a regression re-surfaces as a failing
test instead of a silent bug.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import worker_settings


@pytest.mark.asyncio
async def test_startup_populates_arq_pool_in_ctx():
    """``startup`` must set ``ctx["arq_pool"]`` to a ready pool object.

    Without this, ``_enqueue_post_glowup_nudge`` and the post-analysis
    scheduler both fall through their no-pool branch on every worker
    invocation.
    """
    fake_pool = MagicMock()
    fake_pool.aclose = AsyncMock()

    ctx: dict = {}

    with (
        patch("app.worker_settings.get_supabase_service") as svc,
        patch("app.worker_settings.ImageRepository") as image_repo_cls,
        patch("app.worker_settings.OrphanedStorageKeyRepository") as orphan_repo_cls,
        patch("app.worker_settings.aioredis.from_url") as redis_from_url,
        patch(
            "app.worker_settings.create_pool",
            new=AsyncMock(return_value=fake_pool),
        ) as create_pool_mock,
        patch("app.worker_settings.settings") as settings_mock,
    ):
        svc.return_value = MagicMock()
        image_repo_cls.return_value = MagicMock()
        orphan_repo_cls.return_value = MagicMock()
        plain_redis = MagicMock()
        plain_redis.aclose = AsyncMock()
        redis_from_url.return_value = plain_redis
        settings_mock.REDIS_URL = "redis://localhost:6379"
        # Skip the arcface preload branch — it imports heavy deps and
        # isn't under test here.
        settings_mock.ADAPTER__IMAGE_GENERATION_ADAPTER = "mock"

        await worker_settings.startup(ctx)

        create_pool_mock.assert_awaited_once()
        assert ctx["arq_pool"] is fake_pool, (
            "startup must populate ctx['arq_pool']; see bug #4 2026-04-19"
        )

        # Shutdown closes both pools — never silently leak a socket.
        await worker_settings.shutdown(ctx)
        fake_pool.aclose.assert_awaited()
        plain_redis.aclose.assert_awaited()
