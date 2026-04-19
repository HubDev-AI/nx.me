"""Tests for the Stripe webhook handler _handle_payment_intent_succeeded.

Exercises production code in:
  - app/api/webhooks.py (_handle_payment_intent_succeeded + event dispatch)
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest


try:
    from app.api.webhooks import _handle_payment_intent_succeeded

    _WEBHOOKS_AVAILABLE = True
except (ImportError, AttributeError):
    _WEBHOOKS_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _WEBHOOKS_AVAILABLE, reason="webhooks module unavailable"
)


def _make_intent(
    *,
    user_id: str | None = None,
    credits: str | int | None = "10",
    flow: str | None = "payment_sheet",
    pack_id: str | None = "10_credits",
) -> dict:
    metadata: dict = {}
    if user_id is not None:
        metadata["user_id"] = user_id
    if credits is not None:
        metadata["credits"] = str(credits)
    if flow is not None:
        metadata["flow"] = flow
    if pack_id is not None:
        metadata["pack_id"] = pack_id
    return {"id": "pi_test", "metadata": metadata}


class TestHandlePaymentIntentSucceeded:
    @pytest.mark.asyncio
    async def test_valid_metadata_grants_credits(self):
        """payment_intent.succeeded with flow=payment_sheet calls credit_apply_pack_purchase.

        Unit 8b: replaced handle_checkout_credit_atomic with call_credit_apply_pack_purchase.
        credits_milli is sourced from settings.CREDIT_PACK_V1_CREDITS_MILLI, not metadata.
        """
        from unittest.mock import patch

        user_id = str(uuid4())
        event_id = "evt_001"
        intent = _make_intent(user_id=user_id, credits=10)

        sub_repo = MagicMock()

        with patch("app.api.webhooks.settings") as mock_settings:
            mock_settings.CREDIT_PACK_V1_CREDITS_MILLI = 500
            await _handle_payment_intent_succeeded(sub_repo, intent, event_id)

        sub_repo.call_credit_apply_pack_purchase.assert_called_once()
        kwargs = sub_repo.call_credit_apply_pack_purchase.call_args.kwargs
        assert kwargs["user_id"] == user_id
        assert kwargs["event_id"] == event_id
        assert kwargs["credits_milli"] == 500

    @pytest.mark.asyncio
    async def test_non_payment_sheet_flow_is_skipped(self):
        """Belt-and-suspenders: legacy Checkout-mode PaymentIntents
        must be ignored by this handler."""
        intent = _make_intent(user_id=str(uuid4()), credits=10, flow="checkout_legacy")

        sub_repo = MagicMock()
        await _handle_payment_intent_succeeded(sub_repo, intent, "evt_002")

        sub_repo.call_credit_apply_pack_purchase.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_flow_metadata_is_skipped(self):
        intent = _make_intent(user_id=str(uuid4()), credits=10, flow=None)

        sub_repo = MagicMock()
        await _handle_payment_intent_succeeded(sub_repo, intent, "evt_003")

        sub_repo.call_credit_apply_pack_purchase.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_user_id_is_skipped(self):
        intent = _make_intent(user_id=None, credits=10)

        sub_repo = MagicMock()
        await _handle_payment_intent_succeeded(sub_repo, intent, "evt_004")

        sub_repo.call_credit_apply_pack_purchase.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_user_id_uuid_is_skipped(self):
        intent = _make_intent(user_id="not-a-uuid", credits=10)

        sub_repo = MagicMock()
        await _handle_payment_intent_succeeded(sub_repo, intent, "evt_005")

        sub_repo.call_credit_apply_pack_purchase.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_metadata_is_skipped(self):
        sub_repo = MagicMock()
        await _handle_payment_intent_succeeded(
            sub_repo, {"id": "pi_no_meta"}, "evt_008"
        )
        sub_repo.call_credit_apply_pack_purchase.assert_not_called()

    @pytest.mark.asyncio
    async def test_duplicate_event_idempotency_delegated_to_rpc(self):
        """Each distinct Stripe event_id is processed; same event_id
        twice in a row goes through the RPC twice but the RPC is
        idempotency-keyed on event_id (unit-level behavior covered by
        the repo tests — here we just confirm the handler forwards
        the event_id verbatim)."""
        from unittest.mock import patch

        user_id = str(uuid4())
        intent = _make_intent(user_id=user_id, credits=25)

        sub_repo = MagicMock()

        with patch("app.api.webhooks.settings") as mock_settings:
            mock_settings.CREDIT_PACK_V1_CREDITS_MILLI = 500
            await _handle_payment_intent_succeeded(sub_repo, intent, "evt_dup")
            await _handle_payment_intent_succeeded(sub_repo, intent, "evt_dup")

        assert sub_repo.call_credit_apply_pack_purchase.call_count == 2
        for call in sub_repo.call_credit_apply_pack_purchase.call_args_list:
            assert call.kwargs["event_id"] == "evt_dup"
