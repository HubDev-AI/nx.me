"""Nightly worker — reconcile the ``stripe_customer_dlq`` table.

Scheduled cron: daily 04:00 UTC.

Iterates rows that failed ``delete_customer`` during account deletion and retries
them. Rows where ``resource_missing`` is returned from Stripe are treated as
success (the customer is already gone). After ``_DLQ_MAX_ATTEMPTS`` failures a
WARNING is emitted so ops can investigate manually.

Pattern mirrors ``app/workers/orphan_reclaim.py``.
"""

from __future__ import annotations

import logging

from app.repositories.stripe_customer_dlq import StripeCustomerDLQRepository

logger = logging.getLogger(__name__)

# Emit a WARNING log when a row exceeds this many failed attempts.
_DLQ_MAX_ATTEMPTS = 5

# Cron schedule constants (registered in app/worker_settings.py).
# Daily 04:00 UTC.
STRIPE_CUSTOMER_DLQ_CRON_HOUR = 4
STRIPE_CUSTOMER_DLQ_CRON_MINUTE = 0


async def reconcile_stripe_customer_dlq(ctx: dict) -> None:
    """ARQ cron task: drain the Stripe customer DLQ.

    For each row:
    - Calls ``payment.delete_customer(customer_id)``.
    - ``resource_missing`` (idempotent Stripe response) → delete the row.
    - Any other success → delete the row.
    - Any other failure → ``mark_attempt``; if new attempts > ``_DLQ_MAX_ATTEMPTS``
      emit a WARNING for ops visibility.
    """
    from app.payment.ports import PaymentPort

    payment: PaymentPort = ctx["payment"]
    supabase = ctx["supabase"]
    repo = StripeCustomerDLQRepository(supabase)

    rows = repo.list_drainable(100)
    logger.info("reconcile_stripe_customer_dlq: starting — %d rows to drain", len(rows))

    succeeded = 0
    failed = 0

    for row in rows:
        customer_id: str = row["customer_id"]
        attempts: int = row.get("attempts", 0)

        try:
            await payment.delete_customer(customer_id)
            repo.delete(customer_id)
            succeeded += 1
        except Exception as exc:  # noqa: BLE001
            err_str = str(exc)
            # resource_missing means Stripe already deleted the customer — treat as success.
            if "resource_missing" in err_str:
                logger.info(
                    "reconcile_stripe_customer_dlq: customer=%s already deleted "
                    "(resource_missing) — removing DLQ row",
                    customer_id,
                )
                repo.delete(customer_id)
                succeeded += 1
                continue

            new_attempts = attempts + 1
            repo.mark_attempt(customer_id, last_error=err_str)
            failed += 1

            if new_attempts > _DLQ_MAX_ATTEMPTS:
                logger.warning(
                    "reconcile_stripe_customer_dlq: customer=%s has failed %d times "
                    "(threshold=%d) — manual intervention may be required; last_error=%s",
                    customer_id,
                    new_attempts,
                    _DLQ_MAX_ATTEMPTS,
                    err_str,
                )
            else:
                logger.info(
                    "reconcile_stripe_customer_dlq: customer=%s attempt %d failed: %s",
                    customer_id,
                    new_attempts,
                    err_str,
                )

    logger.info(
        "reconcile_stripe_customer_dlq: done — succeeded=%d failed=%d",
        succeeded,
        failed,
    )
