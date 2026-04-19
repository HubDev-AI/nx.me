"""Subscription repository — all subscriptions and processed_webhook_events queries.

Follows the same pattern as UserRepository: constructor takes a Client,
methods are synchronous (callers use run_sync for async handlers).
"""

from __future__ import annotations

import logging
from uuid import uuid5, NAMESPACE_URL

from supabase import Client

logger = logging.getLogger(__name__)


class SubscriptionRepository:
    """Encapsulates all DB calls related to subscriptions and webhook dedup."""

    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    # ------------------------------------------------------------------
    # subscriptions table — reads
    # ------------------------------------------------------------------

    def get_active_subscription(self, user_id: str) -> dict | None:
        """Return the active subscription for a user, or None."""
        result = (
            self._sb.table("subscriptions")
            .select("provider_subscription_id, status")
            .eq("user_id", user_id)
            .eq("status", "active")
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    def get_subscription_user_id(self, provider_subscription_id: str) -> str | None:
        """Return the user_id for a subscription by provider ID, or None."""
        result = (
            self._sb.table("subscriptions")
            .select("user_id")
            .eq("provider_subscription_id", provider_subscription_id)
            .maybe_single()
            .execute()
        )
        if not result or not result.data:
            return None
        return result.data["user_id"]

    # ------------------------------------------------------------------
    # subscriptions table — writes
    # ------------------------------------------------------------------

    def get_subscription_by_provider_id(
        self, provider_subscription_id: str
    ) -> dict | None:
        """Return the subscription row for a provider ID, or None if not found."""
        result = (
            self._sb.table("subscriptions")
            .select("id, user_id, status, grace_until")
            .eq("provider_subscription_id", provider_subscription_id)
            .maybe_single()
            .execute()
        )
        if not result or not result.data:
            return None
        return result.data

    def insert_subscription(self, row: dict) -> None:
        """Insert a new subscription row."""
        self._sb.table("subscriptions").insert(row).execute()

    def upsert_subscription(self, row: dict) -> None:
        """Upsert a subscription row keyed on provider_subscription_id."""
        self._sb.table("subscriptions").upsert(
            row, on_conflict="provider_subscription_id"
        ).execute()

    def stamp_stripe_customer_id(self, user_id: str, customer_id: str) -> None:
        """Write users.stripe_customer_id for a user (best-effort; logs on failure)."""
        try:
            self._sb.table("users").update({"stripe_customer_id": customer_id}).eq(
                "id", user_id
            ).execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to stamp stripe_customer_id for user=%s: %s", user_id, exc
            )

    def call_credit_apply_monthly_allotment(
        self, user_id: str, plan_version_id: str
    ) -> None:
        """Invoke the credit_apply_monthly_allotment DB RPC (REPLACE semantics)."""
        self._sb.rpc(
            "credit_apply_monthly_allotment",
            {
                "p_user_id": user_id,
                "p_plan_version_id": plan_version_id,
            },
        ).execute()

    def update_subscription_by_provider_id(
        self,
        provider_subscription_id: str,
        updates: dict,
    ) -> None:
        """Apply field updates to a subscription row identified by provider ID."""
        result = (
            self._sb.table("subscriptions")
            .update(updates)
            .eq("provider_subscription_id", provider_subscription_id)
            .execute()
        )
        if not result.data:
            logger.warning(
                "Subscription update affected 0 rows for provider_subscription_id=%s",
                provider_subscription_id,
            )

    # ------------------------------------------------------------------
    # processed_webhook_events table
    # ------------------------------------------------------------------

    def is_webhook_event_processed(self, provider: str, event_id: str) -> bool:
        """Check if a webhook event has already been processed (read-only)."""
        result = (
            self._sb.table("processed_webhook_events")
            .select("id")
            .eq("provider", provider)
            .eq("event_id", event_id)
            .limit(1)
            .execute()
        )
        return bool(result.data)

    def record_webhook_event(self, provider: str, event_id: str) -> bool:
        """Record a processed webhook event, returning True if this is the first time.

        Uses upsert with ``ignore_duplicates=True`` so concurrent duplicate
        webhooks don't both pass the existence check (M-15).  The caller
        should treat a ``False`` return as "already processed — skip".
        """
        result = (
            self._sb.table("processed_webhook_events")
            .upsert(
                {"provider": provider, "event_id": event_id},
                on_conflict="event_id",
                ignore_duplicates=True,
            )
            .execute()
        )
        # When ignore_duplicates=True and the row already existed, Supabase
        # returns an empty data list.  A non-empty list means this was a fresh insert.
        return bool(result.data)

    # ------------------------------------------------------------------
    # RPC — credit-pack purchase (Unit 8b)
    # ------------------------------------------------------------------

    def call_credit_apply_pack_purchase(
        self, user_id: str, event_id: str, credits_milli: int
    ) -> None:
        """Invoke credit_apply_pack_purchase DB RPC (idempotent via uuid5 ref)."""
        self._sb.rpc(
            "credit_apply_pack_purchase",
            {
                "p_user_id": user_id,
                "p_event_id": event_id,
                "p_credits_milli": credits_milli,
            },
        ).execute()

    # ------------------------------------------------------------------
    # RPC — dispute event state machine (Unit 8b)
    # ------------------------------------------------------------------

    def call_apply_dispute_event(
        self,
        user_id: str,
        event_id: str,
        event_at: str,
        new_status: str,
    ) -> dict:
        """Invoke apply_dispute_event RPC and return the JSON result.

        Returns dict with keys: applied (bool), reason (str|None),
        new_status (str), locked_at (str|None).
        """
        result = self._sb.rpc(
            "apply_dispute_event",
            {
                "p_user_id": user_id,
                "p_event_id": event_id,
                "p_event_at": event_at,
                "p_new_status": new_status,
            },
        ).execute()
        if isinstance(result.data, list):
            return result.data[0] if result.data else {}
        # Supabase returns JSONB columns directly as a dict for scalar-return RPCs.
        return result.data or {}

    # ------------------------------------------------------------------
    # RPC — dispute compensating ledger entry (Unit 8b)
    # ------------------------------------------------------------------

    def call_credit_dispute_compensate(
        self, user_id: str, charge_id: str, amount_milli: int
    ) -> None:
        """Invoke credit_dispute_compensate RPC (negative delta, idempotent via uuid5 ref)."""
        self._sb.rpc(
            "credit_dispute_compensate",
            {
                "p_user_id": user_id,
                "p_charge_id": charge_id,
                "p_amount_milli": amount_milli,
            },
        ).execute()

    # ------------------------------------------------------------------
    # Direct ledger write — charge.refunded compensating entry (Unit 8b)
    # ------------------------------------------------------------------

    def record_refund_compensating_entry(
        self, user_id: str, charge_id: str, amount_milli: int
    ) -> None:
        """Write a negative credit_ledger entry for a Stripe charge refund.

        reference_id is a deterministic uuid5(NAMESPACE_URL, charge_id) so the
        ch_xxx Stripe string is safely mapped to the UUID column type.
        Duplicate charge.refunded deliveries are no-ops via ON CONFLICT
        (reference_id, type) — belt-and-braces on top of processed_webhook_events.
        """
        reference_id = str(uuid5(NAMESPACE_URL, charge_id))
        self._sb.table("credit_ledger").upsert(
            {
                "user_id": user_id,
                "delta": -amount_milli,
                "type": "refund",
                "reference_id": reference_id,
            },
            on_conflict="reference_id,type",
            ignore_duplicates=True,
        ).execute()
