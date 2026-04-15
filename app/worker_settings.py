"""Unified ARQ worker settings — handles all queues.

Processes generation jobs (priority lanes), social reactions,
advisor nudges, and reconciliation cron jobs.

Run: arq app.worker_settings.WorkerSettings
"""

from __future__ import annotations

import logging

import redis.asyncio as aioredis
from arq import cron
from arq.connections import RedisSettings

from app.config import settings
from app.db.client import get_supabase_service
from app.generation.worker import process_generation_job, watchdog_stuck_jobs
from app.api.social import persist_reaction, reconcile_reaction_counts
from app.advisor.nudge_scheduler import (
    generate_nudge,
    schedule_post_analysis_nudge,
    check_nudge_eligibility,
)
from app.workers.orphan_reclaim import reclaim_orphaned_blobs
from app.workers.retention import run_retention

logger = logging.getLogger(__name__)


async def startup(ctx: dict) -> None:
    """Worker startup: initialize shared resources."""
    logger.info("Unified worker starting")

    ctx["supabase"] = get_supabase_service()
    ctx["redis"] = aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        encoding="utf-8",
    )

    if settings.ADAPTER__IMAGE_GENERATION_ADAPTER != "mock":
        from app.generation.identity_checker import preload_arcface

        preload_arcface()

    logger.info("Unified worker ready")


async def shutdown(ctx: dict) -> None:
    """Worker shutdown: cleanup."""
    if "redis" in ctx:
        await ctx["redis"].aclose()
    logger.info("Unified worker stopped")


class WorkerSettings:
    """Unified ARQ worker — all queues."""

    functions = [
        process_generation_job,
        persist_reaction,
        schedule_post_analysis_nudge,
        generate_nudge,
        check_nudge_eligibility,
        reconcile_reaction_counts,
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
    ]

    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    job_timeout = (
        settings.GENERATION_TIMEOUT_SECONDS + 60
    )  # buffer for upload + identity check
    max_jobs = 10
    keep_result = 3600
