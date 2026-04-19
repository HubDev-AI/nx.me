"""Entitlement service — ledger-based entitlement state.

Unit 7 rewrite: tier-gating removed entirely. Single public method:
  EntitlementService.get_entitlement(user_id, *, purchase_options) -> EntitlementState

Pure derivation function exposed at module level for testing:
  derive_subscription_status(subscription, locked_at, now) -> SubscriptionStatus
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

import redis.asyncio as aioredis
from supabase import Client

from app.db.async_helpers import run_sync
from app.entitlement.ledger import CreditLedger
from app.entitlement.models import (
    BlockedReason,
    EntitlementState,
    PurchaseOptions,
    SubscriptionStatus,
)
from app.repositories.plan_version_repo import PlanVersionRepository

logger = logging.getLogger(__name__)


def derive_subscription_status(
    subscription: dict | None,
    locked_at: str | datetime | None,
    now: datetime,
) -> SubscriptionStatus:
    """Pure derivation: subscription dates + locked_at → SubscriptionStatus.

    Logic (R3, R10):
    - locked_at not None → LOCKED (overrides everything)
    - subscription None → NONE
    - subscription.status == 'canceled' → CANCELED
    - grace_period_end > now → GRACE
    - billing_period_end > now → ACTIVE
    - billing_period_end is None and status == 'active' → ACTIVE
    - else → NONE (post-grace expiry)

    Naive datetimes treated as UTC.
    """
    if locked_at is not None:
        return SubscriptionStatus.LOCKED

    if subscription is None:
        return SubscriptionStatus.NONE

    status = subscription.get("status", "")

    if status == "canceled":
        return SubscriptionStatus.CANCELED

    # Parse helper: string or datetime → aware datetime (UTC)
    def _parse(value: str | datetime | None) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, str):
            dt = datetime.fromisoformat(value)
        else:
            dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    grace_end = _parse(subscription.get("grace_period_end"))
    billing_end = _parse(subscription.get("billing_period_end"))

    # Grace check runs before billing check so an expired billing period
    # with a live grace window yields GRACE, not NONE.
    if grace_end is not None and grace_end > now:
        return SubscriptionStatus.GRACE

    if billing_end is not None and billing_end > now:
        return SubscriptionStatus.ACTIVE

    if billing_end is None and status == "active":
        return SubscriptionStatus.ACTIVE

    return SubscriptionStatus.NONE


class EntitlementService:
    """Single authoritative entitlement module (ledger-based, Unit 7)."""

    def __init__(
        self,
        supabase: Client,
        redis_client: aioredis.Redis,
    ) -> None:
        self._sb = supabase
        self._redis = redis_client
        self._ledger = CreditLedger(supabase)
        self._plan_version_repo = PlanVersionRepository(supabase)

    async def get_entitlement(
        self,
        user_id: UUID,
        *,
        purchase_options: PurchaseOptions,
    ) -> EntitlementState:
        """Recompute full entitlement snapshot from ledger + subscriptions.

        Never cached as source of truth — always recomputed on each call.
        """
        user_id_str = str(user_id)
        now = datetime.now(tz=timezone.utc)

        # 1. Fetch user row (locked_at, stripe_customer_id)
        user_result = await run_sync(
            lambda: (
                self._sb.table("users")
                .select("locked_at, stripe_customer_id")
                .eq("id", user_id_str)
                .single()
                .execute()
            )
        )
        if not user_result.data:
            raise ValueError(f"User {user_id} not found")

        locked_at = user_result.data.get("locked_at")

        # 2. Fetch latest subscription row (status, billing_period_end,
        #    grace_period_end, plan_version_id, cancelled_at)
        sub_result = await run_sync(
            lambda: (
                self._sb.table("subscriptions")
                .select(
                    "status, billing_period_end, grace_period_end, "
                    "plan_version_id, cancelled_at"
                )
                .eq("user_id", user_id_str)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
        )
        sub: dict | None = sub_result.data[0] if sub_result.data else None

        # 3. Derive subscription status
        subscription_status = derive_subscription_status(sub, locked_at, now)

        # 4. Derive tier label
        _active_statuses = {SubscriptionStatus.ACTIVE, SubscriptionStatus.GRACE}
        tier: str = "Pro" if subscription_status in _active_statuses else "Free"

        # 5. Resolve plan_version (sync repo — wrap with run_sync)
        plan_version_row = await run_sync(
            self._plan_version_repo.get_active_version_for_user, user_id
        )
        plan_version_id = UUID(plan_version_row["id"])
        glowup_cost_milli: int = plan_version_row["glowup_cost_milli"]
        ada_cost_milli: int = plan_version_row["ada_cost_milli"]

        # 6. Fetch credit balance
        balance_milli = await run_sync(self._ledger.balance, user_id)

        # 7. Compute remaining counts
        remaining_glowups = (
            balance_milli // glowup_cost_milli if glowup_cost_milli else 0
        )
        approx_remaining_ada = balance_milli // ada_cost_milli if ada_cost_milli else 0

        # 8. Blocked reason
        blocked_reason = (
            BlockedReason.SUBSCRIPTION_LOCKED_BY_DISPUTE
            if locked_at
            else BlockedReason.NONE
        )

        # 9. Period end / grace end
        period_end: datetime | None = None
        grace_end: datetime | None = None
        if sub and subscription_status in _active_statuses:
            end_str = sub.get("billing_period_end")
            if end_str:
                period_end = datetime.fromisoformat(end_str)
                if period_end.tzinfo is None:
                    period_end = period_end.replace(tzinfo=timezone.utc)
        if sub and subscription_status == SubscriptionStatus.GRACE:
            grace_str = sub.get("grace_period_end")
            if grace_str:
                grace_end = datetime.fromisoformat(grace_str)
                if grace_end.tzinfo is None:
                    grace_end = grace_end.replace(tzinfo=timezone.utc)

        return EntitlementState(
            tier=tier,  # type: ignore[arg-type]
            remaining_glowups=remaining_glowups,
            approx_remaining_ada=approx_remaining_ada,
            subscription_status=subscription_status,
            period_end=period_end,
            grace_end=grace_end,
            blocked_reason=blocked_reason,
            plan_version_id=plan_version_id,
            purchase_options=purchase_options,
        )
