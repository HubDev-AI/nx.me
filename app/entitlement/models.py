"""Entitlement data models.

AC-D1: All entitlement state is computed from credit_ledger + subscriptions.
A-4: Tiers are DB-driven; tier_id UUID FK, not string enums.
A-5: EntitlementResult with error codes for rate/feature gating.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


# ---------------------------------------------------------------------------
# Tier record (cached from DB, per A-4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TierRecord:
    """A tier row from the tiers table (Redis-cached, TTL 5 min)."""

    id: UUID
    slug: str
    display_name: str
    is_default: bool
    is_active: bool
    generation_type: str  # LimitType value: daily, weekly, monthly, credits, total, unlimited
    generation_limit: int | None
    generation_period_seconds: int | None
    advisor_nudges_type: str
    advisor_nudges_limit: int | None
    advisor_nudges_period_seconds: int | None
    max_concurrent_generations: int
    identity_similarity_threshold: float
    feature_advisor_chat: bool
    feature_visual_comparison: bool
    stripe_price_id: str | None
    credits_based: bool


# ---------------------------------------------------------------------------
# Entitlement state (recomputed from credit_ledger + subscriptions)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EntitlementState:
    """Full entitlement snapshot for a user. Recomputed, never cached as source of truth."""

    tier: TierRecord
    trial_analyses_remaining: int
    credit_balance: int
    has_active_subscription: bool
    subscription_billing_period_end: datetime | None = None
    can_generate: bool = False
    reason: str | None = None  # Why can_generate is False


# ---------------------------------------------------------------------------
# can_generate result (AC-2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CanGenerateResult:
    """Result of EntitlementService.can_generate()."""

    can_generate: bool
    reason: str | None = None


# ---------------------------------------------------------------------------
# Entitlement check result (A-5)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EntitlementResult:
    """Result of EntitlementService.check() — route-level enforcement."""

    allowed: bool
    error_code: str | None = None
    limit: int | None = None
    used: int | None = None
    retry_after: datetime | None = None
    reset_in_seconds: int | None = None
    upgrade_available: bool = False


# ---------------------------------------------------------------------------
# Error codes (A-5)
# ---------------------------------------------------------------------------

TIER_LIMIT_DAILY = "TIER_LIMIT_DAILY"
TIER_LIMIT_WEEKLY = "TIER_LIMIT_WEEKLY"
TIER_LIMIT_MONTHLY = "TIER_LIMIT_MONTHLY"
TIER_LIMIT_TOTAL = "TIER_LIMIT_TOTAL"
TIER_LIMIT_CREDITS = "TIER_LIMIT_CREDITS"
TIER_FEATURE_LOCKED = "TIER_FEATURE_LOCKED"
TIER_CONCURRENT_LIMIT = "TIER_CONCURRENT_LIMIT"

# HTTP status mapping: 429 = "try later", 402 = "pay to unlock"
PAYMENT_REQUIRED_CODES = frozenset({TIER_LIMIT_TOTAL, TIER_LIMIT_CREDITS, TIER_FEATURE_LOCKED})

# User-facing error messages for entitlement failures
ENTITLEMENT_ERROR_MESSAGES: dict[str, str] = {
    TIER_LIMIT_DAILY: "Daily generation limit reached",
    TIER_LIMIT_WEEKLY: "Weekly generation limit reached",
    TIER_LIMIT_MONTHLY: "Monthly generation limit reached",
    TIER_LIMIT_TOTAL: "Lifetime generation limit reached",
    TIER_LIMIT_CREDITS: "No credits remaining",
    TIER_FEATURE_LOCKED: "Feature not available on your current plan",
    TIER_CONCURRENT_LIMIT: "A generation is already in progress",
}
