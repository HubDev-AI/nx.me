"""Entitlement service — single authoritative module for credit/subscription/tier state.

AC-D1: All entitlement checks route through this service.
No handler reads credit_ledger or subscriptions directly.

Interface Contract (Story 4-1):
  EntitlementService.get_entitlement(user_id) -> EntitlementState
  EntitlementService.can_generate(user_id) -> CanGenerateResult
  EntitlementService.check(user_id, action) -> EntitlementResult
  EntitlementService.has_feature(user_id, feature) -> bool
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

import redis.asyncio as aioredis
from supabase import Client

from app.entitlement.ledger import CreditLedger
from app.entitlement.models import (
    CanGenerateResult,
    EntitlementResult,
    EntitlementState,
    TIER_CONCURRENT_LIMIT,
    TIER_LIMIT_CREDITS,
    TIER_LIMIT_DAILY,
    TIER_LIMIT_MONTHLY,
    TIER_LIMIT_TOTAL,
    TIER_LIMIT_WEEKLY,
    TierRecord,
)
from app.entitlement.tier_repo import TierRepository
from app.entitlement.usage_repo import UsageRepository
from app.services.limits import LimitType

logger = logging.getLogger(__name__)

# Map LimitType → error code
_LIMIT_CODE: dict[LimitType, str] = {
    LimitType.DAILY: TIER_LIMIT_DAILY,
    LimitType.WEEKLY: TIER_LIMIT_WEEKLY,
    LimitType.MONTHLY: TIER_LIMIT_MONTHLY,
    LimitType.TOTAL: TIER_LIMIT_TOTAL,
    LimitType.PERIOD: TIER_LIMIT_DAILY,  # custom period uses daily code
}

# Map LimitType → timedelta factory
_LIMIT_WINDOW: dict[LimitType, timedelta | None] = {
    LimitType.DAILY: timedelta(days=1),
    LimitType.WEEKLY: timedelta(weeks=1),
    LimitType.MONTHLY: timedelta(days=30),
    LimitType.TOTAL: None,  # lifetime — no window
}


class EntitlementService:
    """Single authoritative entitlement module."""

    def __init__(
        self,
        supabase: Client,
        redis_client: aioredis.Redis,
    ) -> None:
        self._sb = supabase
        self._redis = redis_client
        self._tier_repo = TierRepository(supabase, redis_client)
        self._ledger = CreditLedger(supabase)
        self._usage = UsageRepository(supabase)

    # ------------------------------------------------------------------
    # Core: get_entitlement (AC-1)
    # ------------------------------------------------------------------

    async def get_entitlement(self, user_id: UUID) -> EntitlementState:
        """Recompute entitlement state from credit_ledger + subscriptions.

        users.tier_id is updated as a denormalized cache but is never
        the sole source of truth.
        """
        user_id_str = str(user_id)

        # Fetch user row
        user_result = (
            self._sb.table("users")
            .select("tier_id, trial_analyses_remaining")
            .eq("id", user_id_str)
            .is_("deleted_at", "null")
            .single()
            .execute()
        )
        if not user_result.data:
            raise ValueError(f"User {user_id} not found")

        tier_id = UUID(user_result.data["tier_id"])
        trial_remaining: int = user_result.data["trial_analyses_remaining"]

        # Fetch tier record (Redis-cached)
        tier = await self._tier_repo.get(tier_id)

        # Compute credit balance from ledger (authoritative)
        credit_balance = self._ledger.balance(user_id)

        # Check active subscription
        sub_result = (
            self._sb.table("subscriptions")
            .select("status, billing_period_end")
            .eq("user_id", user_id_str)
            .eq("status", "active")
            .limit(1)
            .execute()
        )
        has_subscription = bool(sub_result.data)
        billing_end: datetime | None = None
        if has_subscription and sub_result.data:
            end_str = sub_result.data[0].get("billing_period_end")
            if end_str:
                billing_end = datetime.fromisoformat(end_str)
                if billing_end.tzinfo is None:
                    billing_end = billing_end.replace(tzinfo=timezone.utc)

        # Determine can_generate
        can_gen_result = await self.can_generate(user_id)

        return EntitlementState(
            tier=tier,
            trial_analyses_remaining=trial_remaining,
            credit_balance=credit_balance,
            has_active_subscription=has_subscription,
            subscription_billing_period_end=billing_end,
            can_generate=can_gen_result.can_generate,
            reason=can_gen_result.reason,
        )

    # ------------------------------------------------------------------
    # can_generate (AC-2)
    # ------------------------------------------------------------------

    async def can_generate(self, user_id: UUID) -> CanGenerateResult:
        """Check if a user can generate (without consuming anything)."""
        tier = await self._get_tier(user_id)
        gen_type = LimitType(tier.generation_type)

        if gen_type == LimitType.UNLIMITED:
            return CanGenerateResult(can_generate=True)

        if gen_type == LimitType.CREDITS:
            balance = self._ledger.balance(user_id)
            if balance > 0:
                return CanGenerateResult(can_generate=True)
            return CanGenerateResult(can_generate=False, reason="No credits remaining")

        # Time-window or total limit
        if gen_type == LimitType.TOTAL:
            used = self._usage.count_total(user_id, "generation")
        else:
            window_seconds = _get_window_seconds(gen_type, tier.generation_period_seconds)
            used = self._usage.count_in_window(user_id, "generation", window_seconds)

        limit = tier.generation_limit or 0
        if used < limit:
            return CanGenerateResult(can_generate=True)

        return CanGenerateResult(can_generate=False, reason="Generation limit reached")

    # ------------------------------------------------------------------
    # check (A-5: route-level enforcement)
    # ------------------------------------------------------------------

    async def check(self, user_id: UUID, action: str) -> EntitlementResult:
        """Full entitlement check with error codes for API responses."""
        tier = await self._get_tier(user_id)

        if action == "generation":
            return await self._check_generation(user_id, tier)

        if action == "advisor_nudge":
            return await self._check_window(
                user_id,
                action="advisor_nudge",
                limit_type=LimitType(tier.advisor_nudges_type),
                limit=tier.advisor_nudges_limit,
                period_seconds=tier.advisor_nudges_period_seconds,
            )

        raise ValueError(f"Unknown entitlement action: {action}")

    async def _check_generation(self, user_id: UUID, tier: TierRecord) -> EntitlementResult:
        """Generation-specific check: concurrent guard + credits/window."""
        # 1. Concurrent guard (Redis)
        # Note: this is a read-only check. The actual INCR/DECR happens in the
        # ARQ worker at job start/end. A small race window exists between this
        # check and the worker INCR, but it's acceptable — the worker also
        # checks and rejects if over limit.
        concurrent_key = f"concurrent:{user_id}"
        current = int(await self._redis.get(concurrent_key) or 0)
        if current >= tier.max_concurrent_generations:
            return EntitlementResult(
                allowed=False,
                error_code=TIER_CONCURRENT_LIMIT,
                upgrade_available=False,
            )

        # 2. Credits check
        if tier.credits_based:
            balance = self._ledger.balance(user_id)
            if balance <= 0:
                return EntitlementResult(
                    allowed=False,
                    error_code=TIER_LIMIT_CREDITS,
                    upgrade_available=True,
                )
            return EntitlementResult(allowed=True)

        # 3. Time-window / total check
        return await self._check_window(
            user_id,
            action="generation",
            limit_type=LimitType(tier.generation_type),
            limit=tier.generation_limit,
            period_seconds=tier.generation_period_seconds,
        )

    async def _check_window(
        self,
        user_id: UUID,
        action: str,
        limit_type: LimitType,
        limit: int | None,
        period_seconds: int | None = None,
    ) -> EntitlementResult:
        """Check usage against a time-window or total limit."""
        if limit_type == LimitType.UNLIMITED:
            return EntitlementResult(allowed=True)

        if limit is None:
            return EntitlementResult(allowed=True)

        error_code = _LIMIT_CODE.get(limit_type, TIER_LIMIT_DAILY)

        # Get usage count
        if limit_type == LimitType.TOTAL:
            used = self._usage.count_total(user_id, action)
        else:
            window_seconds = _get_window_seconds(limit_type, period_seconds)
            used = self._usage.count_in_window(user_id, action, window_seconds)

        if used < limit:
            return EntitlementResult(allowed=True, limit=limit, used=used)

        # Compute retry_after from the earliest event in the window
        # (when that event ages out, the user regains capacity)
        retry_after: datetime | None = None
        reset_in: int | None = None
        window = _LIMIT_WINDOW.get(limit_type)
        if window is not None and limit_type != LimitType.TOTAL:
            window_seconds = _get_window_seconds(limit_type, period_seconds)
            earliest = self._usage.earliest_in_window(user_id, action, window_seconds)
            if earliest:
                retry_after = earliest + window
                reset_in = max(0, int((retry_after - datetime.now(tz=timezone.utc)).total_seconds()))

        return EntitlementResult(
            allowed=False,
            error_code=error_code,
            limit=limit,
            used=used,
            retry_after=retry_after,
            reset_in_seconds=reset_in,
            upgrade_available=True,
        )

    # ------------------------------------------------------------------
    # Feature check (A-5)
    # ------------------------------------------------------------------

    async def has_feature(self, user_id: UUID, feature: str) -> bool:
        """Check if user's tier has a specific feature enabled."""
        tier = await self._get_tier(user_id)
        return getattr(tier, f"feature_{feature}", False)

    async def max_concurrent(self, user_id: UUID) -> int:
        """Get max concurrent generations for user's tier."""
        return (await self._get_tier(user_id)).max_concurrent_generations

    async def similarity_threshold(self, user_id: UUID) -> float:
        """Get identity similarity threshold for user's tier."""
        return (await self._get_tier(user_id)).identity_similarity_threshold

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_tier(self, user_id: UUID) -> TierRecord:
        """Fetch the user's tier record (Redis-cached)."""
        user_result = (
            self._sb.table("users")
            .select("tier_id")
            .eq("id", str(user_id))
            .is_("deleted_at", "null")
            .single()
            .execute()
        )
        if not user_result.data:
            raise ValueError(f"User {user_id} not found")

        return await self._tier_repo.get(UUID(user_result.data["tier_id"]))


def _get_window_seconds(limit_type: LimitType, period_seconds: int | None) -> int:
    """Convert LimitType to window seconds."""
    if limit_type == LimitType.PERIOD and period_seconds:
        return period_seconds
    mapping = {
        LimitType.DAILY: 86_400,
        LimitType.WEEKLY: 604_800,
        LimitType.MONTHLY: 2_592_000,  # 30 days
    }
    return mapping.get(limit_type, 86_400)
