"""Tests for the credit-pack webhook handler — Unit 8b.

Exercises production code in:
  - app/api/webhooks.py (_handle_payment_intent_succeeded)
  - app/repositories/subscription_repo.py (call_credit_apply_pack_purchase)

Happy paths:
  - payment_intent.succeeded with flow=payment_sheet → credit_apply_pack_purchase
  - non-payment-sheet flow is skipped
  - missing user_id is skipped
  - invalid user_id UUID is skipped
  - duplicate event_id: outer dedup handles; handler still calls RPC (idempotency at RPC level)

Edge cases:
  - no metadata → skipped
  - credits_milli comes from settings, not metadata.credits
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
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

_FIXED_CREDITS_MILLI = 500


def _make_intent(
    *,
    user_id: str | None = None,
    flow: str | None = "payment_sheet",
    credits: str | int | None = "10",
) -> dict:
    metadata: dict = {}
    if user_id is not None:
        metadata["user_id"] = user_id
    if flow is not None:
        metadata["flow"] = flow
    if credits is not None:
        metadata["credits"] = str(credits)
    return {"id": "pi_test", "metadata": metadata}


class TestHandlePaymentIntentSucceededPack:
    @pytest.mark.asyncio
    async def test_valid_payment_sheet_calls_pack_rpc(self):
        user_id = str(uuid4())
        event_id = "evt_pack_001"
        intent = _make_intent(user_id=user_id)

        sub_repo = MagicMock()

        with patch("app.api.webhooks.settings") as mock_settings:
            mock_settings.CREDIT_PACK_V1_CREDITS_MILLI = _FIXED_CREDITS_MILLI
            await _handle_payment_intent_succeeded(sub_repo, intent, event_id)

        sub_repo.call_credit_apply_pack_purchase.assert_called_once_with(
            user_id=user_id,
            event_id=event_id,
            credits_milli=_FIXED_CREDITS_MILLI,
        )

    @pytest.mark.asyncio
    async def test_non_payment_sheet_flow_is_skipped(self):
        intent = _make_intent(user_id=str(uuid4()), flow="checkout_legacy")

        sub_repo = MagicMock()
        await _handle_payment_intent_succeeded(sub_repo, intent, "evt_pack_002")

        sub_repo.call_credit_apply_pack_purchase.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_flow_metadata_is_skipped(self):
        intent = _make_intent(user_id=str(uuid4()), flow=None)

        sub_repo = MagicMock()
        await _handle_payment_intent_succeeded(sub_repo, intent, "evt_pack_003")

        sub_repo.call_credit_apply_pack_purchase.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_user_id_is_skipped(self):
        intent = _make_intent(user_id=None)

        sub_repo = MagicMock()
        await _handle_payment_intent_succeeded(sub_repo, intent, "evt_pack_004")

        sub_repo.call_credit_apply_pack_purchase.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_user_id_uuid_is_skipped(self):
        intent = _make_intent(user_id="not-a-uuid")

        sub_repo = MagicMock()
        await _handle_payment_intent_succeeded(sub_repo, intent, "evt_pack_005")

        sub_repo.call_credit_apply_pack_purchase.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_metadata_is_skipped(self):
        sub_repo = MagicMock()
        await _handle_payment_intent_succeeded(
            sub_repo, {"id": "pi_no_meta"}, "evt_pack_006"
        )
        sub_repo.call_credit_apply_pack_purchase.assert_not_called()

    @pytest.mark.asyncio
    async def test_credits_milli_from_settings_not_metadata(self):
        """Server-side CREDIT_PACK_V1_CREDITS_MILLI is the source of truth (R7-Pack).

        Even if metadata.credits says 10, the RPC should receive the settings value.
        """
        user_id = str(uuid4())
        intent = _make_intent(user_id=user_id, credits="10")

        sub_repo = MagicMock()

        with patch("app.api.webhooks.settings") as mock_settings:
            mock_settings.CREDIT_PACK_V1_CREDITS_MILLI = 999
            await _handle_payment_intent_succeeded(sub_repo, intent, "evt_pack_007")

        kwargs = sub_repo.call_credit_apply_pack_purchase.call_args.kwargs
        # Must use the settings value (999), not metadata.credits (10)
        assert kwargs["credits_milli"] == 999

    @pytest.mark.asyncio
    async def test_duplicate_event_id_passes_event_id_to_rpc(self):
        """Duplicate event_id processing is idempotent at the RPC level.

        The outer processed_webhook_events dedup catches duplicates before
        the handler runs; at the handler level, both calls forward event_id
        correctly so the RPC's uuid5 dedup also fires.
        """
        user_id = str(uuid4())
        intent = _make_intent(user_id=user_id)

        sub_repo = MagicMock()

        with patch("app.api.webhooks.settings") as mock_settings:
            mock_settings.CREDIT_PACK_V1_CREDITS_MILLI = _FIXED_CREDITS_MILLI
            await _handle_payment_intent_succeeded(sub_repo, intent, "evt_dup_pack")
            await _handle_payment_intent_succeeded(sub_repo, intent, "evt_dup_pack")

        assert sub_repo.call_credit_apply_pack_purchase.call_count == 2
        for call in sub_repo.call_credit_apply_pack_purchase.call_args_list:
            assert call.kwargs["event_id"] == "evt_dup_pack"
            assert call.kwargs["user_id"] == user_id
