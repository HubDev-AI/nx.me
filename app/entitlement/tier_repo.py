"""Tier repository — DB + Redis-cached tier lookups.

A-4: Tiers are DB rows. Business logic reads columns, never conditions on slug.
Redis cache TTL 5 min to avoid per-request DB hits for tier resolution.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

import redis.asyncio as aioredis
from supabase import Client

from app.db.async_helpers import run_sync
from app.entitlement.models import TierRecord

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 300  # 5 minutes
_CACHE_PREFIX = "tier:"


def _row_to_tier(row: dict) -> TierRecord:
    """Convert a Supabase tiers table row to a TierRecord."""
    return TierRecord(
        id=UUID(row["id"]),
        slug=row["slug"],
        display_name=row["display_name"],
        is_default=row["is_default"],
        is_active=row["is_active"],
        generation_type=row["generation_type"],
        generation_limit=row.get("generation_limit"),
        generation_period_seconds=row.get("generation_period_seconds"),
        advisor_nudges_type=row["advisor_nudges_type"],
        advisor_nudges_limit=row.get("advisor_nudges_limit"),
        advisor_nudges_period_seconds=row.get("advisor_nudges_period_seconds"),
        max_concurrent_generations=(
            int(row["max_concurrent_generations"])
            if row.get("max_concurrent_generations") is not None
            else 1
        ),
        identity_similarity_threshold=(
            float(row["identity_similarity_threshold"])
            if row.get("identity_similarity_threshold") is not None
            else 0.75
        ),
        feature_advisor_chat=(
            bool(row["feature_advisor_chat"])
            if row.get("feature_advisor_chat") is not None
            else False
        ),
        feature_visual_comparison=(
            bool(row["feature_visual_comparison"])
            if row.get("feature_visual_comparison") is not None
            else False
        ),
        stripe_price_id=row.get("stripe_price_id"),
        credits_based=row["credits_based"],
    )


def _tier_to_cache(tier: TierRecord) -> str:
    """Serialize TierRecord to JSON for Redis cache."""
    return json.dumps(
        {
            "id": str(tier.id),
            "slug": tier.slug,
            "display_name": tier.display_name,
            "is_default": tier.is_default,
            "is_active": tier.is_active,
            "generation_type": tier.generation_type,
            "generation_limit": tier.generation_limit,
            "generation_period_seconds": tier.generation_period_seconds,
            "advisor_nudges_type": tier.advisor_nudges_type,
            "advisor_nudges_limit": tier.advisor_nudges_limit,
            "advisor_nudges_period_seconds": tier.advisor_nudges_period_seconds,
            "max_concurrent_generations": tier.max_concurrent_generations,
            "identity_similarity_threshold": tier.identity_similarity_threshold,
            "feature_advisor_chat": tier.feature_advisor_chat,
            "feature_visual_comparison": tier.feature_visual_comparison,
            "stripe_price_id": tier.stripe_price_id,
            "credits_based": tier.credits_based,
        }
    )


class TierRepository:
    """Fetch and cache tier rows from the tiers table."""

    def __init__(self, supabase: Client, redis: aioredis.Redis) -> None:
        self._sb = supabase
        self._redis = redis

    async def get(self, tier_id: UUID) -> TierRecord:
        """Fetch a tier by UUID, with Redis caching."""
        cache_key = f"{_CACHE_PREFIX}{tier_id}"

        # Check cache
        cached = await self._redis.get(cache_key)
        if cached:
            try:
                return _row_to_tier(json.loads(cached))
            except (json.JSONDecodeError, TypeError):
                logger.warning("Corrupted tier cache for key %s, deleting", cache_key)
                await self._redis.delete(cache_key)
                # Fall through to DB lookup below

        # Fetch from DB
        # C-3: Wrap sync Supabase call to avoid blocking the event loop
        result = await run_sync(
            lambda: (
                self._sb.table("tiers")
                .select("*")
                .eq("id", str(tier_id))
                .single()
                .execute()
            )
        )
        if not result.data:
            raise ValueError(f"Tier {tier_id} not found")

        tier = _row_to_tier(result.data)

        # Cache
        await self._redis.set(cache_key, _tier_to_cache(tier), ex=_CACHE_TTL_SECONDS)

        return tier

    async def get_default(self) -> TierRecord:
        """Fetch the active default tier."""
        # C-3: Wrap sync Supabase call to avoid blocking the event loop
        result = await run_sync(
            lambda: (
                self._sb.table("tiers")
                .select("*")
                .eq("is_default", True)
                .eq("is_active", True)
                .single()
                .execute()
            )
        )
        if not result.data:
            raise ValueError("No active default tier found")

        return _row_to_tier(result.data)
