"""Extended tests for entitlement models, constants, and error codes.

Exercises production code in:
  - app/entitlement/models.py (TierRecord, EntitlementState, CanGenerateResult,
    EntitlementResult, error code constants, PAYMENT_REQUIRED_CODES, ENTITLEMENT_ERROR_MESSAGES)
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest


try:
    from app.entitlement.models import (
        TierRecord, EntitlementState, CanGenerateResult, EntitlementResult,
        TIER_LIMIT_DAILY, TIER_LIMIT_WEEKLY, TIER_LIMIT_MONTHLY,
        TIER_LIMIT_TOTAL, TIER_LIMIT_CREDITS, TIER_FEATURE_LOCKED,
        TIER_CONCURRENT_LIMIT, PAYMENT_REQUIRED_CODES,
        ENTITLEMENT_ERROR_MESSAGES,
    )
    _MODELS_AVAILABLE = True
except (ImportError, AttributeError):
    _MODELS_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _MODELS_AVAILABLE, reason="entitlement models unavailable"
)


def _make_tier(**overrides) -> TierRecord:
    defaults = dict(
        id=uuid4(), slug="trial", display_name="Trial", is_default=True,
        is_active=True, generation_type="total", generation_limit=2,
        generation_period_seconds=None, advisor_nudges_type="daily",
        advisor_nudges_limit=5, advisor_nudges_period_seconds=86400,
        max_concurrent_generations=1, identity_similarity_threshold=0.8,
        feature_advisor_chat=False, feature_visual_comparison=False,
        stripe_price_id=None, credits_based=False,
    )
    defaults.update(overrides)
    return TierRecord(**defaults)


class TestTierRecord:
    """Tests for TierRecord dataclass."""

    def test_create_trial_tier(self):
        tier = _make_tier()
        assert tier.slug == "trial"
        assert tier.is_default is True

    def test_create_premium_tier(self):
        tier = _make_tier(
            slug="premium", is_default=False,
            generation_type="unlimited", generation_limit=None,
            feature_advisor_chat=True, feature_visual_comparison=True,
            stripe_price_id="price_premium",
        )
        assert tier.feature_advisor_chat is True
        assert tier.stripe_price_id == "price_premium"

    def test_frozen(self):
        tier = _make_tier()
        with pytest.raises(AttributeError):
            tier.slug = "modified"  # type: ignore[misc]


class TestEntitlementState:
    """Tests for EntitlementState dataclass."""

    def test_trial_state(self):
        tier = _make_tier()
        state = EntitlementState(
            tier=tier, trial_analyses_remaining=2,
            credit_balance=0, has_active_subscription=False,
            can_generate=True,
        )
        assert state.can_generate is True
        assert state.subscription_billing_period_end is None

    def test_premium_state(self):
        tier = _make_tier(slug="premium")
        end = datetime(2026, 4, 1, tzinfo=timezone.utc)
        state = EntitlementState(
            tier=tier, trial_analyses_remaining=0,
            credit_balance=25, has_active_subscription=True,
            subscription_billing_period_end=end,
            can_generate=True,
        )
        assert state.has_active_subscription is True
        assert state.subscription_billing_period_end == end

    def test_cannot_generate(self):
        tier = _make_tier()
        state = EntitlementState(
            tier=tier, trial_analyses_remaining=0,
            credit_balance=0, has_active_subscription=False,
            can_generate=False, reason="No credits remaining",
        )
        assert state.can_generate is False
        assert state.reason is not None


class TestCanGenerateResult:
    """Tests for CanGenerateResult dataclass."""

    def test_allowed(self):
        result = CanGenerateResult(can_generate=True)
        assert result.reason is None

    def test_denied_with_reason(self):
        result = CanGenerateResult(can_generate=False, reason="Limit reached")
        assert result.can_generate is False


class TestEntitlementResult:
    """Tests for EntitlementResult dataclass."""

    def test_allowed(self):
        result = EntitlementResult(allowed=True)
        assert result.error_code is None

    def test_denied_daily(self):
        result = EntitlementResult(
            allowed=False, error_code=TIER_LIMIT_DAILY,
            limit=5, used=5, reset_in_seconds=3600,
        )
        assert result.allowed is False
        assert result.reset_in_seconds == 3600

    def test_denied_credits(self):
        result = EntitlementResult(
            allowed=False, error_code=TIER_LIMIT_CREDITS,
            upgrade_available=True,
        )
        assert result.upgrade_available is True


class TestErrorConstants:
    """Tests for error code constants and mappings."""

    def test_error_code_strings(self):
        assert TIER_LIMIT_DAILY == "TIER_LIMIT_DAILY"
        assert TIER_LIMIT_WEEKLY == "TIER_LIMIT_WEEKLY"
        assert TIER_LIMIT_MONTHLY == "TIER_LIMIT_MONTHLY"
        assert TIER_LIMIT_TOTAL == "TIER_LIMIT_TOTAL"
        assert TIER_LIMIT_CREDITS == "TIER_LIMIT_CREDITS"
        assert TIER_FEATURE_LOCKED == "TIER_FEATURE_LOCKED"
        assert TIER_CONCURRENT_LIMIT == "TIER_CONCURRENT_LIMIT"

    def test_payment_required_codes(self):
        assert TIER_LIMIT_TOTAL in PAYMENT_REQUIRED_CODES
        assert TIER_LIMIT_CREDITS in PAYMENT_REQUIRED_CODES
        assert TIER_FEATURE_LOCKED in PAYMENT_REQUIRED_CODES
        # Rate-limit codes should NOT be payment-required
        assert TIER_LIMIT_DAILY not in PAYMENT_REQUIRED_CODES
        assert TIER_CONCURRENT_LIMIT not in PAYMENT_REQUIRED_CODES

    def test_error_messages_complete(self):
        # Every defined error code should have a message
        for code in (TIER_LIMIT_DAILY, TIER_LIMIT_WEEKLY, TIER_LIMIT_MONTHLY,
                     TIER_LIMIT_TOTAL, TIER_LIMIT_CREDITS, TIER_FEATURE_LOCKED,
                     TIER_CONCURRENT_LIMIT):
            assert code in ENTITLEMENT_ERROR_MESSAGES
            assert len(ENTITLEMENT_ERROR_MESSAGES[code]) > 0
