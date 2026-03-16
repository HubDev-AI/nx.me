"""Tier seed definitions — used ONLY by the migration runner and admin seed scripts.

NEVER import this module at runtime (from app startup, services, or API handlers).
Runtime tier data comes from the database, not from this file.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.services.limits import LimitType


@dataclass(frozen=True)
class TierSeed:
    id: str
    slug: str
    display_name: str
    is_default: bool
    is_active: bool
    generation_type: str          # LimitType value
    generation_limit: Optional[int]
    generation_period_seconds: Optional[int]
    advisor_nudges_type: str      # LimitType value
    advisor_nudges_limit: Optional[int]
    advisor_nudges_period_seconds: Optional[int]
    max_concurrent_generations: int
    identity_similarity_threshold: float
    feature_advisor_chat: bool
    feature_visual_comparison: bool
    credits_based: bool


SEED_TIERS: list[TierSeed] = [
    TierSeed(
        id="a0000000-0000-0000-0000-000000000001",
        slug="free",
        display_name="Free",
        is_default=True,
        is_active=True,
        generation_type=LimitType.DAILY,
        generation_limit=1,
        generation_period_seconds=86400,
        advisor_nudges_type=LimitType.WEEKLY,
        advisor_nudges_limit=3,
        advisor_nudges_period_seconds=604800,
        max_concurrent_generations=1,
        identity_similarity_threshold=0.800,
        feature_advisor_chat=False,
        feature_visual_comparison=False,
        credits_based=False,
    ),
    TierSeed(
        id="a0000000-0000-0000-0000-000000000002",
        slug="credits",
        display_name="Credits",
        is_default=False,
        is_active=True,
        generation_type=LimitType.CREDITS,
        generation_limit=None,
        generation_period_seconds=None,
        advisor_nudges_type=LimitType.WEEKLY,
        advisor_nudges_limit=10,
        advisor_nudges_period_seconds=604800,
        max_concurrent_generations=2,
        identity_similarity_threshold=0.750,
        feature_advisor_chat=False,
        feature_visual_comparison=True,
        credits_based=True,
    ),
    TierSeed(
        id="a0000000-0000-0000-0000-000000000003",
        slug="premium",
        display_name="Premium",
        is_default=False,
        is_active=True,
        generation_type=LimitType.MONTHLY,
        generation_limit=100,
        generation_period_seconds=2592000,
        advisor_nudges_type=LimitType.UNLIMITED,
        advisor_nudges_limit=None,
        advisor_nudges_period_seconds=None,
        max_concurrent_generations=3,
        identity_similarity_threshold=0.700,
        feature_advisor_chat=True,
        feature_visual_comparison=True,
        credits_based=False,
    ),
]
