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
        CreditPackOption,
        PremiumOption,
        PurchaseOptions,
        EntitlementResponse,
        CreditPurchaseRequest,
        CheckoutResponse,
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
        opt = CreditPackOption(
            pack_id="10_credits",
            credits=10,
            price_id="price_abc",
            amount_cents=499,
            currency="usd",
        )
        assert opt.credits == 10
        assert opt.amount_cents == 499
        assert opt.currency == "usd"

    def test_premium_option(self):
        opt = PremiumOption(
            price_id="price_premium",
            name="Premium",
            amount_cents=999,
            currency="usd",
        )
        assert opt.name == "Premium"
        assert opt.amount_cents == 999

    def test_purchase_options_with_packs(self):
        opts = PurchaseOptions(
            credit_packs=[
                CreditPackOption(
                    pack_id="10",
                    credits=10,
                    price_id="p1",
                    amount_cents=499,
                    currency="usd",
                )
            ],
            premium=None,
        )
        assert len(opts.credit_packs) == 1
        assert opts.premium is None

    def test_entitlement_response_minimal(self):
        resp = EntitlementResponse(
            tier="TRIAL",
            trial_analyses_remaining=2,
            trial_analyses_limit=2,
            credit_balance=0,
            can_generate=True,
        )
        assert resp.can_generate is True
        assert resp.subscription_status is None
        assert resp.trial_analyses_limit == 2

    def test_entitlement_response_full(self):
        resp = EntitlementResponse(
            tier="PREMIUM",
            trial_analyses_remaining=0,
            trial_analyses_limit=2,
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
        resp = CancelSubscriptionResponse(
            status="cancelling", message="Will cancel at period end"
        )
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

        result = await cancel_subscription(
            claims=claims, sub_repo=sub_repo, payment=payment
        )
        assert result.status == "cancelling"
        payment.cancel_subscription.assert_called_once_with("sub_123")


class TestGetEntitlementEnhancements:
    """Behavioral tests for get_entitlement enhancements:
    - purchase_options always populated (regression: previously gated on
      can_generate == false)
    - amount_cents + currency populated from PaymentPort.get_price
    - Stripe price retrieval failure skips that pack rather than 500ing
    - trial_analyses_limit returned in response
    """

    @staticmethod
    def _make_state(*, can_generate: bool = True, trial_remaining: int = 1):
        from app.entitlement.models import EntitlementState, TierRecord

        tier = TierRecord(
            id=uuid4(),
            slug="free",
            display_name="Free",
            is_default=True,
            is_active=True,
            generation_type="total",
            generation_limit=2,
            generation_period_seconds=None,
            advisor_nudges_type="daily",
            advisor_nudges_limit=5,
            advisor_nudges_period_seconds=86400,
            max_concurrent_generations=1,
            identity_similarity_threshold=0.8,
            feature_advisor_chat=False,
            feature_visual_comparison=False,
            stripe_price_id=None,
            credits_based=False,
        )
        return EntitlementState(
            tier=tier,
            trial_analyses_remaining=trial_remaining,
            trial_analyses_limit=2,
            credit_balance=5,
            has_active_subscription=False,
            can_generate=can_generate,
        )

    @staticmethod
    def _payment_with_prices(prices: dict[str, tuple[int, str]]):
        """AsyncMock payment adapter returning PriceInfo for known IDs,
        raising for unknown ones (callers can override per-test)."""
        from app.payment.ports import PriceInfo

        mock = AsyncMock()

        async def _get_price(price_id: str) -> PriceInfo:
            if price_id in prices:
                cents, currency = prices[price_id]
                return PriceInfo(
                    price_id=price_id, amount_cents=cents, currency=currency
                )
            raise RuntimeError(f"Unknown price: {price_id}")

        mock.get_price.side_effect = _get_price
        return mock

    @pytest.mark.asyncio
    async def test_purchase_options_populated_when_can_generate(self, monkeypatch):
        """Regression: purchase_options must be populated even when the user
        can still generate — the mobile subscription screen needs them for
        preemptive top-up."""
        from app.api import entitlement as ent_module
        from app.api.entitlement import get_entitlement

        monkeypatch.setattr(ent_module.settings, "STRIPE_PRICE_CREDITS_10", "price_10")

        svc = MagicMock()
        svc.get_entitlement = AsyncMock(
            return_value=self._make_state(can_generate=True)
        )
        svc.get_tier_stripe_price_id = AsyncMock(return_value=None)

        payment = self._payment_with_prices({"price_10": (499, "usd")})

        resp = await get_entitlement(
            claims={"sub": str(uuid4())}, svc=svc, payment=payment
        )

        assert resp.can_generate is True
        assert resp.purchase_options is not None
        assert len(resp.purchase_options.credit_packs) == 1
        pack = resp.purchase_options.credit_packs[0]
        assert pack.amount_cents == 499
        assert pack.currency == "usd"

    @pytest.mark.asyncio
    async def test_amount_cents_and_currency_populated(self, monkeypatch):
        from app.api import entitlement as ent_module
        from app.api.entitlement import get_entitlement

        monkeypatch.setattr(ent_module.settings, "STRIPE_PRICE_CREDITS_10", "price_10")
        monkeypatch.setattr(ent_module.settings, "STRIPE_PRICE_CREDITS_25", "price_25")

        svc = MagicMock()
        svc.get_entitlement = AsyncMock(
            return_value=self._make_state(can_generate=False)
        )
        svc.get_tier_stripe_price_id = AsyncMock(return_value="price_premium")

        payment = self._payment_with_prices(
            {
                "price_10": (499, "usd"),
                "price_25": (1099, "usd"),
                "price_premium": (999, "usd"),
            }
        )

        resp = await get_entitlement(
            claims={"sub": str(uuid4())}, svc=svc, payment=payment
        )

        assert resp.purchase_options is not None
        # Credit packs in declared order (10, 25)
        cents = {p.pack_id: p.amount_cents for p in resp.purchase_options.credit_packs}
        assert cents == {"10_credits": 499, "25_credits": 1099}
        assert resp.purchase_options.premium is not None
        assert resp.purchase_options.premium.amount_cents == 999
        assert resp.purchase_options.premium.currency == "usd"

    @pytest.mark.asyncio
    async def test_stripe_failure_skips_pack_does_not_500(self, monkeypatch):
        """If Stripe price retrieval fails for one pack, that pack is
        dropped (logged as warning) and the endpoint still responds."""
        from app.api import entitlement as ent_module
        from app.api.entitlement import get_entitlement

        monkeypatch.setattr(ent_module.settings, "STRIPE_PRICE_CREDITS_10", "price_10")
        monkeypatch.setattr(
            ent_module.settings, "STRIPE_PRICE_CREDITS_25", "price_broken"
        )

        svc = MagicMock()
        svc.get_entitlement = AsyncMock(
            return_value=self._make_state(can_generate=False)
        )
        svc.get_tier_stripe_price_id = AsyncMock(return_value="price_premium_broken")

        # price_10 succeeds; price_broken + premium both raise
        payment = self._payment_with_prices({"price_10": (499, "usd")})

        resp = await get_entitlement(
            claims={"sub": str(uuid4())}, svc=svc, payment=payment
        )

        assert resp.purchase_options is not None
        # Only the working pack survived
        assert len(resp.purchase_options.credit_packs) == 1
        assert resp.purchase_options.credit_packs[0].pack_id == "10_credits"
        # Premium failure → None (per spec)
        assert resp.purchase_options.premium is None

    @pytest.mark.asyncio
    async def test_trial_analyses_limit_in_response(self, monkeypatch):
        from app.api.entitlement import get_entitlement

        svc = MagicMock()
        svc.get_entitlement = AsyncMock(
            return_value=self._make_state(can_generate=True)
        )
        svc.get_tier_stripe_price_id = AsyncMock(return_value=None)

        payment = self._payment_with_prices({})

        resp = await get_entitlement(
            claims={"sub": str(uuid4())}, svc=svc, payment=payment
        )

        # Source of truth: settings.FREE_TRIAL_ANALYSES (currently 2)
        from app.config import settings as app_settings

        assert resp.trial_analyses_limit == app_settings.FREE_TRIAL_ANALYSES
