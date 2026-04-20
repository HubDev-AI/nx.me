"""Feature flag registry — single source of truth for app-wide feature toggles.

Flags are backend-controlled (env-var sourced). Mobile fetches them once per
cold start via GET /v1/features and caches in memory.

When a flag is off:
- Backend routes guarded by `require_feature(name)` return 403 FEATURE_DISABLED.
- Mobile hides the associated UI entirely (no greyed-out states).

Day-one registry: SOCIAL_ENABLED, SHARE_ENABLED, ONBOARDING_ENABLED,
ADVISOR_ENABLED. Auth is not a feature — every route requires JWT except
the public-route allowlist enumerated in tests/test_auth_invariants.py.
"""

from __future__ import annotations

from pydantic import BaseModel


class FeatureFlags(BaseModel):
    """Public feature flag payload — wire format for GET /v1/features.

    Field names here are the flag identifiers used on both sides of the wire
    and in `require_feature(name)` calls. When adding a new flag, update this
    model, config defaults, and the mobile `FeatureFlags` interface together.

    NOTE on ``weekly_free_grant_enabled``: this one is sourced from the
    ``app_kill_switches`` hot-toggle table (via ``runtime_flags``), not a
    deploy-time env var. It is exposed on this endpoint so mobile can
    conditionally render the "+1 free glow-up every week" paywall line
    without scattering `if features.X` checks elsewhere (per the
    feature-gating convention: the capabilities module is the one seam).
    """

    social_enabled: bool
    share_enabled: bool
    onboarding_enabled: bool
    advisor_enabled: bool
    weekly_free_grant_enabled: bool


def get_features() -> FeatureFlags:
    """Build the public FeatureFlags payload from config settings.

    Uses the default for ``weekly_free_grant_enabled`` (True, fail-open —
    matches ``runtime_flags.is_kill_switch_enabled`` semantics for a missing
    row). Callers that want the live kill-switch value should use
    ``get_features_async`` instead.
    """
    from app.config import settings

    return FeatureFlags(
        social_enabled=settings.FEATURE_SOCIAL_ENABLED,
        share_enabled=settings.FEATURE_SHARE_ENABLED,
        onboarding_enabled=settings.FEATURE_ONBOARDING_ENABLED,
        advisor_enabled=settings.ADVISOR_ENABLED,  # uses existing setting
        weekly_free_grant_enabled=True,
    )


async def get_features_async(supabase) -> FeatureFlags:
    """Build FeatureFlags with the live ``weekly_free_grant`` kill-switch
    value from ``app_kill_switches``. Used by the HTTP handler.

    Fail-open on DB errors per ``runtime_flags.is_kill_switch_enabled``.
    """
    from app.runtime_flags import (
        KILL_SWITCH_WEEKLY_FREE_GRANT,
        is_kill_switch_enabled,
    )

    flags = get_features()
    flags_dict = flags.model_dump()
    flags_dict["weekly_free_grant_enabled"] = await is_kill_switch_enabled(
        supabase, KILL_SWITCH_WEEKLY_FREE_GRANT
    )
    return FeatureFlags(**flags_dict)


def is_enabled(feature: str) -> bool:
    """Check if a feature is enabled by its public flag name (snake_case).

    Raises ValueError for unknown feature names to catch typos early.
    """
    features = get_features()
    if not hasattr(features, feature):
        raise ValueError(f"Unknown feature flag: {feature!r}")
    return getattr(features, feature)
