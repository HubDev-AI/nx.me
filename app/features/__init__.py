"""Feature flag registry — single source of truth for app-wide feature toggles.

Flags are backend-controlled (env-var sourced). Mobile fetches them once per
cold start via GET /v1/features and caches in memory.

When a flag is off:
- Backend routes guarded by `require_feature(name)` return 403 FEATURE_DISABLED.
- Mobile hides the associated UI entirely (no greyed-out states).

Day-one registry: AUTH_REQUIRED, SOCIAL_ENABLED, SHARE_ENABLED,
ONBOARDING_ENABLED, ADVISOR_ENABLED.
"""

from __future__ import annotations

from pydantic import BaseModel


class FeatureFlags(BaseModel):
    """Public feature flag payload — wire format for GET /v1/features.

    Field names here are the flag identifiers used on both sides of the wire
    and in `require_feature(name)` calls. When adding a new flag, update this
    model, config defaults, and the mobile `FeatureFlags` interface together.
    """

    auth_required: bool
    social_enabled: bool
    share_enabled: bool
    onboarding_enabled: bool
    advisor_enabled: bool


def get_features() -> FeatureFlags:
    """Build the public FeatureFlags payload from config settings."""
    from app.config import settings

    return FeatureFlags(
        auth_required=settings.FEATURE_AUTH_REQUIRED,
        social_enabled=settings.FEATURE_SOCIAL_ENABLED,
        share_enabled=settings.FEATURE_SHARE_ENABLED,
        onboarding_enabled=settings.FEATURE_ONBOARDING_ENABLED,
        advisor_enabled=settings.ADVISOR_ENABLED,  # uses existing setting
    )


def is_enabled(feature: str) -> bool:
    """Check if a feature is enabled by its public flag name (snake_case).

    Raises ValueError for unknown feature names to catch typos early.
    """
    features = get_features()
    if not hasattr(features, feature):
        raise ValueError(f"Unknown feature flag: {feature!r}")
    return getattr(features, feature)
