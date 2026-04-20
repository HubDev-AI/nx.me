"""Subscription-lifecycle webhook tests — out-of-order event behavior.

Tests:
- out-of-order subscription.updated (row NOT FOUND) → 500 (Stripe retries)
- second attempt after .created fires successfully
- subscription.deleted writes cancelled_at + status='cancelled' (not 'expired')
- checkout.session.completed (subscription mode) stamps stripe_customer_id
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.webhooks import (
    _handle_checkout_completed,
    _handle_subscription_created,
    _handle_subscription_deleted,
    _handle_subscription_updated,
)

_NOW_TS = int(time.time())


def _make_sub_repo(
    *,
    already_processed: bool = False,
    subscription_row: dict | None = None,
) -> MagicMock:
    repo = MagicMock()
    repo.is_webhook_event_processed.return_value = already_processed
    repo.record_webhook_event.return_value = True
    repo.get_subscription_by_provider_id.return_value = subscription_row
    repo.upsert_subscription.return_value = None
    repo.call_credit_apply_monthly_allotment.return_value = None
    repo.update_subscription_by_provider_id.return_value = None
    repo.stamp_stripe_customer_id.return_value = None
    return repo


def _make_plan_repo(*, plan_version_id: str | None = None) -> MagicMock:
    pid = plan_version_id or str(uuid4())
    repo = MagicMock()
    repo.get_by_version_num.return_value = {
        "id": pid,
        "version_num": "v1_pro",
        "monthly_allotment_milli": 3000,
    }
    return repo


# ---------------------------------------------------------------------------
# Out-of-order: subscription.updated arrives before subscription.created
# ---------------------------------------------------------------------------


class TestOutOfOrderSubscriptionUpdated:
    def test_updated_before_created_returns_500(self):
        """If subscription row is not found, handler raises HTTP 500."""
        sub_repo = _make_sub_repo(subscription_row=None)

        subscription = {
            "id": "sub_oor",
            "cancel_at_period_end": False,
            "current_period_start": _NOW_TS,
            "current_period_end": _NOW_TS + 2592000,
        }
        with pytest.raises(HTTPException) as exc_info:
            _handle_subscription_updated(sub_repo, subscription)

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail["error"]["code"] == "SUBSCRIPTION_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_second_attempt_after_created_succeeds(self):
        """After subscription.created runs, subscription.updated succeeds."""
        user_id = str(uuid4())
        plan_id = str(uuid4())
        sub_id = "sub_oor2"

        # First: create the subscription row.
        sub_repo_create = _make_sub_repo()
        plan_repo = _make_plan_repo(plan_version_id=plan_id)

        subscription_obj: dict[str, Any] = {
            "id": sub_id,
            "metadata": {"user_id": user_id},
            "current_period_start": _NOW_TS,
            "current_period_end": _NOW_TS + 2592000,
        }
        await _handle_subscription_created(sub_repo_create, plan_repo, subscription_obj)
        sub_repo_create.upsert_subscription.assert_called_once()

        # Second: now subscription.updated finds the row (simulate with row present).
        existing_row = {
            "id": "internal_row_id",
            "user_id": user_id,
            "status": "active",
            "grace_until": None,
        }
        sub_repo_update = _make_sub_repo(subscription_row=existing_row)

        update_obj = {
            "id": sub_id,
            "cancel_at_period_end": False,
            "current_period_start": _NOW_TS,
            "current_period_end": _NOW_TS + 2592000,
        }
        # Must not raise.
        _handle_subscription_updated(sub_repo_update, update_obj)
        sub_repo_update.update_subscription_by_provider_id.assert_called_once()

    def test_cancel_at_period_end_sets_cancelled_at(self):
        """cancel_at_period_end=True writes cancelled_at to the subscription row."""
        existing_row = {
            "id": "row_cancel",
            "user_id": str(uuid4()),
            "status": "active",
            "grace_until": None,
        }
        sub_repo = _make_sub_repo(subscription_row=existing_row)

        subscription = {
            "id": "sub_cancel",
            "cancel_at_period_end": True,
            "current_period_start": _NOW_TS,
            "current_period_end": _NOW_TS + 2592000,
        }
        _handle_subscription_updated(sub_repo, subscription)

        sub_repo.update_subscription_by_provider_id.assert_called_once()
        updates = sub_repo.update_subscription_by_provider_id.call_args[0][1]
        assert "cancelled_at" in updates


# ---------------------------------------------------------------------------
# subscription.deleted — writes cancelled_at + status='cancelled'
# ---------------------------------------------------------------------------


class TestSubscriptionDeleted:
    def test_writes_cancelled_at_and_status(self):
        """Deleted subscription gets status='cancelled', not 'expired'."""
        sub_repo = _make_sub_repo()

        _handle_subscription_deleted(sub_repo, {"id": "sub_del"})

        sub_repo.update_subscription_by_provider_id.assert_called_once()
        updates = sub_repo.update_subscription_by_provider_id.call_args[0][1]
        assert updates["status"] == "cancelled"
        assert "cancelled_at" in updates
        # Must NOT write 'expired' (old enum value).
        assert updates["status"] != "expired"

    def test_no_balance_mutation(self):
        """Subscription deletion must not touch the credit ledger."""
        sub_repo = _make_sub_repo()

        _handle_subscription_deleted(sub_repo, {"id": "sub_del2"})

        sub_repo.call_credit_apply_monthly_allotment.assert_not_called()


# ---------------------------------------------------------------------------
# checkout.session.completed — subscription mode stamps stripe_customer_id
# ---------------------------------------------------------------------------


class TestCheckoutSessionCompleted:
    @pytest.mark.asyncio
    async def test_subscription_mode_stamps_customer_id(self):
        user_id = str(uuid4())
        customer_id = "cus_test123"
        sub_repo = _make_sub_repo()

        session = {
            "mode": "subscription",
            "metadata": {"user_id": user_id},
            "customer": customer_id,
        }
        await _handle_checkout_completed(sub_repo, session, "evt_checkout")

        sub_repo.stamp_stripe_customer_id.assert_called_once_with(user_id, customer_id)
        # Subscription row must NOT be written here — subscription.created owns that.
        sub_repo.upsert_subscription.assert_not_called()
        sub_repo.insert_subscription.assert_not_called()

    @pytest.mark.asyncio
    async def test_subscription_mode_missing_user_id_skips(self):
        sub_repo = _make_sub_repo()
        session = {"mode": "subscription", "metadata": {}, "customer": "cus_x"}
        await _handle_checkout_completed(sub_repo, session, "evt_no_uid")
        sub_repo.stamp_stripe_customer_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_subscription_mode_missing_customer_skips_stamp(self):
        """No customer ID in session → stamp not called but handler doesn't raise."""
        user_id = str(uuid4())
        sub_repo = _make_sub_repo()
        session = {
            "mode": "subscription",
            "metadata": {"user_id": user_id},
            "customer": None,
        }
        await _handle_checkout_completed(sub_repo, session, "evt_no_cus")
        sub_repo.stamp_stripe_customer_id.assert_not_called()
