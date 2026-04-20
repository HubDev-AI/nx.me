"""Entitlement data models — ledger-based (Unit 7).

New shape:
  EntitlementState carries tier (marketing label), remaining_glowups,
  approx_remaining_ada, subscription_status, period_end, grace_end,
  blocked_reason, plan_version_id, and purchase_options.

R2: TierRecord and TierRepository removed; tiers table dropped in migration 0054.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Subscription status (pure enum — drives tier label + blocked_reason)
# ---------------------------------------------------------------------------


class SubscriptionStatus(str, Enum):
    """Derived subscription state (R3 derivation logic)."""

    NONE = "none"
    ACTIVE = "active"
    GRACE = "grace"
    CANCELED = "canceled"
    LOCKED = "locked"


# ---------------------------------------------------------------------------
# Blocked reason
# ---------------------------------------------------------------------------


class BlockedReason(str, Enum):
    """Why a user account is blocked (state-level, not per-action)."""

    NONE = "none"
    SUBSCRIPTION_LOCKED_BY_DISPUTE = "subscription_locked_by_dispute"
    INSUFFICIENT_CREDITS = "insufficient_credits"


# ---------------------------------------------------------------------------
# Purchase options (returned inline in EntitlementState for paywall display)
# ---------------------------------------------------------------------------


class ProOption(BaseModel):
    """Pro subscription purchase option."""

    price_id: str
    amount_cents: int
    currency: str


class PurchaseOptions(BaseModel):
    """All available purchase options returned with entitlement state."""

    pro: ProOption | None = None


# ---------------------------------------------------------------------------
# Entitlement state (ledger-based, Unit 7)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EntitlementState:
    """Full entitlement snapshot for a user. Recomputed, never cached as source of truth."""

    # Marketing tier label (R10): "Pro" iff status in {active, grace}, else "Free"
    tier: Literal["Free", "Pro"]
    # How many full glowups the current balance covers
    remaining_glowups: int
    # Approximate Ada messages the current balance covers (floor)
    approx_remaining_ada: int
    # Derived subscription status
    subscription_status: SubscriptionStatus
    # Subscription billing period end (active/grace only)
    period_end: datetime | None
    # Grace period end (grace only; None when status != grace)
    grace_end: datetime | None
    # Account-level block reason
    blocked_reason: BlockedReason
    # The plan_version row used to compute costs
    plan_version_id: UUID
    # Purchase options for paywall display (always populated, fail-soft on Stripe errors)
    purchase_options: PurchaseOptions


# ---------------------------------------------------------------------------
# Error codes — concurrent limit only (used by concurrent_guard callers)
# ---------------------------------------------------------------------------

ACCOUNT_CONCURRENT_LIMIT = "ACCOUNT_CONCURRENT_LIMIT"
INSUFFICIENT_CREDITS = "INSUFFICIENT_CREDITS"
ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
