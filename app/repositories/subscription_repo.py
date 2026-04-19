"""Subscription repository — all subscriptions and processed_webhook_events queries.

Follows the same pattern as UserRepository: constructor takes a Client,
methods are synchronous (callers use run_sync for async handlers).
"""

from __future__ import annotations

import logging
from uuid import UUID

from supabase import Client

from app.entitlement.ledger import CreditLedger

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
    # users table — tier updates driven by webhook events
    # ------------------------------------------------------------------

    def update_user_tier(self, user_id: str | UUID, tier_id: str | UUID) -> None:
        """Update a user's tier_id."""
        self._sb.table("users").update(
            {
                "tier_id": str(tier_id),
            }
        ).eq("id", str(user_id)).execute()

    # ------------------------------------------------------------------
    # Tier recomputation via credit balance
    # ------------------------------------------------------------------

    def recompute_tier_after_subscription_deleted(
        self,
        user_id: str,
        credit_holder_tier_id: str,
        trial_tier_id: str,
    ) -> str:
        """Recompute a user's tier after subscription deletion based on credit balance.

        Returns the new tier_id that was applied.
        """
        ledger = CreditLedger(self._sb)
        balance = ledger.balance(UUID(user_id))
        new_tier_id = credit_holder_tier_id if balance > 0 else trial_tier_id
        self.update_user_tier(user_id, new_tier_id)
        return new_tier_id

    # ------------------------------------------------------------------
    # RPC — atomic credit checkout
    # ------------------------------------------------------------------

    def handle_checkout_credit_atomic(
        self,
        user_id: str,
        credits: int,
        event_id: str,
        trial_tier_id: str,
        credit_holder_tier_id: str,
    ) -> dict:
        """Call the handle_checkout_credit_atomic RPC and return the first row."""
        result = self._sb.rpc(
            "handle_checkout_credit_atomic",
            {
                "p_user_id": user_id,
                "p_credits": credits,
                "p_event_id": event_id,
                "p_trial_tier_id": trial_tier_id,
                "p_credit_holder_tier_id": credit_holder_tier_id,
            },
        ).execute()
        return result.data[0] if result.data else {}

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

        Keyed on charge_id so duplicate charge.refunded deliveries are no-ops
        (ON CONFLICT DO NOTHING via the unique constraint on reference_id where
        type='refund' — assumed to be added alongside this call; if the index
        does not exist yet, duplicates are harmless for v1 given the outer
        processed_webhook_events dedup).
        """
        self._sb.table("credit_ledger").upsert(
            {
                "user_id": user_id,
                "delta": -amount_milli,
                "type": "refund",
                "reference_id": charge_id,
            },
            on_conflict="reference_id,type",
            ignore_duplicates=True,
        ).execute()
