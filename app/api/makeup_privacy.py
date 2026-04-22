"""Makeup data privacy endpoint.

DELETE /v1/users/me/makeup-data — right-to-erasure for makeup biometrics.

Nullifies mst_bin, undertone, region_anchors on all makeup_analyses rows
for the caller. Consent and ranking metadata are retained per privacy policy.
Flushes per-user makeup Redis keys (rate-limit counters).
"""

from __future__ import annotations

import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import get_current_user, get_redis, require_app_feature
from app.api.middleware.auth import UserClaims
from app.db.async_helpers import run_sync
from app.repositories.makeup_analysis_repo import MakeupAnalysisRepository

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["makeup"],
    dependencies=[Depends(require_app_feature("makeup_enabled"))],
)


@router.delete(
    "/users/me/makeup-data",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_makeup_data(
    request: Request,
    claims: UserClaims = Depends(get_current_user),
    redis_client: aioredis.Redis = Depends(get_redis),
) -> Response:
    """Wipe biometric fields from all makeup_analyses rows for the caller.

    Idempotent — safe to call multiple times.
    Next /generate call will re-run analysis and re-record consent.

    Errors: none beyond auth (401).
    """
    user_id: str = claims["sub"]

    supabase = request.app.state.supabase
    analysis_repo = MakeupAnalysisRepository(supabase)
    await run_sync(analysis_repo.nullify_biometric_fields, user_id)

    try:
        await redis_client.delete(
            f"makeup:quota:{user_id}",
            f"makeup:analyze_rate:{user_id}",
        )
    except Exception:
        logger.warning("delete_makeup_data: Redis cleanup failed for user=%s", user_id)

    logger.info("delete_makeup_data: biometrics nullified for user=%s", user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
