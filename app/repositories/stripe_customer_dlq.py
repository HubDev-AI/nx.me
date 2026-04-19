"""Repository for the ``stripe_customer_dlq`` table.

Rows are written when ``delete_customer`` fails during account deletion.
A nightly reconciler (``app/workers/stripe_customer_dlq_reconciler.py``) drains
the queue, calling ``delete_customer`` again with exponential back-off awareness
(attempts counter + WARN ceiling).

See migration ``0053_stripe_customer_dlq.sql``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from supabase import Client

logger = logging.getLogger(__name__)


class StripeCustomerDLQRepository:
    """Thin wrapper around the ``stripe_customer_dlq`` table."""

    def __init__(self, sb: Client) -> None:
        self._sb = sb

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record(
        self,
        customer_id: str,
        reason: str,
        last_error: str | None = None,
    ) -> None:
        """Upsert a DLQ row for ``customer_id``.

        Safe to call from inline exception handlers — duplicate inserts update
        ``last_error`` and ``updated_at`` rather than raising. Never propagates
        exceptions so a DLQ-write failure cannot mask the primary delete error.
        """
        now = datetime.now(tz=timezone.utc).isoformat()
        try:
            (
                self._sb.table("stripe_customer_dlq")
                .upsert(
                    {
                        "customer_id": customer_id,
                        "reason": reason,
                        "last_error": last_error,
                        "updated_at": now,
                    },
                    on_conflict="customer_id",
                )
                .execute()
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to record stripe_customer_dlq row for customer=%s — "
                "row may be missing until next reconciler run",
                customer_id,
            )

    # ------------------------------------------------------------------
    # Read (reconciler)
    # ------------------------------------------------------------------

    def list_drainable(self, limit: int = 100) -> list[dict]:
        """Return up to ``limit`` DLQ rows ordered by (attempts ASC, inserted_at ASC)."""
        result = (
            self._sb.table("stripe_customer_dlq")
            .select("id, customer_id, reason, attempts, last_error, inserted_at")
            .order("attempts", desc=False)
            .order("inserted_at", desc=False)
            .limit(limit)
            .execute()
        )
        return result.data or []

    # ------------------------------------------------------------------
    # Update / delete
    # ------------------------------------------------------------------

    def mark_attempt(self, customer_id: str, last_error: str | None = None) -> None:
        """Increment ``attempts`` and refresh ``last_error`` / ``updated_at``."""
        now = datetime.now(tz=timezone.utc).isoformat()
        current = (
            self._sb.table("stripe_customer_dlq")
            .select("attempts")
            .eq("customer_id", customer_id)
            .maybe_single()
            .execute()
        )
        if not current or not current.data:
            return
        next_attempts = int(current.data.get("attempts", 0)) + 1
        (
            self._sb.table("stripe_customer_dlq")
            .update(
                {
                    "attempts": next_attempts,
                    "last_error": last_error,
                    "updated_at": now,
                }
            )
            .eq("customer_id", customer_id)
            .execute()
        )

    def delete(self, customer_id: str) -> None:
        """Remove a DLQ row once the Stripe delete succeeded."""
        (
            self._sb.table("stripe_customer_dlq")
            .delete()
            .eq("customer_id", customer_id)
            .execute()
        )
