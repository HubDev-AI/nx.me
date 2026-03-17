"""Cost tracking and circuit breaker for generation pipeline.

Rolling 24h cost average, per-user daily cap, queue depth limit,
emergency stop flag, fal.ai health probe.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

# Redis key patterns
_COST_BUCKET_PREFIX = "gen:cost:24h:"
_EMERGENCY_STOP_KEY = "gen:emergency_stop"
_USER_DAILY_KEY = "gen:user_daily:{user_id}:{date}"
_QUEUE_DEPTH_KEY = "gen:queue_depth"


class CostTracker:
    """Tracks generation costs and enforces circuit breakers."""

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    # ------------------------------------------------------------------
    # Record cost
    # ------------------------------------------------------------------

    async def record_cost(self, cost_usd: float) -> None:
        """Record a generation cost in the rolling 24h window."""
        hour_bucket = datetime.now(tz=timezone.utc).strftime("%Y%m%d%H")
        key = f"{_COST_BUCKET_PREFIX}{hour_bucket}"

        pipe = self._redis.pipeline()
        pipe.incrbyfloat(key, cost_usd)
        pipe.expire(key, 90000)  # 25 hours TTL (24h + 1h buffer)
        await pipe.execute()

    # ------------------------------------------------------------------
    # Rolling 24h average cost per generation
    # ------------------------------------------------------------------

    async def get_rolling_24h_avg_cost(self) -> float:
        """Compute rolling 24h average cost per generation."""
        now = datetime.now(tz=timezone.utc)
        total_cost = 0.0
        bucket_count = 0

        for i in range(24):
            hour = now.hour - i
            if hour < 0:
                hour += 24
            bucket = now.replace(hour=hour % 24).strftime("%Y%m%d%H")
            key = f"{_COST_BUCKET_PREFIX}{bucket}"
            val = await self._redis.get(key)
            if val:
                total_cost += float(val)
                bucket_count += 1

        if bucket_count == 0:
            return 0.0

        # Rough estimate: assume ~10 generations per bucket hour
        return total_cost / max(bucket_count * 10, 1)

    # ------------------------------------------------------------------
    # Circuit breaker checks
    # ------------------------------------------------------------------

    async def should_throttle_trial(self) -> bool:
        """Check if TRIAL lane should be throttled due to cost."""
        avg = await self.get_rolling_24h_avg_cost()

        if avg > settings.IMAGE_GEN_COST_CEILING_USD:
            logger.warning("Cost ceiling exceeded: avg=$%.4f > ceiling=$%.4f — throttling TRIAL",
                           avg, settings.IMAGE_GEN_COST_CEILING_USD)
            return True

        if avg > settings.CREDIT_COST_ALERT_USD:
            logger.info("Cost alert: avg=$%.4f > alert=$%.4f", avg, settings.CREDIT_COST_ALERT_USD)

        return False

    async def is_emergency_stopped(self) -> bool:
        """Check if emergency stop flag is set."""
        val = await self._redis.get(_EMERGENCY_STOP_KEY)
        return val == "1"

    async def check_queue_depth(self, max_depth: int = 15000) -> bool:
        """Return True if queue is within acceptable depth."""
        # Check all three lanes
        total = 0
        for lane in ["generation:premium", "generation:credit", "generation:trial"]:
            depth = await self._redis.llen(f"arq:queue:{lane}")
            total += depth

        if total > max_depth:
            logger.warning("Queue depth %d exceeds max %d", total, max_depth)
            return False
        return True

    # ------------------------------------------------------------------
    # Per-user daily cap
    # ------------------------------------------------------------------

    async def check_user_daily_cap(self, user_id: str, max_per_day: int = 50) -> bool:
        """Return True if user is within daily generation cap."""
        date_str = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
        key = _USER_DAILY_KEY.format(user_id=user_id, date=date_str)

        count = int(await self._redis.get(key) or 0)
        return count < max_per_day

    async def increment_user_daily(self, user_id: str) -> None:
        """Increment user's daily generation count."""
        date_str = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
        key = _USER_DAILY_KEY.format(user_id=user_id, date=date_str)

        pipe = self._redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 86400)
        await pipe.execute()
