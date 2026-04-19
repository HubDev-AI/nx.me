"""Stripe webhook handler — idempotent event processing.

POST /webhooks/stripe — verify signature, deduplicate, route to handler.

No JWT auth — authenticates via stripe-signature header.
Registered outside /v1 prefix (per architecture router table).

Security contract (in order):
  1. Verify Stripe signature BEFORE any DB read/write.
  2. Reject events older than WEBHOOK_EVENT_MAX_AGE_HOURS (R18).
  3. Dedup via processed_webhook_events (idempotency primitive).
  4. Route to handler.
  5. Record event_id post-success. On transient failure → 5xx (Stripe retries).

Subscription-lifecycle semantics (Unit 8a):
  - grace_until replaces status='past_due'.
  - cancelled_at replaces status='expired'.
  - credit_apply_monthly_allotment called on subscription.created
    and invoice.payment_succeeded (during/after grace).
  - 5xx on out-of-order subscription.updated (Stripe retry handles ordering).
  - No tier-gating reads; Pro is a marketing label derived from dates.

Credit-pack / Payment-sheet handlers (Unit 8b scope) are preserved from
the prior implementation — they are not changed in this unit.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import (
    get_payment_adapter,
    get_plan_version_repo,
    get_subscription_repo,
)
from app.api.entitlement import FLOW_PAYMENT_SHEET
from app.constants.tiers import TIER_ID_CREDIT_HOLDER, TIER_ID_TRIAL
from app.constants.webhooks import (
    EVT_CHECKOUT_SESSION_COMPLETED,
    EVT_INVOICE_PAYMENT_FAILED,
    EVT_INVOICE_PAYMENT_SUCCEEDED,
    EVT_SUBSCRIPTION_CREATED,
    EVT_SUBSCRIPTION_DELETED,
    EVT_SUBSCRIPTION_UPDATED,
    GRACE_PERIOD_DAYS,
    WEBHOOK_EVENT_MAX_AGE_HOURS,
)
from app.repositories.plan_version_repo import PlanVersionRepository, PRO_VERSION_NUM
from app.repositories.subscription_repo import SubscriptionRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    sub_repo: SubscriptionRepository = Depends(get_subscription_repo),
    plan_repo: PlanVersionRepository = Depends(get_plan_version_repo),
) -> dict:
    """Handle Stripe webhook events with idempotent processing.

    Security: signature verified BEFORE idempotency check or any DB write.
    Ordering: subscription.updated returns 500 when the subscription row is
    not yet present so Stripe's retry backoff handles ordering automatically.
    """
    t_start = time.monotonic()

    # ── 1. Read raw body (required for signature verification) ────────────────
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    # ── 2. Verify signature FIRST (before any DB access) ─────────────────────
    adapter = get_payment_adapter()
    try:
        event = adapter.construct_webhook_event(payload, sig_header)
    except ValueError:
        logger.warning("Invalid Stripe webhook signature")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "INVALID_WEBHOOK_SIGNATURE",
                    "message": "Invalid webhook signature",
                }
            },
        )

    event_id = event.event_id
    event_type = event.event_type
    event_created: int | None = getattr(event, "created", None)

    logger.info("Stripe webhook received: type=%s, id=%s", event_type, event_id)

    # ── 3. Reject stale events (R18) ──────────────────────────────────────────
    if event_created is not None:
        age_hours = (time.time() - event_created) / 3600
        if age_hours > WEBHOOK_EVENT_MAX_AGE_HOURS:
            logger.warning(
                "Webhook event %s is %.1fh old (limit=%dh) — discarding",
                event_id,
                age_hours,
                WEBHOOK_EVENT_MAX_AGE_HOURS,
            )
            return {"status": "stale_event_discarded"}

    # ── 4. Idempotency check (read-only, after sig verify) ────────────────────
    if sub_repo.is_webhook_event_processed(provider="stripe", event_id=event_id):
        logger.info("Duplicate webhook event %s — skipping", event_id)
        return {"status": "already_processed"}

    # ── 5. Route to handler ───────────────────────────────────────────────────
    try:
        data = event.data.get("data", {}).get("object", {})

        if event_type == EVT_CHECKOUT_SESSION_COMPLETED:
            await _handle_checkout_completed(sub_repo, data, event_id)
        elif event_type == EVT_SUBSCRIPTION_CREATED:
            await _handle_subscription_created(sub_repo, plan_repo, data)
        elif event_type == EVT_SUBSCRIPTION_UPDATED:
            _handle_subscription_updated(sub_repo, data)
        elif event_type == EVT_SUBSCRIPTION_DELETED:
            _handle_subscription_deleted(sub_repo, data)
        elif event_type == EVT_INVOICE_PAYMENT_SUCCEEDED:
            await _handle_payment_succeeded(sub_repo, plan_repo, data)
        elif event_type == EVT_INVOICE_PAYMENT_FAILED:
            _handle_payment_failed(sub_repo, data)
        elif event_type == "payment_intent.succeeded":
            await _handle_payment_intent_succeeded(sub_repo, data, event_id)
        else:
            logger.info("Unhandled webhook event type: %s", event_type)

    except (httpx.HTTPError, ConnectionError, TimeoutError, OSError) as exc:
        logger.warning("Transient error processing webhook %s: %s", event_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": {
                    "code": "TRANSIENT_ERROR",
                    "message": "Temporary processing error",
                }
            },
        ) from exc

    # ── 6. Record idempotency AFTER successful processing ─────────────────────
    sub_repo.record_webhook_event(provider="stripe", event_id=event_id)

    elapsed_ms = (time.monotonic() - t_start) * 1000
    logger.info(
        "_webhook_latency_ms=%.1f type=%s id=%s", elapsed_ms, event_type, event_id
    )

    return {"status": "processed"}


# ---------------------------------------------------------------------------
# Event handlers — subscription lifecycle
# ---------------------------------------------------------------------------


async def _handle_checkout_completed(
    sub_repo: SubscriptionRepository, session: dict, event_id: str
) -> None:
    """Handle checkout.session.completed.

    Subscription mode: stamp users.stripe_customer_id; wait for
    customer.subscription.created to write the subscription row.

    Payment mode: credit-pack grant (Unit 8b path — preserved from prior
    implementation; handled inline here until 8b refactors it out).
    """
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

    if mode == "subscription":
        # Stamp stripe_customer_id; subscription row written by subscription.created.
        customer_id = session.get("customer")
        if customer_id:
            sub_repo.stamp_stripe_customer_id(user_id, customer_id)
        logger.info(
            "Subscription checkout completed for user=%s customer=%s",
            user_id,
            customer_id,
        )

    elif mode == "payment":
        # Credit-pack purchase — Unit 8b scope; logic preserved from v0.
        credits_str = metadata.get("credits", "0")
        try:
            credits = int(credits_str)
        except (ValueError, TypeError):
            logger.error(
                "checkout.session.completed: invalid credits value '%s' in event %s",
                credits_str,
                event_id,
            )
            return

        if credits <= 0:
            logger.warning(
                "checkout.session.completed with invalid credits=%s", credits_str
            )
            return

        rpc_result = sub_repo.handle_checkout_credit_atomic(
            user_id=user_id,
            credits=credits,
            event_id=event_id,
            trial_tier_id=TIER_ID_TRIAL,
            credit_holder_tier_id=TIER_ID_CREDIT_HOLDER,
        )
        logger.info(
            "Credit purchase: user=%s, credits=%d, event=%s, tier_upgraded=%s",
            user_id,
            credits,
            event_id,
            rpc_result.get("tier_upgraded", False),
        )


async def _handle_subscription_created(
    sub_repo: SubscriptionRepository,
    plan_repo: PlanVersionRepository,
    subscription: dict,
) -> None:
    """Handle customer.subscription.created.

    UPSERTs the subscription row with plan_version_id=v1_pro, status='active',
    and billing period dates.  Then calls credit_apply_monthly_allotment (R11
    REPLACE semantics).
    """
    sub_id = subscription.get("id", "")
    metadata = subscription.get("metadata", {})
    user_id = metadata.get("user_id")

    if not user_id:
        logger.warning(
            "subscription.created missing user_id in metadata (sub=%s)", sub_id
        )
        return
    try:
        UUID(user_id)
    except ValueError:
        logger.error("Invalid user_id UUID in subscription.created: %s", user_id)
        return

    # Resolve v1_pro plan version id (instance-level cache; safe per R12).
    pro_row = plan_repo.get_by_version_num(PRO_VERSION_NUM)
    if not pro_row:
        raise RuntimeError(
            f"plan_versions seed row '{PRO_VERSION_NUM}' is missing; "
            "migration 0048 did not seed correctly."
        )
    plan_version_id = pro_row["id"]

    now_utc = datetime.now(tz=timezone.utc).isoformat()
    period_start = subscription.get("current_period_start")
    period_end = subscription.get("current_period_end")

    start_iso = (
        datetime.fromtimestamp(period_start, tz=timezone.utc).isoformat()
        if period_start
        else now_utc
    )
    end_iso = (
        datetime.fromtimestamp(period_end, tz=timezone.utc).isoformat()
        if period_end
        else now_utc
    )

    sub_repo.upsert_subscription(
        {
            "user_id": user_id,
            "provider": "stripe",
            "provider_subscription_id": sub_id,
            "plan_version_id": plan_version_id,
            "status": "active",
            "billing_period_start": start_iso,
            "billing_period_end": end_iso,
            "created_at": now_utc,
            "updated_at": now_utc,
        }
    )

    # Grant monthly allotment (REPLACE semantics — discards non-pack balance).
    sub_repo.call_credit_apply_monthly_allotment(user_id, plan_version_id)

    logger.info(
        "Subscription created: user=%s, sub=%s, plan_version_id=%s",
        user_id,
        sub_id,
        plan_version_id,
    )


def _handle_subscription_updated(
    sub_repo: SubscriptionRepository, subscription: dict
) -> None:
    """Handle customer.subscription.updated.

    If the subscription row is NOT FOUND, returns HTTP 500 so Stripe's
    built-in retry backoff handles out-of-order delivery (subscription.created
    arrives after subscription.updated).  No ARQ retry worker in v1.
    """
    sub_id = subscription.get("id", "")
    existing = sub_repo.get_subscription_by_provider_id(sub_id)
    if existing is None:
        logger.warning(
            "subscription.updated: row not found for sub=%s — returning 500 "
            "for Stripe retry",
            sub_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": {
                    "code": "SUBSCRIPTION_NOT_FOUND",
                    "message": (
                        "Subscription row not found; event may have arrived "
                        "before subscription.created. Stripe will retry."
                    ),
                }
            },
        )

    now_utc = datetime.now(tz=timezone.utc).isoformat()
    update_data: dict = {"updated_at": now_utc}

    cancel_at_period_end = subscription.get("cancel_at_period_end", False)
    if cancel_at_period_end:
        update_data["cancelled_at"] = now_utc
        logger.info("Subscription %s set to cancel at period end", sub_id)

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

    sub_repo.update_subscription_by_provider_id(sub_id, update_data)
    logger.info("Subscription updated: sub=%s", sub_id)


def _handle_subscription_deleted(
    sub_repo: SubscriptionRepository, subscription: dict
) -> None:
    """Handle customer.subscription.deleted.

    Writes cancelled_at + status='cancelled'.  No balance mutation (R10).
    """
    sub_id = subscription.get("id", "")
    now_utc = datetime.now(tz=timezone.utc).isoformat()

    sub_repo.update_subscription_by_provider_id(
        sub_id,
        {
            "status": "cancelled",
            "cancelled_at": now_utc,
            "updated_at": now_utc,
        },
    )

    logger.info("Subscription deleted (cancelled): sub=%s", sub_id)


async def _handle_payment_succeeded(
    sub_repo: SubscriptionRepository,
    plan_repo: PlanVersionRepository,
    invoice: dict,
) -> None:
    """Handle invoice.payment_succeeded.

    If the subscription is currently in grace (grace_until IS NOT NULL) OR
    the label is effectively Free (grace expired), restore status='active',
    clear grace_until, and re-grant the monthly allotment (REPLACE semantics).
    """
    sub_id = invoice.get("subscription", "")
    if not sub_id:
        logger.warning("invoice.payment_succeeded with no subscription ID")
        return

    row = sub_repo.get_subscription_by_provider_id(sub_id)
    if row is None:
        logger.warning(
            "invoice.payment_succeeded: no subscription row for sub=%s", sub_id
        )
        return

    grace_until = row.get("grace_until")
    current_status = row.get("status", "")
    now_utc = datetime.now(tz=timezone.utc)

    # Recover if in grace or if grace has already expired (status drifted to
    # non-active after the grace window lapsed without a prior payment event).
    in_grace = grace_until is not None
    grace_expired = (
        current_status != "active"
        and grace_until is None
        and current_status in {"past_due"}  # legacy enum value compatibility
    )

    if in_grace or grace_expired:
        user_id = row.get("user_id")
        if not user_id:
            logger.error(
                "invoice.payment_succeeded: subscription row has no user_id for sub=%s",
                sub_id,
            )
            return

        # Resolve plan version for re-grant.
        pro_row = plan_repo.get_by_version_num(PRO_VERSION_NUM)
        if not pro_row:
            raise RuntimeError(
                f"plan_versions seed row '{PRO_VERSION_NUM}' missing during "
                "payment_succeeded recovery"
            )
        plan_version_id = pro_row["id"]

        sub_repo.update_subscription_by_provider_id(
            sub_id,
            {
                "status": "active",
                "grace_until": None,
                "updated_at": now_utc.isoformat(),
            },
        )
        sub_repo.call_credit_apply_monthly_allotment(user_id, plan_version_id)

        logger.info(
            "Payment succeeded during grace: user=%s sub=%s grace_cleared=True",
            user_id,
            sub_id,
        )
    else:
        logger.info(
            "invoice.payment_succeeded for active sub=%s — no recovery needed", sub_id
        )


def _handle_payment_failed(sub_repo: SubscriptionRepository, invoice: dict) -> None:
    """Handle invoice.payment_failed.

    Sets grace_until = now() + GRACE_PERIOD_DAYS.  Does NOT set
    status='past_due' (R9 new semantics).
    """
    sub_id = invoice.get("subscription", "")
    if not sub_id:
        logger.warning("invoice.payment_failed with no subscription ID")
        return

    grace_until = (
        datetime.now(tz=timezone.utc) + timedelta(days=GRACE_PERIOD_DAYS)
    ).isoformat()

    sub_repo.update_subscription_by_provider_id(
        sub_id,
        {
            "grace_until": grace_until,
            "updated_at": datetime.now(tz=timezone.utc).isoformat(),
        },
    )

    logger.warning(
        "Payment failed for subscription %s — grace_until=%s", sub_id, grace_until
    )


# ---------------------------------------------------------------------------
# Payment-sheet / PaymentIntent handler (Unit 8b scope — preserved)
# ---------------------------------------------------------------------------


async def _handle_payment_intent_succeeded(
    sub_repo: SubscriptionRepository, intent: dict, event_id: str
) -> None:
    """Handle payment_intent.succeeded — credit grant from Payment Sheet.

    Only processes intents stamped with ``metadata.flow=payment_sheet``
    so legacy Checkout-created PaymentIntents are ignored here (the
    ``checkout.session.completed`` handler owns those).
    """
    metadata = intent.get("metadata") or {}
    if metadata.get("flow") != FLOW_PAYMENT_SHEET:
        logger.info(
            "payment_intent.succeeded: non-payment-sheet flow, skipping (event=%s)",
            event_id,
        )
        return

    user_id = metadata.get("user_id")
    if not user_id:
        logger.warning(
            "payment_intent.succeeded missing user_id in metadata (event=%s)",
            event_id,
        )
        return
    try:
        UUID(user_id)
    except ValueError:
        logger.error(
            "Invalid user_id UUID in payment_intent.succeeded: %s (event=%s)",
            user_id,
            event_id,
        )
        return

    credits_str = metadata.get("credits", "0")
    try:
        credits = int(credits_str)
    except (ValueError, TypeError):
        logger.error(
            "payment_intent.succeeded: invalid credits value '%s' in event %s",
            credits_str,
            event_id,
        )
        return

    if credits <= 0:
        logger.warning(
            "payment_intent.succeeded with invalid credits=%s (event=%s)",
            credits_str,
            event_id,
        )
        return

    rpc_result = sub_repo.handle_checkout_credit_atomic(
        user_id=user_id,
        credits=credits,
        event_id=event_id,
        trial_tier_id=TIER_ID_TRIAL,
        credit_holder_tier_id=TIER_ID_CREDIT_HOLDER,
    )

    logger.info(
        "PaymentIntent credit purchase: user=%s, credits=%d, event=%s, tier_upgraded=%s",
        user_id,
        credits,
        event_id,
        rpc_result.get("tier_upgraded", False),
    )
