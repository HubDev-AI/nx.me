"""Tests for dispute + refund webhook handlers — Unit 8b.

Exercises production code in:
  - app/api/webhooks.py (_handle_dispute_event, _handle_dispute_closed,
    _handle_charge_refunded, _resolve_dispute_user_id)
  - app/repositories/subscription_repo.py (call_apply_dispute_event,
    call_credit_dispute_compensate, record_refund_compensating_entry)
  - app/repositories/user_repo.py (find_by_stripe_customer_id)

Scenarios (per plan lines 768-777):
  Happy path — charge.dispute.created → apply_dispute_event sets locked_at
  Happy path — charge.dispute.closed (won) → apply_dispute_event clears locked_at
  Happy path — charge.dispute.closed (lost) → negative compensating entry; locked_at persists
  Happy path — charge.dispute.funds_withdrawn → audit-only, no lock change
  Happy path — charge.refunded → compensating entry written
  Edge — out-of-order dispute: out_of_order result → handler raises 500
  Edge — duplicate event_id (reason='duplicate') → treated as success (no 500)
  Edge — missing customer → skipped
  Edge — unknown customer → skipped
  Edge — dispute.closed with non-won/lost status → treated as closed_won
  Integration — full lifecycle created → closed_won
  Integration — full lifecycle created → closed_lost → compensating entry
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException


try:
    from app.api.webhooks import (
        _handle_charge_refunded,
        _handle_dispute_closed,
        _handle_dispute_event,
    )
    from app.constants.webhooks import (
        DISPUTE_EVENT_CLOSED_LOST,
        DISPUTE_EVENT_CLOSED_WON,
        DISPUTE_EVENT_CREATED,
        DISPUTE_EVENT_FUNDS_WITHDRAWN,
    )

    _WEBHOOKS_AVAILABLE = True
except (ImportError, AttributeError):
    _WEBHOOKS_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _WEBHOOKS_AVAILABLE, reason="webhooks module unavailable"
)

_NOW_TS = int(time.time())
_FIXED_CREDITS_MILLI = 500


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user_repo(user_id: str | None = None) -> MagicMock:
    repo = MagicMock()
    if user_id is not None:
        repo.find_by_stripe_customer_id.return_value = {"id": user_id}
    else:
        repo.find_by_stripe_customer_id.return_value = None
    return repo


def _make_sub_repo(
    applied: bool = True,
    reason: str | None = None,
    locked_at: str | None = None,
) -> MagicMock:
    repo = MagicMock()
    repo.call_apply_dispute_event.return_value = {
        "applied": applied,
        "reason": reason,
        "new_status": DISPUTE_EVENT_CREATED,
        "locked_at": locked_at,
    }
    return repo


def _make_dispute(
    *,
    customer: str = "cus_test",
    charge: str = "ch_test",
    created: int | None = None,
    status: str = "needs_response",
) -> dict:
    return {
        "id": "dp_test",
        "customer": customer,
        "charge": charge,
        "created": created if created is not None else _NOW_TS,
        "status": status,
    }


# ---------------------------------------------------------------------------
# _handle_dispute_event tests
# ---------------------------------------------------------------------------


class TestHandleDisputeEvent:
    def test_created_calls_apply_dispute_event(self):
        user_id = str(uuid4())
        event_id = "evt_disp_001"
        dispute = _make_dispute(customer="cus_abc")
        user_repo = _make_user_repo(user_id)
        sub_repo = _make_sub_repo(applied=True)

        _handle_dispute_event(
            sub_repo, user_repo, dispute, event_id, DISPUTE_EVENT_CREATED
        )

        sub_repo.call_apply_dispute_event.assert_called_once()
        kwargs = sub_repo.call_apply_dispute_event.call_args.kwargs
        assert kwargs["user_id"] == user_id
        assert kwargs["event_id"] == event_id
        assert kwargs["new_status"] == DISPUTE_EVENT_CREATED

    def test_out_of_order_raises_http_500(self):
        user_id = str(uuid4())
        dispute = _make_dispute()
        user_repo = _make_user_repo(user_id)
        sub_repo = _make_sub_repo(applied=False, reason="out_of_order")

        with pytest.raises(HTTPException) as exc_info:
            _handle_dispute_event(
                sub_repo, user_repo, dispute, "evt_oor_001", DISPUTE_EVENT_CLOSED_WON
            )

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail["error"]["code"] == "DISPUTE_OUT_OF_ORDER"

    def test_duplicate_event_id_does_not_raise(self):
        """reason='duplicate' means Stripe redelivered the same event — treat as success."""
        user_id = str(uuid4())
        dispute = _make_dispute()
        user_repo = _make_user_repo(user_id)
        sub_repo = _make_sub_repo(applied=False, reason="duplicate")

        # Should not raise — duplicate is a no-op success path.
        _handle_dispute_event(
            sub_repo, user_repo, dispute, "evt_dup_disp", DISPUTE_EVENT_CREATED
        )

        sub_repo.call_apply_dispute_event.assert_called_once()

    def test_missing_customer_is_skipped(self):
        dispute = _make_dispute()
        dispute["customer"] = None
        user_repo = _make_user_repo(None)
        sub_repo = MagicMock()

        _handle_dispute_event(
            sub_repo, user_repo, dispute, "evt_no_cust", DISPUTE_EVENT_CREATED
        )

        sub_repo.call_apply_dispute_event.assert_not_called()

    def test_unknown_customer_is_skipped(self):
        dispute = _make_dispute(customer="cus_unknown")
        user_repo = _make_user_repo(None)  # returns None → user not found
        sub_repo = MagicMock()

        _handle_dispute_event(
            sub_repo, user_repo, dispute, "evt_unknown_cust", DISPUTE_EVENT_CREATED
        )

        sub_repo.call_apply_dispute_event.assert_not_called()

    def test_missing_created_timestamp_is_skipped(self):
        user_id = str(uuid4())
        dispute = _make_dispute()
        dispute["created"] = None
        user_repo = _make_user_repo(user_id)
        sub_repo = MagicMock()

        _handle_dispute_event(
            sub_repo, user_repo, dispute, "evt_no_ts", DISPUTE_EVENT_CREATED
        )

        sub_repo.call_apply_dispute_event.assert_not_called()

    def test_funds_withdrawn_calls_apply_with_correct_status(self):
        user_id = str(uuid4())
        dispute = _make_dispute()
        user_repo = _make_user_repo(user_id)
        sub_repo = _make_sub_repo(applied=True)

        _handle_dispute_event(
            sub_repo, user_repo, dispute, "evt_fw_001", DISPUTE_EVENT_FUNDS_WITHDRAWN
        )

        kwargs = sub_repo.call_apply_dispute_event.call_args.kwargs
        assert kwargs["new_status"] == DISPUTE_EVENT_FUNDS_WITHDRAWN


# ---------------------------------------------------------------------------
# _handle_dispute_closed tests
# ---------------------------------------------------------------------------


class TestHandleDisputeClosed:
    def test_closed_won_maps_to_closed_won(self):
        user_id = str(uuid4())
        dispute = _make_dispute(status="won")
        user_repo = _make_user_repo(user_id)
        sub_repo = _make_sub_repo(applied=True)

        _handle_dispute_closed(sub_repo, user_repo, dispute, "evt_won_001")

        kwargs = sub_repo.call_apply_dispute_event.call_args.kwargs
        assert kwargs["new_status"] == DISPUTE_EVENT_CLOSED_WON
        # No compensating entry for won disputes
        sub_repo.call_credit_dispute_compensate.assert_not_called()

    def test_closed_lost_maps_to_closed_lost_and_compensates(self):
        user_id = str(uuid4())
        charge_id = "ch_lost_001"
        dispute = _make_dispute(status="lost", charge=charge_id)
        user_repo = _make_user_repo(user_id)
        sub_repo = _make_sub_repo(applied=True)

        with patch("app.api.webhooks.settings") as mock_settings:
            mock_settings.MONTHLY_ALLOTMENT_MILLI = _FIXED_CREDITS_MILLI
            _handle_dispute_closed(sub_repo, user_repo, dispute, "evt_lost_001")

        kwargs = sub_repo.call_apply_dispute_event.call_args.kwargs
        assert kwargs["new_status"] == DISPUTE_EVENT_CLOSED_LOST

        sub_repo.call_credit_dispute_compensate.assert_called_once_with(
            user_id=user_id,
            charge_id=charge_id,
            amount_milli=_FIXED_CREDITS_MILLI,
        )

    def test_warning_closed_treated_as_won(self):
        user_id = str(uuid4())
        dispute = _make_dispute(status="warning_closed")
        user_repo = _make_user_repo(user_id)
        sub_repo = _make_sub_repo(applied=True)

        _handle_dispute_closed(sub_repo, user_repo, dispute, "evt_warn_001")

        kwargs = sub_repo.call_apply_dispute_event.call_args.kwargs
        assert kwargs["new_status"] == DISPUTE_EVENT_CLOSED_WON
        sub_repo.call_credit_dispute_compensate.assert_not_called()

    def test_unknown_status_treated_as_won(self):
        user_id = str(uuid4())
        dispute = _make_dispute(status="unknown_future_status")
        user_repo = _make_user_repo(user_id)
        sub_repo = _make_sub_repo(applied=True)

        _handle_dispute_closed(sub_repo, user_repo, dispute, "evt_unknown_status")

        kwargs = sub_repo.call_apply_dispute_event.call_args.kwargs
        assert kwargs["new_status"] == DISPUTE_EVENT_CLOSED_WON

    def test_out_of_order_closed_raises_500(self):
        user_id = str(uuid4())
        dispute = _make_dispute(status="won")
        user_repo = _make_user_repo(user_id)
        sub_repo = _make_sub_repo(applied=False, reason="out_of_order")

        with pytest.raises(HTTPException) as exc_info:
            _handle_dispute_closed(sub_repo, user_repo, dispute, "evt_oor_closed")

        assert exc_info.value.status_code == 500
        # No compensating entry should be written when the state transition fails
        sub_repo.call_credit_dispute_compensate.assert_not_called()

    def test_closed_lost_no_compensate_when_out_of_order(self):
        """If the CAS state transition fails (out-of-order), no compensating entry."""
        user_id = str(uuid4())
        dispute = _make_dispute(status="lost")
        user_repo = _make_user_repo(user_id)
        sub_repo = _make_sub_repo(applied=False, reason="out_of_order")

        with pytest.raises(HTTPException):
            _handle_dispute_closed(sub_repo, user_repo, dispute, "evt_lost_oor")

        sub_repo.call_credit_dispute_compensate.assert_not_called()


# ---------------------------------------------------------------------------
# _handle_charge_refunded tests
# ---------------------------------------------------------------------------


class TestHandleChargeRefunded:
    def test_refund_writes_compensating_entry(self):
        user_id = str(uuid4())
        charge_id = "ch_refund_001"
        charge = {"id": charge_id, "customer": "cus_refund", "amount_refunded": 999}
        user_repo = _make_user_repo(user_id)
        sub_repo = MagicMock()

        with patch("app.api.webhooks.settings") as mock_settings:
            mock_settings.MONTHLY_ALLOTMENT_MILLI = _FIXED_CREDITS_MILLI
            _handle_charge_refunded(sub_repo, user_repo, charge, "evt_refund_001")

        sub_repo.record_refund_compensating_entry.assert_called_once_with(
            user_id=user_id,
            charge_id=charge_id,
            amount_milli=_FIXED_CREDITS_MILLI,
        )

    def test_missing_customer_is_skipped(self):
        charge = {"id": "ch_test", "customer": None}
        user_repo = MagicMock()
        sub_repo = MagicMock()

        _handle_charge_refunded(sub_repo, user_repo, charge, "evt_refund_no_cust")

        sub_repo.record_refund_compensating_entry.assert_not_called()
        user_repo.find_by_stripe_customer_id.assert_not_called()

    def test_unknown_customer_is_skipped(self):
        charge = {"id": "ch_test", "customer": "cus_ghost"}
        user_repo = _make_user_repo(None)
        sub_repo = MagicMock()

        _handle_charge_refunded(sub_repo, user_repo, charge, "evt_refund_ghost")

        sub_repo.record_refund_compensating_entry.assert_not_called()


# ---------------------------------------------------------------------------
# Integration — full dispute lifecycle (unit-level, mocked DB)
# ---------------------------------------------------------------------------


class TestDisputeLifecycleIntegration:
    def test_created_then_closed_won_lifecycle(self):
        """Full happy path: created → closed_won.

        After closed_won the compensating entry is NOT written, confirming
        the account is effectively unlocked (locked_at=NULL on apply_dispute_event).
        """
        user_id = str(uuid4())
        customer_id = "cus_lifecycle"
        charge_id = "ch_lifecycle"

        user_repo = _make_user_repo(user_id)
        sub_repo = MagicMock()
        sub_repo.call_apply_dispute_event.return_value = {
            "applied": True,
            "reason": None,
            "new_status": DISPUTE_EVENT_CREATED,
            "locked_at": "2026-04-19T00:00:00+00:00",
        }

        dispute_created = {
            "id": "dp_lifecycle",
            "customer": customer_id,
            "charge": charge_id,
            "created": _NOW_TS,
            "status": "needs_response",
        }

        # Step 1: dispute.created
        _handle_dispute_event(
            sub_repo,
            user_repo,
            dispute_created,
            "evt_lc_created",
            DISPUTE_EVENT_CREATED,
        )
        assert sub_repo.call_apply_dispute_event.call_count == 1

        # Step 2: dispute.closed (won) — higher timestamp
        sub_repo.call_apply_dispute_event.return_value = {
            "applied": True,
            "reason": None,
            "new_status": DISPUTE_EVENT_CLOSED_WON,
            "locked_at": None,  # cleared by RPC
        }
        dispute_closed_won = {
            **dispute_created,
            "created": _NOW_TS + 60,
            "status": "won",
        }
        _handle_dispute_closed(
            sub_repo, user_repo, dispute_closed_won, "evt_lc_closed_won"
        )

        assert sub_repo.call_apply_dispute_event.call_count == 2
        last_call = sub_repo.call_apply_dispute_event.call_args.kwargs
        assert last_call["new_status"] == DISPUTE_EVENT_CLOSED_WON
        # No compensating entry for won
        sub_repo.call_credit_dispute_compensate.assert_not_called()

    def test_created_then_closed_lost_lifecycle(self):
        """Full path: created → closed_lost.

        locked_at stays set; compensating entry is written.
        """
        user_id = str(uuid4())
        customer_id = "cus_lost"
        charge_id = "ch_lost"

        user_repo = _make_user_repo(user_id)
        sub_repo = MagicMock()

        sub_repo.call_apply_dispute_event.return_value = {
            "applied": True,
            "reason": None,
            "new_status": DISPUTE_EVENT_CREATED,
            "locked_at": "2026-04-19T00:00:00+00:00",
        }

        dispute = {
            "id": "dp_lost",
            "customer": customer_id,
            "charge": charge_id,
            "created": _NOW_TS,
            "status": "needs_response",
        }

        # Step 1: created
        _handle_dispute_event(
            sub_repo, user_repo, dispute, "evt_lost_created", DISPUTE_EVENT_CREATED
        )

        # Step 2: closed (lost)
        sub_repo.call_apply_dispute_event.return_value = {
            "applied": True,
            "reason": None,
            "new_status": DISPUTE_EVENT_CLOSED_LOST,
            "locked_at": "2026-04-19T00:00:00+00:00",  # stays set
        }
        dispute_closed = {**dispute, "created": _NOW_TS + 60, "status": "lost"}

        with patch("app.api.webhooks.settings") as mock_settings:
            mock_settings.MONTHLY_ALLOTMENT_MILLI = _FIXED_CREDITS_MILLI
            _handle_dispute_closed(
                sub_repo, user_repo, dispute_closed, "evt_lost_closed"
            )

        # Both state transitions applied
        assert sub_repo.call_apply_dispute_event.call_count == 2

        # Compensating entry written after closed_lost
        sub_repo.call_credit_dispute_compensate.assert_called_once_with(
            user_id=user_id,
            charge_id=charge_id,
            amount_milli=_FIXED_CREDITS_MILLI,
        )

    def test_out_of_order_closed_before_created(self):
        """Edge: closed arrives before created (out-of-order).

        The first apply returns out_of_order → handler raises 500.
        Stripe retries; eventually created arrives first, then closed re-delivers.
        """
        user_id = str(uuid4())
        dispute = {
            "id": "dp_oor",
            "customer": "cus_oor",
            "charge": "ch_oor",
            "created": _NOW_TS,
            "status": "won",
        }
        user_repo = _make_user_repo(user_id)
        sub_repo = _make_sub_repo(applied=False, reason="out_of_order")

        with pytest.raises(HTTPException) as exc_info:
            _handle_dispute_closed(sub_repo, user_repo, dispute, "evt_oor_closed")

        assert exc_info.value.status_code == 500
