"""Health check endpoints.

GET /health   — liveness probe: app is running
GET /readiness — readiness probe: app can serve traffic (Redis + Supabase reachable)
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

import redis.asyncio as aioredis

from app.api.deps import get_redis, get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness probe — always returns 200 if the process is up."""
    return {"status": "ok"}


@router.get("/readiness")
async def readiness(
    r: aioredis.Redis = Depends(get_redis),
    supabase: Client = Depends(get_supabase),
) -> dict:
    """Readiness probe — checks that Redis and Supabase are reachable."""
    checks: dict[str, str] = {}

    # Redis ping
    try:
        await r.ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        logger.error("Redis readiness check failed: %s", exc)
        checks["redis"] = "unavailable"

    # Supabase: lightweight query
    try:
        supabase.table("tiers").select("id").limit(1).execute()
        checks["supabase"] = "ok"
    except Exception as exc:  # noqa: BLE001
        logger.error("Supabase readiness check failed: %s", exc)
        checks["supabase"] = "unavailable"

    if any(v != "ok" for v in checks.values()):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=checks,
        )

    return {"status": "ok", "checks": checks}
