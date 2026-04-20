"""Feature flags API.

GET /v1/features — return the current feature flag registry. Public endpoint
(no auth required) so mobile can fetch it on cold start before the user logs
in. Flags are read from server config on every request — no caching on the
server side, mobile caches in-memory for the session.

``weekly_free_grant_enabled`` is sourced from the ``app_kill_switches`` table
via ``runtime_flags.is_kill_switch_enabled`` so operator flips on the weekly
cron become visible to mobile copy on the next cold start (no redeploy).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from supabase import Client

from app.api.deps import get_supabase
from app.features import FeatureFlags, get_features_async

router = APIRouter(tags=["features"])


@router.get("/features", response_model=FeatureFlags)
async def get_feature_flags(
    supabase: Client = Depends(get_supabase),
) -> FeatureFlags:
    """Return the current feature flag registry."""
    return await get_features_async(supabase)
