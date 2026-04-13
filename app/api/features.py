"""Feature flags API.

GET /v1/features — return the current feature flag registry. Public endpoint
(no auth required) so mobile can fetch it on cold start before the user logs
in. Flags are read from server config on every request — no caching on the
server side, mobile caches in-memory for the session.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.features import FeatureFlags, get_features

router = APIRouter(tags=["features"])


@router.get("/features", response_model=FeatureFlags)
async def get_feature_flags() -> FeatureFlags:
    """Return the current feature flag registry."""
    return get_features()
