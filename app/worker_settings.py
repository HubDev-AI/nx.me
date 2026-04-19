"""Unified ARQ worker settings — handles all queues.

Processes generation jobs (priority lanes), social reactions,
advisor nudges, and reconciliation cron jobs.

Run: arq app.worker_settings.WorkerSettings
"""

from __future__ import annotations

import logging

import redis.asyncio as aioredis
from arq import create_pool, cron
from arq.connections import RedisSettings

from app.config import settings
from app.db.client import get_supabase_service
from app.logging_config import configure_logging
from app.generation.worker import process_generation_job, watchdog_stuck_jobs
from app.api.social import persist_reaction, reconcile_reaction_counts
from app.advisor.nudge_scheduler import (
    generate_nudge,
    schedule_post_analysis_nudge,
    check_nudge_eligibility,
    write_analysis_insight_job,
)
from app.repositories.image_repo import ImageRepository
from app.repositories.orphaned_storage_repo import OrphanedStorageKeyRepository
from app.workers.delete_account_blobs import wipe_deleted_user_blobs
from app.workers.orphan_analysis_reclaim import reclaim_orphaned_analyses
from app.workers.orphan_reclaim import reclaim_orphaned_blobs
from app.workers.retention import run_retention

configure_logging()

logger = logging.getLogger(__name__)


async def startup(ctx: dict) -> None:
    """Worker startup: initialize shared resources."""
    logger.info("Unified worker starting")

    ctx["supabase"] = get_supabase_service()
    ctx["image_repo"] = ImageRepository(ctx["supabase"])
    ctx["orphan_repo"] = OrphanedStorageKeyRepository(ctx["supabase"])
    ctx["redis"] = aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        encoding="utf-8",
    )

    # ARQ dispatch pool for fire-and-forget enqueue_job calls from within
    # worker jobs (e.g. _enqueue_post_glowup_nudge in generation/worker.py,
    # schedule_post_analysis_nudge in advisor/nudge_scheduler.py). ARQ
    # populates ctx["redis"] with its ArqRedis pool by default, but the
    # block above overwrites it with a plain aioredis client configured
    # for string decoding — dropping ArqRedis's enqueue_job method. The
    # dedicated pool here mirrors the FastAPI app.state.arq_pool pattern
    # (app/main.py:152) and restores enqueue_job without forcing the
    # plain redis ops used elsewhere to migrate off string decoding.
    #
    # Fail-fast at CRITICAL on pool creation failure: ARQ does not retry
    # startup, so a Redis flap at boot terminates the worker. The
    # structured log gives ops a signal to alert on — process-exit alone
    # is ambiguous (OOM, OOM-kill, supervisor bug all look identical).
    try:
        ctx["arq_pool"] = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    except Exception:
        logger.critical(
            "Failed to create ARQ dispatch pool during worker startup — worker will abort",
            exc_info=True,
        )
        raise

    if settings.ADAPTER__IMAGE_GENERATION_ADAPTER != "mock":
        from app.generation.identity_checker import preload_arcface

        preload_arcface()

    logger.info("Unified worker ready")


async def shutdown(ctx: dict) -> None:
    """Worker shutdown: cleanup.

    Uses ``try/finally`` so a ``redis.aclose`` failure cannot skip the
    ``arq_pool`` close. On managed Redis with a connection cap, leaking
    the ARQ pool socket on every faulted restart quickly exhausts the
    cap and future worker boots fail with connection-refused.
    """
    try:
        if "redis" in ctx:
            try:
                await ctx["redis"].aclose()
            except Exception:
                logger.warning(
                    "ctx['redis'].aclose() failed during shutdown", exc_info=True
                )
            finally:
                # Drop the handle so a second shutdown call does not
                # double-close the already-closed pool.
                ctx.pop("redis", None)
    finally:
        if "arq_pool" in ctx:
            try:
                await ctx["arq_pool"].aclose()
            except Exception:
                logger.warning(
                    "ctx['arq_pool'].aclose() failed during shutdown", exc_info=True
                )
            finally:
                ctx.pop("arq_pool", None)
    logger.info("Unified worker stopped")


class WorkerSettings:
    """Unified ARQ worker — all queues."""

    functions = [
        process_generation_job,
        persist_reaction,
        schedule_post_analysis_nudge,
        generate_nudge,
        check_nudge_eligibility,
        write_analysis_insight_job,
        reconcile_reaction_counts,
        wipe_deleted_user_blobs,
    ]

    on_startup = startup
    on_shutdown = shutdown

    queue_read_limit = 10

    cron_jobs = [
        cron(watchdog_stuck_jobs, second=0),  # Every minute
        cron(check_nudge_eligibility, hour=6, minute=0),  # Daily at 06:00 UTC
        cron(reconcile_reaction_counts, hour=3, minute=0),  # Nightly at 03:00 UTC
        cron(run_retention, hour=3, minute=30),  # Nightly at 03:30 UTC
        cron(reclaim_orphaned_blobs, hour=3, minute=45),  # Nightly at 03:45 UTC
        cron(reclaim_orphaned_analyses, hour=4, minute=0),  # Nightly at 04:00 UTC
    ]

    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    job_timeout = (
        settings.GENERATION_TIMEOUT_SECONDS + 60
    )  # buffer for upload + identity check
    max_jobs = 10
    keep_result = 3600
