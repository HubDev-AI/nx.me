"""Tests for ``app.workers.stripe_customer_dlq_reconciler.reconcile_stripe_customer_dlq``.

Covers:
  - Happy path: row with delete_customer success → row deleted.
  - Edge: row with resource_missing → row deleted (idempotent success).
  - Edge: row with other failure → attempts++; attempts > 5 logs WARN.
  - Edge: empty DLQ — worker completes without error.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers.stripe_customer_dlq_reconciler import (
    reconcile_stripe_customer_dlq,
    _DLQ_MAX_ATTEMPTS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CUSTOMER_ID = "cus_test_123"


def _make_row(customer_id: str = _CUSTOMER_ID, attempts: int = 0) -> dict:
    return {
        "id": "row-uuid",
        "customer_id": customer_id,
        "reason": "delete_account",
        "attempts": attempts,
        "last_error": None,
        "inserted_at": "2026-04-01T00:00:00+00:00",
    }


def _make_ctx(rows: list[dict], delete_raises: Exception | None = None) -> dict:
    """Build a minimal ARQ ctx with mocked payment and supabase."""
    payment = MagicMock()
    if delete_raises:
        payment.delete_customer = AsyncMock(side_effect=delete_raises)
    else:
        payment.delete_customer = AsyncMock(return_value=None)

    supabase = MagicMock()
    return {"payment": payment, "supabase": supabase, "_rows": rows}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestReconcileStripeCustomerDLQ:
    @pytest.mark.asyncio
    async def test_success_deletes_row(self):
        """Successful delete_customer must remove the DLQ row."""
        row = _make_row()
        ctx = _make_ctx([row])

        with patch(
            "app.workers.stripe_customer_dlq_reconciler.StripeCustomerDLQRepository"
        ) as MockRepo:
            MockRepo.return_value.list_drainable.return_value = [row]
            await reconcile_stripe_customer_dlq(ctx)

        MockRepo.return_value.delete.assert_called_once_with(_CUSTOMER_ID)
        MockRepo.return_value.mark_attempt.assert_not_called()

    @pytest.mark.asyncio
    async def test_resource_missing_treated_as_success(self):
        """resource_missing error from Stripe must remove the DLQ row (idempotent)."""
        row = _make_row()
        ctx = _make_ctx([row], delete_raises=RuntimeError("resource_missing"))

        with patch(
            "app.workers.stripe_customer_dlq_reconciler.StripeCustomerDLQRepository"
        ) as MockRepo:
            MockRepo.return_value.list_drainable.return_value = [row]
            await reconcile_stripe_customer_dlq(ctx)

        MockRepo.return_value.delete.assert_called_once_with(_CUSTOMER_ID)
        MockRepo.return_value.mark_attempt.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_dlq_completes_cleanly(self, caplog):
        """Empty DLQ must complete without any errors or warnings."""
        ctx = _make_ctx([])

        with patch(
            "app.workers.stripe_customer_dlq_reconciler.StripeCustomerDLQRepository"
        ) as MockRepo:
            MockRepo.return_value.list_drainable.return_value = []
            with caplog.at_level(
                logging.WARNING, logger="app.workers.stripe_customer_dlq_reconciler"
            ):
                await reconcile_stripe_customer_dlq(ctx)

        assert not any(r.levelno >= logging.WARNING for r in caplog.records)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestReconcileStripeCustomerDLQEdges:
    @pytest.mark.asyncio
    async def test_other_failure_increments_attempts(self):
        """Non-resource_missing error must call mark_attempt."""
        row = _make_row(attempts=1)
        ctx = _make_ctx([row], delete_raises=RuntimeError("network timeout"))

        with patch(
            "app.workers.stripe_customer_dlq_reconciler.StripeCustomerDLQRepository"
        ) as MockRepo:
            MockRepo.return_value.list_drainable.return_value = [row]
            await reconcile_stripe_customer_dlq(ctx)

        MockRepo.return_value.mark_attempt.assert_called_once_with(
            _CUSTOMER_ID, last_error="network timeout"
        )
        MockRepo.return_value.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_attempts_exceeding_max_logs_warning(self, caplog):
        """When new attempts > _DLQ_MAX_ATTEMPTS a WARNING must be emitted."""
        # Start at max attempts so the next failure crosses the threshold.
        row = _make_row(attempts=_DLQ_MAX_ATTEMPTS)
        ctx = _make_ctx([row], delete_raises=RuntimeError("stripe down"))

        with patch(
            "app.workers.stripe_customer_dlq_reconciler.StripeCustomerDLQRepository"
        ) as MockRepo:
            MockRepo.return_value.list_drainable.return_value = [row]
            with caplog.at_level(
                logging.WARNING, logger="app.workers.stripe_customer_dlq_reconciler"
            ):
                await reconcile_stripe_customer_dlq(ctx)

        assert any(
            r.levelno == logging.WARNING and "manual intervention" in r.message
            for r in caplog.records
        )

    @pytest.mark.asyncio
    async def test_attempts_below_max_does_not_warn(self, caplog):
        """Failures below the attempt ceiling must NOT emit a WARNING."""
        row = _make_row(attempts=0)
        ctx = _make_ctx([row], delete_raises=RuntimeError("timeout"))

        with patch(
            "app.workers.stripe_customer_dlq_reconciler.StripeCustomerDLQRepository"
        ) as MockRepo:
            MockRepo.return_value.list_drainable.return_value = [row]
            with caplog.at_level(
                logging.WARNING, logger="app.workers.stripe_customer_dlq_reconciler"
            ):
                await reconcile_stripe_customer_dlq(ctx)

        assert not any(
            r.levelno == logging.WARNING and "manual intervention" in r.message
            for r in caplog.records
        )
