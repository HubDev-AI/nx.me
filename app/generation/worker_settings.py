"""ARQ worker settings — priority queue configuration.

Three lanes processed in priority order:
  1. generation:premium (highest)
  2. generation:credit
  3. generation:trial (lowest)

Includes stuck-job watchdog as cron job and ArcFace preload on startup.
"""
from __future__ import annotations

import logging

import redis.asyncio as aioredis
from arq import cron

from app.config import settings
from app.db.client import get_supabase_service
from app.generation.models import QUEUE_LANES
from app.generation.worker import process_generation_job, watchdog_stuck_jobs

logger = logging.getLogger(__name__)


async def startup(ctx: dict) -> None:
    """Worker startup: initialize shared resources."""
    logger.info("Generation worker starting")

    ctx["supabase"] = get_supabase_service()
    ctx["redis"] = aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        encoding="utf-8",
    )

    # Pre-load ArcFace model (like MediaPipe preload pattern)
    if settings.ADAPTER__IMAGE_GENERATION_ADAPTER != "mock":
        from app.generation.identity_checker import preload_arcface
        preload_arcface()

    logger.info("Generation worker ready")


async def shutdown(ctx: dict) -> None:
    """Worker shutdown: cleanup."""
    if "redis" in ctx:
        await ctx["redis"].aclose()
    logger.info("Generation worker stopped")


class WorkerSettings:
    """ARQ worker configuration."""

    functions = [process_generation_job]
    on_startup = startup
    on_shutdown = shutdown

    # Priority queue ordering: premium → credit → trial
    queue_read_limit = 10
    queues = QUEUE_LANES

    # Cron jobs
    cron_jobs = [
        cron(watchdog_stuck_jobs, second=0),  # Every minute
    ]

    # Connection
    redis_settings = None  # Set from REDIS_URL at runtime

    # Timeouts
    job_timeout = settings.GENERATION_TIMEOUT_SECONDS
    max_jobs = 10
    keep_result = 3600  # 1 hour
