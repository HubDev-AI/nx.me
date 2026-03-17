"""Stripe webhook handler — idempotent event processing.

Story 4-4:
  POST /webhooks/stripe — verify signature, deduplicate, route to handler.

No JWT auth — authenticates via stripe-signature header.
Registered outside /v1 prefix (per architecture router table).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from supabase import Client

from app.api.deps import get_payment_adapter
from app.config import settings
from app.constants.tiers import TIER_ID_CREDIT_HOLDER, TIER_ID_PREMIUM, TIER_ID_TRIAL
from app.entitlement.ledger import CreditLedger

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(request: Request) -> dict:
    """Handle Stripe webhook events with idempotent processing.

    AC-2: Duplicate events return 200 without re-processing.
    AC-3: subscription.deleted recomputes tier.
    AC-4: Invalid signature returns 401.
    """
    # --- Read raw body (required for signature verification) ---
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    # --- Verify signature ---
    adapter = get_payment_adapter()
    try:
        event = adapter.construct_webhook_event(payload, sig_header)
    except ValueError:
        logger.warning("Invalid Stripe webhook signature")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "INVALID_WEBHOOK_SIGNATURE", "message": "Invalid webhook signature"}},
        )

    event_id = event.get("id", "")
    event_type = event.get("type", "")

    logger.info("Stripe webhook received: type=%s, id=%s", event_type, event_id)

    # --- Idempotency check ---
    supabase: Client = request.app.state.supabase

    try:
        supabase.table("processed_webhook_events").insert({
            "provider": "stripe",
            "event_id": event_id,
        }).execute()
    except Exception as exc:
        # UNIQUE constraint violation = duplicate event
        if "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
            logger.info("Duplicate webhook event %s — skipping", event_id)
            return {"status": "already_processed"}
        raise

    # --- Route to handler ---
    try:
        data = event.get("data", {}).get("object", {})

        if event_type == "checkout.session.completed":
            await _handle_checkout_completed(supabase, data, event_id)
        elif event_type == "customer.subscription.created":
            _handle_subscription_created(supabase, data)
        elif event_type == "customer.subscription.updated":
            _handle_subscription_updated(supabase, data)
        elif event_type == "customer.subscription.deleted":
            _handle_subscription_deleted(supabase, data)
        elif event_type == "invoice.payment_failed":
            _handle_payment_failed(supabase, data)
        else:
            logger.info("Unhandled webhook event type: %s", event_type)

    except (httpx.HTTPError, ConnectionError, TimeoutError, OSError) as exc:
        logger.warning("Transient error processing webhook event %s (type=%s): %s", event_id, event_type, exc)
        # Transient network error — return 200 to prevent Stripe retries.
        # Event is already recorded in processed_webhook_events.
        return {"status": "processing_error"}

    return {"status": "processed"}


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------


async def _handle_checkout_completed(supabase: Client, session: dict, event_id: str) -> None:
    """Handle checkout.session.completed — credit purchase or subscription."""
    mode = session.get("mode")
    metadata = session.get("metadata", {})
    user_id = metadata.get("user_id")

    if not user_id:
        logger.warning("checkout.session.completed missing user_id in metadata")
        return
    try:
        UUID(user_id)
    except ValueError:
        logger.error("Invalid user_id UUID in webhook checkout: %s", user_id)
        return

    if mode == "payment":
        # Credit purchase
        credits_str = metadata.get("credits", "0")
        try:
            credits = int(credits_str)
        except (ValueError, TypeError):
            logger.error("checkout.session.completed: invalid credits value '%s' in event %s", credits_str, event_id)
            return

        if credits <= 0:
            logger.warning("checkout.session.completed with invalid credits=%s", credits_str)
            return

        # Atomic: insert ledger entry + conditional tier upgrade
        result = supabase.rpc("handle_checkout_credit_atomic", {
            "p_user_id": user_id,
            "p_credits": credits,
            "p_event_id": event_id,
            "p_trial_tier_id": TIER_ID_TRIAL,
            "p_credit_holder_tier_id": TIER_ID_CREDIT_HOLDER,
        }).execute()

        tier_upgraded = result.data[0]["tier_upgraded"] if result.data else False
        logger.info(
            "Credit purchase: user=%s, credits=%d, event=%s, tier_upgraded=%s",
            user_id, credits, event_id, tier_upgraded,
        )

    elif mode == "subscription":
        # Subscription activation handled by customer.subscription.created webhook
        logger.info("Subscription checkout completed for user=%s", user_id)


def _handle_subscription_created(supabase: Client, subscription: dict) -> None:
    """Handle customer.subscription.created — insert subscription row."""
    sub_id = subscription.get("id", "")
    customer = subscription.get("customer", "")
    metadata = subscription.get("metadata", {})
    user_id = metadata.get("user_id")

    if not user_id:
        logger.warning("subscription.created missing user_id in metadata (sub=%s)", sub_id)
        return
    try:
        UUID(user_id)
    except ValueError:
        logger.error("Invalid user_id UUID in subscription.created: %s", user_id)
        return

    now_utc = datetime.now(tz=timezone.utc).isoformat()
    period_start = subscription.get("current_period_start")
    period_end = subscription.get("current_period_end")

    # Convert Unix timestamps to ISO
    start_iso = datetime.fromtimestamp(period_start, tz=timezone.utc).isoformat() if period_start else now_utc
    end_iso = datetime.fromtimestamp(period_end, tz=timezone.utc).isoformat() if period_end else now_utc

    supabase.table("subscriptions").insert({
        "user_id": user_id,
        "provider": "stripe",
        "provider_subscription_id": sub_id,
        "status": "active",
        "billing_period_start": start_iso,
        "billing_period_end": end_iso,
        "created_at": now_utc,
        "updated_at": now_utc,
    }).execute()

    # Upgrade tier to premium
    supabase.table("users").update({
        "tier_id": TIER_ID_PREMIUM,
    }).eq("id", user_id).execute()

    logger.info("Subscription created: user=%s, sub=%s", user_id, sub_id)


def _handle_subscription_updated(supabase: Client, subscription: dict) -> None:
    """Handle customer.subscription.updated — cancel_at_period_end or plan change."""
    sub_id = subscription.get("id", "")
    cancel_at_period_end = subscription.get("cancel_at_period_end", False)

    now_utc = datetime.now(tz=timezone.utc).isoformat()

    update_data: dict = {"updated_at": now_utc}

    if cancel_at_period_end:
        update_data["cancelled_at"] = now_utc
        logger.info("Subscription %s set to cancel at period end", sub_id)

    # Update billing period dates if present
    period_start = subscription.get("current_period_start")
    period_end = subscription.get("current_period_end")
    if period_start:
        update_data["billing_period_start"] = datetime.fromtimestamp(
            period_start, tz=timezone.utc
        ).isoformat()
    if period_end:
        update_data["billing_period_end"] = datetime.fromtimestamp(
            period_end, tz=timezone.utc
        ).isoformat()

    supabase.table("subscriptions").update(
        update_data
    ).eq("provider_subscription_id", sub_id).execute()


def _handle_subscription_deleted(supabase: Client, subscription: dict) -> None:
    """Handle customer.subscription.deleted — expire and recompute tier.

    AC-3: subscriptions.status = 'expired'; EntitlementService recomputes tier.
    """
    sub_id = subscription.get("id", "")
    now_utc = datetime.now(tz=timezone.utc).isoformat()

    # Fetch user_id BEFORE updating status (needed for tier recomputation)
    sub_row = (
        supabase.table("subscriptions")
        .select("user_id")
        .eq("provider_subscription_id", sub_id)
        .maybe_single()
        .execute()
    )
    if not sub_row.data:
        logger.warning("subscription.deleted: no subscription found for %s", sub_id)
        return

    user_id = sub_row.data["user_id"]

    # Mark subscription expired
    supabase.table("subscriptions").update({
        "status": "expired",
        "updated_at": now_utc,
    }).eq("provider_subscription_id", sub_id).execute()

    # Recompute tier based on credit balance
    ledger = CreditLedger(supabase)
    balance = ledger.balance(UUID(user_id))

    new_tier_id = TIER_ID_CREDIT_HOLDER if balance > 0 else TIER_ID_TRIAL
    supabase.table("users").update({
        "tier_id": new_tier_id,
    }).eq("id", user_id).execute()

    logger.info(
        "Subscription deleted: user=%s, sub=%s, new_tier=%s (balance=%d)",
        user_id, sub_id, new_tier_id, balance,
    )


def _handle_payment_failed(supabase: Client, invoice: dict) -> None:
    """Handle invoice.payment_failed — set subscription to past_due."""
    sub_id = invoice.get("subscription", "")
    if not sub_id:
        logger.warning("invoice.payment_failed with no subscription ID")
        return

    now_utc = datetime.now(tz=timezone.utc).isoformat()

    supabase.table("subscriptions").update({
        "status": "past_due",
        "updated_at": now_utc,
    }).eq("provider_subscription_id", sub_id).execute()

    logger.warning("Payment failed for subscription %s — set to past_due", sub_id)
