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
        return result.data["user_id"] if result.data else None

    # ------------------------------------------------------------------
    # subscriptions table — writes
    # ------------------------------------------------------------------

    def insert_subscription(self, row: dict) -> None:
        """Insert a new subscription row."""
        self._sb.table("subscriptions").insert(row).execute()

    def update_subscription_by_provider_id(
        self,
        provider_subscription_id: str,
        updates: dict,
    ) -> None:
        """Apply field updates to a subscription row identified by provider ID."""
        self._sb.table("subscriptions").update(updates).eq(
            "provider_subscription_id", provider_subscription_id
        ).execute()

    # ------------------------------------------------------------------
    # processed_webhook_events table
    # ------------------------------------------------------------------

    def record_webhook_event(self, provider: str, event_id: str) -> None:
        """Insert a processed webhook event record.

        Raises the underlying exception (including unique constraint violation)
        so the caller can detect duplicate events.
        """
        self._sb.table("processed_webhook_events").insert({
            "provider": provider,
            "event_id": event_id,
        }).execute()

    # ------------------------------------------------------------------
    # users table — tier updates driven by webhook events
    # ------------------------------------------------------------------

    def update_user_tier(self, user_id: str | UUID, tier_id: str | UUID) -> None:
        """Update a user's tier_id."""
        self._sb.table("users").update({
            "tier_id": str(tier_id),
        }).eq("id", str(user_id)).execute()

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
        result = self._sb.rpc("handle_checkout_credit_atomic", {
            "p_user_id": user_id,
            "p_credits": credits,
            "p_event_id": event_id,
            "p_trial_tier_id": trial_tier_id,
            "p_credit_holder_tier_id": credit_holder_tier_id,
        }).execute()
        return result.data[0] if result.data else {}
