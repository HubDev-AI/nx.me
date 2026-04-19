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
from arq.connections import RedisSettings

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

        # Pin the DSN argument — a bare ``assert_awaited_once()`` would
        # still pass if a future edit passed None or the wrong DSN into
        # ``create_pool``, re-opening the bug this test exists to block.
        create_pool_mock.assert_awaited_once_with(
            RedisSettings.from_dsn("redis://localhost:6379")
        )
        assert ctx["arq_pool"] is fake_pool, (
            "startup must populate ctx['arq_pool']; see bug #4 2026-04-19"
        )

        # Shutdown closes both pools — never silently leak a socket.
        await worker_settings.shutdown(ctx)
        fake_pool.aclose.assert_awaited()
        plain_redis.aclose.assert_awaited()


@pytest.mark.asyncio
async def test_startup_raises_on_create_pool_failure(caplog):
    """``create_pool`` failure must propagate with a CRITICAL log.

    ARQ does not retry startup. Silent swallowing would leave the worker
    running with ``ctx["arq_pool"]`` missing — the original bug #4 shape.
    A CRITICAL log gives ops a single alert-able signal distinct from
    generic process-exit noise (OOM, supervisor bugs, etc.).
    """
    import logging

    ctx: dict = {}

    with (
        patch("app.worker_settings.get_supabase_service") as svc,
        patch("app.worker_settings.ImageRepository") as image_repo_cls,
        patch("app.worker_settings.OrphanedStorageKeyRepository") as orphan_repo_cls,
        patch("app.worker_settings.aioredis.from_url") as redis_from_url,
        patch(
            "app.worker_settings.create_pool",
            new=AsyncMock(side_effect=ConnectionError("redis unreachable")),
        ),
        patch("app.worker_settings.settings") as settings_mock,
    ):
        svc.return_value = MagicMock()
        image_repo_cls.return_value = MagicMock()
        orphan_repo_cls.return_value = MagicMock()
        redis_from_url.return_value = MagicMock()
        settings_mock.REDIS_URL = "redis://localhost:6379"
        settings_mock.ADAPTER__IMAGE_GENERATION_ADAPTER = "mock"

        caplog.set_level(logging.CRITICAL)
        with pytest.raises(ConnectionError, match="redis unreachable"):
            await worker_settings.startup(ctx)

        assert any(
            "Failed to create ARQ dispatch pool" in r.message
            and r.levelname == "CRITICAL"
            for r in caplog.records
        ), "startup must emit a CRITICAL log before re-raising"


@pytest.mark.asyncio
async def test_shutdown_closes_arq_pool_even_if_redis_close_raises():
    """``try/finally`` discipline: a failed ``redis.aclose()`` must not
    skip ``arq_pool.aclose()``. On managed Redis with a connection cap,
    leaking the ARQ pool socket on every faulted restart exhausts the
    cap and future worker boots fail with connection-refused.
    """
    bad_redis = MagicMock()
    bad_redis.aclose = AsyncMock(side_effect=RuntimeError("already closed"))
    arq_pool = MagicMock()
    arq_pool.aclose = AsyncMock()

    ctx: dict = {"redis": bad_redis, "arq_pool": arq_pool}

    # shutdown must not raise; the arq_pool close must still run.
    await worker_settings.shutdown(ctx)

    bad_redis.aclose.assert_awaited()
    arq_pool.aclose.assert_awaited()
    # Both handles dropped so a second shutdown call is a no-op.
    assert "redis" not in ctx
    assert "arq_pool" not in ctx
