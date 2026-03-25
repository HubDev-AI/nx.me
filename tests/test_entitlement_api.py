"""Tests for entitlement API models and endpoint logic.

Exercises production code in:
  - app/api/entitlement.py (models, credit purchase validation, subscription logic)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException


try:
    from app.api.entitlement import (
        CreditPackOption, PremiumOption, PurchaseOptions,
        EntitlementResponse, CreditPurchaseRequest, CheckoutResponse,
        CancelSubscriptionResponse,
    )
    _ENTITLEMENT_AVAILABLE = True
except (ImportError, AttributeError):
    _ENTITLEMENT_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _ENTITLEMENT_AVAILABLE, reason="entitlement module unavailable"
)


class TestEntitlementModels:
    """Pydantic model tests — exercises app/api/entitlement.py."""

    def test_credit_pack_option(self):
        opt = CreditPackOption(pack_id="10_credits", credits=10, price_id="price_abc")
        assert opt.credits == 10

    def test_premium_option(self):
        opt = PremiumOption(price_id="price_premium", name="Premium")
        assert opt.name == "Premium"

    def test_purchase_options_with_packs(self):
        opts = PurchaseOptions(
            credit_packs=[CreditPackOption(pack_id="10", credits=10, price_id="p1")],
            premium=None,
        )
        assert len(opts.credit_packs) == 1
        assert opts.premium is None

    def test_entitlement_response_minimal(self):
        resp = EntitlementResponse(
            tier="TRIAL",
            trial_analyses_remaining=2,
            credit_balance=0,
            can_generate=True,
        )
        assert resp.can_generate is True
        assert resp.subscription_status is None

    def test_entitlement_response_full(self):
        resp = EntitlementResponse(
            tier="PREMIUM",
            trial_analyses_remaining=0,
            credit_balance=25,
            can_generate=True,
            subscription_status="active",
            billing_period_end="2026-04-01T00:00:00+00:00",
        )
        assert resp.subscription_status == "active"

    def test_credit_purchase_request(self):
        req = CreditPurchaseRequest(credit_pack_id="25_credits")
        assert req.credit_pack_id == "25_credits"

    def test_checkout_response(self):
        resp = CheckoutResponse(checkout_url="https://checkout.stripe.com/sess_123")
        assert "stripe.com" in resp.checkout_url

    def test_cancel_subscription_response(self):
        resp = CancelSubscriptionResponse(status="cancelling", message="Will cancel at period end")
        assert resp.status == "cancelling"


class TestCreateCreditPurchase:
    """Tests for POST /credit-purchases — exercises app/api/entitlement.py."""

    @pytest.mark.asyncio
    async def test_invalid_pack_id(self):
        from app.api.entitlement import create_credit_purchase

        body = CreditPurchaseRequest(credit_pack_id="999_credits")
        claims = {"sub": str(uuid4())}
        payment = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await create_credit_purchase(body=body, claims=claims, payment=payment)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_unconfigured_price_id(self):
        from app.api.entitlement import create_credit_purchase

        body = CreditPurchaseRequest(credit_pack_id="10_credits")
        claims = {"sub": str(uuid4())}
        payment = AsyncMock()

        # settings.STRIPE_PRICE_CREDITS_10 is empty string by default in test env
        with pytest.raises(HTTPException) as exc_info:
            await create_credit_purchase(body=body, claims=claims, payment=payment)
        assert exc_info.value.status_code == 503


class TestCancelSubscription:
    """Tests for DELETE /subscriptions — exercises app/api/entitlement.py."""

    @pytest.mark.asyncio
    async def test_no_active_subscription(self):
        from app.api.entitlement import cancel_subscription

        claims = {"sub": str(uuid4())}
        sub_repo = MagicMock()
        sub_repo.get_active_subscription.return_value = None
        payment = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await cancel_subscription(claims=claims, sub_repo=sub_repo, payment=payment)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_success(self):
        from app.api.entitlement import cancel_subscription

        claims = {"sub": str(uuid4())}
        sub_repo = MagicMock()
        sub_repo.get_active_subscription.return_value = {
            "provider_subscription_id": "sub_123"
        }
        payment = AsyncMock()

        result = await cancel_subscription(claims=claims, sub_repo=sub_repo, payment=payment)
        assert result.status == "cancelling"
        payment.cancel_subscription.assert_called_once_with("sub_123")
