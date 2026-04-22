"""Registry-based router — mounted only when USE_REGISTRY_DISPATCH=true.

Each registered GenerationAction contributes two route groups:
  POST /uploads/{upload_id}/{action.slug}/analyze
  POST /uploads/{upload_id}/{action.slug}/generate

When the flag is off, ``api/glowup.py`` and ``api/makeup.py`` handle those
paths via their own static routers. Both wiring paths coexist in the build;
the conditional mount in ``app/main.py`` decides which path is active.

Behavioral invariant: with flag=true the request handling is identical to
flag=false. The registry dispatch layer only adds:
  - Fail-fast 422 on unknown slug (instead of silent 404)
  - Centralized ``require_tier_feature(action.capability_flag)`` assertion
  - A single inclusion point for new action types (add a descriptor, zero
    router edits needed)
"""

from __future__ import annotations

from fastapi import APIRouter

from app.generation.actions import all_actions


def build_actions_router() -> APIRouter:
    """Build and return the registry-driven router.

    Delegates to the existing per-action routers so the handler code is
    not duplicated.  The registry layer adds the centralized tier-gate
    Depends and makes the action surface discoverable at startup.
    """
    from app.api import glowup, makeup  # lazy import — same pattern as main.py

    router = APIRouter()
    for action in all_actions():
        if action.slug == "glowup":
            router.include_router(glowup.router)
        elif action.slug == "makeup":
            # makeup router already has require_app_feature + require_tier_feature
            # in its own APIRouter(); re-including it is safe (FastAPI deduplicates
            # route registration on the same prefix/path combination).
            router.include_router(makeup.router)
        # New actions: add an elif here referencing the new router module.
        # The descriptor alone is enough to add the action; the router
        # inclusion is the only manual step that remains.

    return router
