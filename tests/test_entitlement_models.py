"""Tests for entitlement data models and error codes.

Exercises production code in:
  - app/entitlement/models.py (EntitlementResult, PAYMENT_REQUIRED_CODES, etc.)
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.entitlement.models import (
    EntitlementResult,
    TierRecord,
    EntitlementState,
    CanGenerateResult,
    TIER_LIMIT_DAILY,
    TIER_LIMIT_WEEKLY,
    TIER_LIMIT_MONTHLY,
    TIER_LIMIT_TOTAL,
    TIER_LIMIT_CREDITS,
    TIER_FEATURE_LOCKED,
    TIER_CONCURRENT_LIMIT,
    PAYMENT_REQUIRED_CODES,
)


class TestEntitlementResult:
    """Tests for EntitlementResult dataclass — exercises app/entitlement/models.py."""

    def test_allowed_result(self):
        result = EntitlementResult(allowed=True)
        assert result.allowed is True
        assert result.error_code is None

    def test_denied_result_with_error_code(self):
        result = EntitlementResult(
            allowed=False,
            error_code=TIER_LIMIT_DAILY,
            limit=10,
            used=10,
        )
        assert result.allowed is False
        assert result.error_code == "TIER_LIMIT_DAILY"
        assert result.limit == 10
        assert result.used == 10

    def test_denied_with_retry_after(self):
        retry = datetime(2026, 3, 18, 0, 0, 0, tzinfo=timezone.utc)
        result = EntitlementResult(
            allowed=False,
            error_code=TIER_LIMIT_DAILY,
            retry_after=retry,
            reset_in_seconds=3600,
        )
        assert result.retry_after == retry
        assert result.reset_in_seconds == 3600

    def test_upgrade_available_flag(self):
        result = EntitlementResult(
            allowed=False,
            error_code=TIER_LIMIT_TOTAL,
            upgrade_available=True,
        )
        assert result.upgrade_available is True


class TestPaymentRequiredCodes:
    """Tests for PAYMENT_REQUIRED_CODES — exercises app/entitlement/models.py."""

    def test_total_is_payment_required(self):
        assert TIER_LIMIT_TOTAL in PAYMENT_REQUIRED_CODES

    def test_credits_is_payment_required(self):
        assert TIER_LIMIT_CREDITS in PAYMENT_REQUIRED_CODES

    def test_feature_locked_is_payment_required(self):
        assert TIER_FEATURE_LOCKED in PAYMENT_REQUIRED_CODES

    def test_daily_is_not_payment_required(self):
        assert TIER_LIMIT_DAILY not in PAYMENT_REQUIRED_CODES

    def test_weekly_is_not_payment_required(self):
        assert TIER_LIMIT_WEEKLY not in PAYMENT_REQUIRED_CODES

    def test_concurrent_is_not_payment_required(self):
        assert TIER_CONCURRENT_LIMIT not in PAYMENT_REQUIRED_CODES


class TestCanGenerateResult:
    """Tests for CanGenerateResult — exercises app/entitlement/models.py."""

    def test_can_generate_true(self):
        result = CanGenerateResult(can_generate=True)
        assert result.can_generate is True
        assert result.reason is None

    def test_can_generate_false_with_reason(self):
        result = CanGenerateResult(can_generate=False, reason="Credit balance is 0")
        assert result.can_generate is False
        assert "Credit balance" in result.reason


class TestTierRecord:
    """Tests for TierRecord — exercises app/entitlement/models.py."""

    def test_tier_record_creation(self):
        tier_id = uuid4()
        tier = TierRecord(
            id=tier_id,
            slug="trial",
            display_name="Free Trial",
            is_default=True,
            is_active=True,
            generation_type="total",
            generation_limit=2,
            generation_period_seconds=None,
            advisor_nudges_type="total",
            advisor_nudges_limit=5,
            advisor_nudges_period_seconds=None,
            max_concurrent_generations=1,
            identity_similarity_threshold=0.80,
            feature_advisor_chat=False,
            feature_visual_comparison=False,
            stripe_price_id=None,
            credits_based=False,
        )
        assert tier.slug == "trial"
        assert tier.is_default is True
        assert tier.generation_limit == 2

    def test_tier_record_is_frozen(self):
        tier_id = uuid4()
        tier = TierRecord(
            id=tier_id,
            slug="trial",
            display_name="Free Trial",
            is_default=True,
            is_active=True,
            generation_type="total",
            generation_limit=2,
            generation_period_seconds=None,
            advisor_nudges_type="total",
            advisor_nudges_limit=5,
            advisor_nudges_period_seconds=None,
            max_concurrent_generations=1,
            identity_similarity_threshold=0.80,
            feature_advisor_chat=False,
            feature_visual_comparison=False,
            stripe_price_id=None,
            credits_based=False,
        )
        with pytest.raises(AttributeError):
            tier.slug = "premium"  # type: ignore[misc]
