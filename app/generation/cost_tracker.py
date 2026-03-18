"""Cost tracking and circuit breaker for generation pipeline.

Rolling 24h cost average, per-user daily cap, queue depth limit,
emergency stop flag, fal.ai health probe.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

# Circuit breaker constants — sourced from settings (L-11).
# These module-level aliases avoid repeated attribute access in hot paths.
# The authoritative values live in app.config.Settings.
_COST_BUCKET_TTL_SECONDS = settings.COST_BUCKET_TTL_SECONDS
_CB_FAILURE_THRESHOLD = settings.CB_FAILURE_THRESHOLD
_CB_FAILURE_WINDOW_SECONDS = settings.CB_FAILURE_WINDOW_SECONDS
_CB_COOLDOWN_SECONDS = settings.CB_COOLDOWN_SECONDS

# Redis key patterns
_COST_BUCKET_PREFIX = "gen:cost:24h:"
_COUNT_BUCKET_PREFIX = "gen:count:24h:"
_EMERGENCY_STOP_KEY = "gen:emergency_stop"
_USER_DAILY_KEY = "gen:user_daily:{user_id}:{date}"
_QUEUE_DEPTH_KEY = "gen:queue_depth"

# Circuit breaker state keys
_CB_STATE_KEY = "gen:cb:state"      # "closed" | "open" | "half_open"
_CB_FAILURES_KEY = "gen:cb:failures"  # sorted set of failure timestamps
_CB_OPEN_AT_KEY = "gen:cb:open_at"  # float timestamp when circuit was opened


_CB_TRANSITION_SCRIPT = """
local open_at = redis.call('GET', KEYS[1])
if not open_at then return 0 end
local cooldown = tonumber(ARGV[1])
local now = tonumber(ARGV[2])
if (now - tonumber(open_at)) >= cooldown then
    redis.call('DEL', KEYS[1])
    return 1
end
return 0
"""


class CostTracker:
    """Tracks generation costs and enforces circuit breakers."""

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client
        self._cb_transition_sha: str | None = None

    # ------------------------------------------------------------------
    # Record cost
    # ------------------------------------------------------------------

    async def record_cost(self, cost_usd: float) -> None:
        """Record a generation cost and generation count in the rolling 24h window."""
        hour_bucket = datetime.now(tz=timezone.utc).strftime("%Y%m%d%H")
        cost_key = f"{_COST_BUCKET_PREFIX}{hour_bucket}"
        count_key = f"{_COUNT_BUCKET_PREFIX}{hour_bucket}"

        pipe = self._redis.pipeline()
        pipe.incrbyfloat(cost_key, cost_usd)
        pipe.expire(cost_key, _COST_BUCKET_TTL_SECONDS)
        pipe.incr(count_key)
        pipe.expire(count_key, _COST_BUCKET_TTL_SECONDS)
        results = await pipe.execute()
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("Redis pipeline command %d failed in record_cost: %s", i, result)

    # ------------------------------------------------------------------
    # Rolling 24h average cost per generation
    # ------------------------------------------------------------------

    async def get_rolling_24h_avg_cost(self) -> float:
        """Compute rolling 24h average cost per generation."""
        now = datetime.now(tz=timezone.utc)
        total_cost = 0.0
        total_count = 0

        for i in range(24):
            bucket_time = now - timedelta(hours=i)
            bucket = bucket_time.strftime("%Y%m%d%H")
            cost_val = await self._redis.get(f"{_COST_BUCKET_PREFIX}{bucket}")
            count_val = await self._redis.get(f"{_COUNT_BUCKET_PREFIX}{bucket}")
            if cost_val:
                total_cost += float(cost_val)
            if count_val:
                total_count += int(count_val)

        if total_count == 0:
            return 0.0

        return total_cost / total_count

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

    async def check_queue_depth(self, max_depth: int) -> bool:
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
        results = await pipe.execute()
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("Redis pipeline command %d failed in increment_user_daily: %s", i, result)

    # ------------------------------------------------------------------
    # Circuit breaker (fal.ai failures) — sliding window + half-open state
    #
    # State machine:
    #   CLOSED    — normal operation; failures tracked in sliding window.
    #               Transitions to OPEN when failure count >= threshold.
    #   OPEN      — all requests rejected.
    #               Transitions to HALF_OPEN after cooldown period elapses.
    #   HALF_OPEN — one probe request allowed through.
    #               Success → CLOSED; Failure → OPEN.
    # ------------------------------------------------------------------

    async def record_failure(self) -> None:
        """Record a fal.ai failure and open the circuit if threshold is reached."""
        now = time.time()
        window_start = now - _CB_FAILURE_WINDOW_SECONDS

        pipe = self._redis.pipeline()
        # Add this failure timestamp to the sorted set (score = member = timestamp)
        pipe.zadd(_CB_FAILURES_KEY, {str(now): now})
        # Trim entries outside the sliding window
        pipe.zremrangebyscore(_CB_FAILURES_KEY, 0, window_start)
        results = await pipe.execute()
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("Redis pipeline command %d failed in record_failure: %s", i, result)

        failure_count = await self._redis.zcard(_CB_FAILURES_KEY)

        current_state = (await self._redis.get(_CB_STATE_KEY) or b"closed")
        if isinstance(current_state, bytes):
            current_state = current_state.decode()

        if failure_count >= _CB_FAILURE_THRESHOLD and current_state != "open":
            await self._redis.set(_CB_STATE_KEY, "open")
            await self._redis.set(_CB_OPEN_AT_KEY, str(now))
            logger.critical(
                "Circuit breaker OPEN: %d fal.ai failures in last %ds",
                failure_count,
                _CB_FAILURE_WINDOW_SECONDS,
            )
        elif current_state == "half_open":
            # Probe failed — return to OPEN
            await self._redis.set(_CB_STATE_KEY, "open")
            await self._redis.set(_CB_OPEN_AT_KEY, str(now))
            logger.warning("Circuit breaker probe FAILED — returning to OPEN")

    async def record_success(self) -> None:
        """Record a fal.ai success.

        In HALF_OPEN: single success closes the circuit and clears failure history.
        In CLOSED: do not wipe failure history (prevents flap on a single success).
        """
        current_state = (await self._redis.get(_CB_STATE_KEY) or b"closed")
        if isinstance(current_state, bytes):
            current_state = current_state.decode()

        if current_state == "half_open":
            # Probe succeeded — close the circuit and clear failure history
            pipe = self._redis.pipeline()
            pipe.set(_CB_STATE_KEY, "closed")
            pipe.delete(_CB_FAILURES_KEY)
            pipe.delete(_CB_OPEN_AT_KEY)
            results = await pipe.execute()
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error("Redis pipeline command %d failed in record_success: %s", i, result)
            logger.info("Circuit breaker CLOSED: probe succeeded")
        # In CLOSED state intentionally do nothing — failure history is preserved
        # so a single success cannot mask a genuinely flapping provider.

    async def is_circuit_open(self) -> bool:
        """Check if the circuit breaker is blocking requests.

        Returns True  → reject the request (circuit OPEN and still cooling down).
        Returns False → allow the request (CLOSED or HALF_OPEN probe slot).

        Side effect: transitions OPEN → HALF_OPEN when cooldown has elapsed,
        using an atomic Lua script to prevent multiple concurrent probes (M-9).
        """
        current_state = (await self._redis.get(_CB_STATE_KEY) or b"closed")
        if isinstance(current_state, bytes):
            current_state = current_state.decode()

        if current_state == "closed":
            return False

        if current_state == "open":
            # Atomic check-and-transition: delete open_at only if cooldown elapsed.
            # This prevents two concurrent callers from both seeing "cooldown elapsed"
            # and both transitioning to half_open (letting two probes through).
            if self._cb_transition_sha is None:
                self._cb_transition_sha = await self._redis.script_load(
                    _CB_TRANSITION_SCRIPT
                )

            transitioned = await self._redis.evalsha(
                self._cb_transition_sha,
                1,
                _CB_OPEN_AT_KEY,
                str(_CB_COOLDOWN_SECONDS),
                str(time.time()),
            )
            if transitioned:
                await self._redis.set(_CB_STATE_KEY, "half_open")
                logger.info(
                    "Circuit breaker → HALF_OPEN: allowing probe after %ds cooldown",
                    _CB_COOLDOWN_SECONDS,
                )
                return False  # Let this request through as the probe
            return True  # Still cooling down

        # half_open — probe slot is open
        return False
