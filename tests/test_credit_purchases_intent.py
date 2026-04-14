"""Tests for POST /v1/credit-purchases/intent — Stripe Payment Sheet bootstrap.

Exercises production code in:
  - app/api/entitlement.py (create_credit_purchase_intent)
  - app/payment/adapters/mock.py (MockPaymentAdapter.create_payment_intent)
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException


try:
    from app.api.entitlement import (
        CreditPurchaseIntentRequest,
        CreditPurchaseIntentResponse,
        FLOW_PAYMENT_SHEET,
        create_credit_purchase_intent,
    )
    from app.payment.ports import PaymentIntentBundle

    _ENTITLEMENT_AVAILABLE = True
except (ImportError, AttributeError):
    _ENTITLEMENT_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _ENTITLEMENT_AVAILABLE, reason="entitlement module unavailable"
)


class TestCreditPurchaseIntentModels:
    """Pydantic model sanity checks."""

    def test_request_model(self):
        req = CreditPurchaseIntentRequest(credit_pack_id="10_credits")
        assert req.credit_pack_id == "10_credits"

    def test_response_model(self):
        resp = CreditPurchaseIntentResponse(
            payment_intent_client_secret="pi_123_secret_abc",
            ephemeral_key="ek_456",
            customer_id="cus_789",
            publishable_key="pk_test_xyz",
        )
        assert resp.payment_intent_client_secret.startswith("pi_")
        assert resp.customer_id == "cus_789"


class TestCreateCreditPurchaseIntent:
    """Endpoint-level tests for POST /credit-purchases/intent."""

    @staticmethod
    def _bundle(user_id: str) -> PaymentIntentBundle:
        return PaymentIntentBundle(
            client_secret=f"pi_{user_id}_secret",
            ephemeral_key="ek_test",
            customer_id=f"cus_{user_id}",
            publishable_key="pk_test_fake",
        )

    @pytest.mark.asyncio
    async def test_invalid_pack_id_returns_400(self):
        body = CreditPurchaseIntentRequest(credit_pack_id="999_credits")
        claims = {"sub": str(uuid4())}
        payment = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await create_credit_purchase_intent(
                body=body, claims=claims, payment=payment
            )
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["error"]["code"] == "INVALID_CREDIT_PACK"
        payment.create_payment_intent.assert_not_called()

    @pytest.mark.asyncio
    async def test_unconfigured_price_returns_503(self, monkeypatch):
        from app.api import entitlement as ent_module

        # Clear any prior monkeypatch so STRIPE_PRICE_CREDITS_10 is empty.
        monkeypatch.setattr(ent_module.settings, "STRIPE_PRICE_CREDITS_10", "")

        body = CreditPurchaseIntentRequest(credit_pack_id="10_credits")
        claims = {"sub": str(uuid4())}
        payment = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await create_credit_purchase_intent(
                body=body, claims=claims, payment=payment
            )
        assert exc_info.value.status_code == 503
        assert exc_info.value.detail["error"]["code"] == "CREDIT_PACK_NOT_CONFIGURED"
        payment.create_payment_intent.assert_not_called()

    @pytest.mark.asyncio
    async def test_happy_path_returns_bundle(self, monkeypatch):
        from app.api import entitlement as ent_module

        monkeypatch.setattr(
            ent_module.settings, "STRIPE_PRICE_CREDITS_10", "price_10_test"
        )

        user_id = str(uuid4())
        body = CreditPurchaseIntentRequest(credit_pack_id="10_credits")
        claims = {"sub": user_id}
        payment = AsyncMock()
        payment.create_payment_intent.return_value = self._bundle(user_id)

        resp = await create_credit_purchase_intent(
            body=body, claims=claims, payment=payment
        )

        assert isinstance(resp, CreditPurchaseIntentResponse)
        assert resp.payment_intent_client_secret == f"pi_{user_id}_secret"
        assert resp.customer_id == f"cus_{user_id}"
        assert resp.ephemeral_key == "ek_test"
        assert resp.publishable_key == "pk_test_fake"

        payment.create_payment_intent.assert_called_once()
        kwargs = payment.create_payment_intent.call_args.kwargs
        assert kwargs["user_id"] == user_id
        assert kwargs["price_id"] == "price_10_test"
        assert kwargs["metadata"]["flow"] == FLOW_PAYMENT_SHEET
        assert kwargs["metadata"]["credits"] == "10"
        assert kwargs["metadata"]["pack_id"] == "10_credits"


class TestMockPaymentAdapterCreatePaymentIntent:
    """Sanity check the mock adapter returns deterministic data."""

    @pytest.mark.asyncio
    async def test_mock_adapter_returns_deterministic_bundle(self):
        from app.payment.adapters.mock import MockPaymentAdapter

        adapter = MockPaymentAdapter()
        bundle = await adapter.create_payment_intent(
            user_id="user-1", price_id="price_10", metadata={"flow": "payment_sheet"}
        )
        assert bundle.client_secret == "pi_mock_user-1_secret"
        assert bundle.customer_id == "cus_mock_user-1"
        assert bundle.ephemeral_key == "ek_mock"
        assert bundle.publishable_key.startswith("pk_")
