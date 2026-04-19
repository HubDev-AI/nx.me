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

Credit-pack + dispute + refund handlers (Unit 8b):
  - payment_intent.succeeded with flow=payment_sheet → credit_apply_pack_purchase.
  - charge.refunded → compensating ledger entry (type='refund').
  - charge.dispute.created/closed/funds_withdrawn → apply_dispute_event CAS
    state machine; 500 on out-of-order so Stripe retries.
  - charge.dispute.closed (lost) → also calls credit_dispute_compensate.
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
    get_user_repo,
)
from app.api.entitlement import FLOW_PAYMENT_SHEET
from app.config import settings
from app.constants.tiers import TIER_ID_CREDIT_HOLDER, TIER_ID_TRIAL
from app.constants.webhooks import (
    DISPUTE_EVENT_CLOSED_LOST,
    DISPUTE_EVENT_CLOSED_WON,
    DISPUTE_EVENT_CREATED,
    DISPUTE_EVENT_FUNDS_WITHDRAWN,
    DISPUTE_STATUS_LOST,
    DISPUTE_STATUS_WON,
    EVT_CHARGE_DISPUTE_CLOSED,
    EVT_CHARGE_DISPUTE_CREATED,
    EVT_CHARGE_DISPUTE_FUNDS_WITHDRAWN,
    EVT_CHARGE_REFUNDED,
    EVT_CHECKOUT_SESSION_COMPLETED,
    EVT_INVOICE_PAYMENT_FAILED,
    EVT_INVOICE_PAYMENT_SUCCEEDED,
    EVT_PAYMENT_INTENT_SUCCEEDED,
    EVT_SUBSCRIPTION_CREATED,
    EVT_SUBSCRIPTION_DELETED,
    EVT_SUBSCRIPTION_UPDATED,
    GRACE_PERIOD_DAYS,
    WEBHOOK_EVENT_MAX_AGE_HOURS,
)
from app.repositories.plan_version_repo import PlanVersionRepository, PRO_VERSION_NUM
from app.repositories.subscription_repo import SubscriptionRepository
from app.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    sub_repo: SubscriptionRepository = Depends(get_subscription_repo),
    plan_repo: PlanVersionRepository = Depends(get_plan_version_repo),
    user_repo: UserRepository = Depends(get_user_repo),
) -> dict:
    """Handle Stripe webhook events with idempotent processing.

    Security: signature verified BEFORE idempotency check or any DB write.
    Ordering: subscription.updated returns 500 when the subscription row is
    not yet present so Stripe's retry backoff handles ordering automatically.
    Dispute ordering: apply_dispute_event returns out_of_order → handler
    returns 500 so Stripe retries until CAS sequence converges.
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
        elif event_type == EVT_PAYMENT_INTENT_SUCCEEDED:
            await _handle_payment_intent_succeeded(sub_repo, data, event_id)
        elif event_type == EVT_CHARGE_REFUNDED:
            _handle_charge_refunded(sub_repo, user_repo, data, event_id)
        elif event_type == EVT_CHARGE_DISPUTE_CREATED:
            _handle_dispute_event(
                sub_repo, user_repo, data, event_id, DISPUTE_EVENT_CREATED
            )
        elif event_type == EVT_CHARGE_DISPUTE_CLOSED:
            _handle_dispute_closed(sub_repo, user_repo, data, event_id)
        elif event_type == EVT_CHARGE_DISPUTE_FUNDS_WITHDRAWN:
            _handle_dispute_event(
                sub_repo, user_repo, data, event_id, DISPUTE_EVENT_FUNDS_WITHDRAWN
            )
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
# Payment-sheet / PaymentIntent handler (Unit 8b)
# ---------------------------------------------------------------------------


async def _handle_payment_intent_succeeded(
    sub_repo: SubscriptionRepository, intent: dict, event_id: str
) -> None:
    """Handle payment_intent.succeeded — credit grant from Payment Sheet.

    Only processes intents stamped with ``metadata.flow=payment_sheet``
    so legacy Checkout-created PaymentIntents are ignored here (the
    ``checkout.session.completed`` handler owns those).

    Calls credit_apply_pack_purchase RPC with CREDIT_PACK_V1_CREDITS_MILLI
    from settings, ignoring the intent's metadata.credits field, so the
    server is the single source of truth for pack size (R7-Pack).
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

    credits_milli = settings.CREDIT_PACK_V1_CREDITS_MILLI
    sub_repo.call_credit_apply_pack_purchase(
        user_id=user_id,
        event_id=event_id,
        credits_milli=credits_milli,
    )

    logger.info(
        "PaymentIntent credit pack purchase: user=%s, credits_milli=%d, event=%s",
        user_id,
        credits_milli,
        event_id,
    )


# ---------------------------------------------------------------------------
# Charge refund handler (Unit 8b)
# ---------------------------------------------------------------------------


def _handle_charge_refunded(
    sub_repo: SubscriptionRepository,
    user_repo: UserRepository,
    charge: dict,
    event_id: str,
) -> None:
    """Handle charge.refunded — write a compensating credit_ledger entry.

    Looks up user_id via users.stripe_customer_id (backfilled in Unit 1).
    Writes a negative ledger entry (type='refund') keyed on charge_id so
    duplicate charge.refunded deliveries are no-ops via outer dedup.
    Amount is the refund amount_refunded in pence/cents; we store a
    milli-credit equivalent of CREDIT_PACK_V1_CREDITS_MILLI (one pack)
    per refund regardless of the monetary amount, as packs are atomic.
    """
    customer_id = charge.get("customer")
    charge_id = charge.get("id", "")

    if not customer_id:
        logger.warning(
            "charge.refunded missing customer field (event=%s, charge=%s)",
            event_id,
            charge_id,
        )
        return

    user_row = user_repo.find_by_stripe_customer_id(customer_id)
    if not user_row:
        logger.warning(
            "charge.refunded: no user found for customer=%s (event=%s)",
            customer_id,
            event_id,
        )
        return

    user_id = user_row["id"]
    amount_milli = settings.CREDIT_PACK_V1_CREDITS_MILLI

    sub_repo.record_refund_compensating_entry(
        user_id=user_id,
        charge_id=charge_id,
        amount_milli=amount_milli,
    )

    logger.info(
        "Charge refunded compensating entry: user=%s charge=%s amount_milli=%d event=%s",
        user_id,
        charge_id,
        amount_milli,
        event_id,
    )


# ---------------------------------------------------------------------------
# Dispute event handlers (Unit 8b)
# ---------------------------------------------------------------------------


def _resolve_dispute_user_id(
    user_repo: UserRepository, dispute: dict, event_id: str
) -> str | None:
    """Resolve user_id for a dispute object from stripe_customer_id.

    Returns user_id string or None if the user cannot be found.
    """
    customer_id = dispute.get("customer") or dispute.get("charge", {})
    # dispute object carries .customer directly
    if not isinstance(customer_id, str):
        customer_id = dispute.get("customer")

    if not customer_id:
        logger.warning("dispute event missing customer field (event=%s)", event_id)
        return None

    user_row = user_repo.find_by_stripe_customer_id(customer_id)
    if not user_row:
        logger.warning(
            "dispute event: no user found for customer=%s (event=%s)",
            customer_id,
            event_id,
        )
        return None

    return user_row["id"]


def _handle_dispute_event(
    sub_repo: SubscriptionRepository,
    user_repo: UserRepository,
    dispute: dict,
    event_id: str,
    new_status: str,
) -> None:
    """Apply a dispute state transition via the apply_dispute_event CAS RPC.

    Returns 500 (re-raises HTTPException) on out-of-order events so Stripe
    retries delivery — the CAS state machine converges on the final state.
    Duplicate event_id (Stripe retry of same event) returns applied=False
    with reason='duplicate'; this is treated as success.
    """
    user_id = _resolve_dispute_user_id(user_repo, dispute, event_id)
    if not user_id:
        return

    # dispute object carries 'created' as a unix timestamp.
    raw_created = dispute.get("created")
    if raw_created is None:
        logger.warning("dispute event missing created timestamp (event=%s)", event_id)
        return
    event_at = datetime.fromtimestamp(raw_created, tz=timezone.utc).isoformat()

    result = sub_repo.call_apply_dispute_event(
        user_id=user_id,
        event_id=event_id,
        event_at=event_at,
        new_status=new_status,
    )

    applied = result.get("applied", False)
    reason = result.get("reason")

    if not applied and reason == "out_of_order":
        logger.warning(
            "dispute event out-of-order: user=%s event=%s status=%s — returning 500 for Stripe retry",
            user_id,
            event_id,
            new_status,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": {
                    "code": "DISPUTE_OUT_OF_ORDER",
                    "message": (
                        "Dispute event arrived out-of-order. "
                        "Stripe will retry delivery."
                    ),
                }
            },
        )

    logger.info(
        "Dispute event applied: user=%s event=%s status=%s applied=%s reason=%s locked_at=%s",
        user_id,
        event_id,
        new_status,
        applied,
        reason,
        result.get("locked_at"),
    )


def _handle_dispute_closed(
    sub_repo: SubscriptionRepository,
    user_repo: UserRepository,
    dispute: dict,
    event_id: str,
) -> None:
    """Handle charge.dispute.closed — map Stripe outcome status to dispute event.

    Stripe sends a single charge.dispute.closed event; the outcome lives in
    dispute.status. Maps:
      won                 → closed_won  (clear locked_at)
      lost                → closed_lost (keep locked_at + compensating entry)
      warning_closed /
      warning_needs_response → closed_won (pre-dispute inquiry, not a chargeback)
    """
    stripe_status = dispute.get("status", "")
    charge_id = dispute.get("charge", "") or dispute.get("id", "")

    if stripe_status == DISPUTE_STATUS_WON:
        new_status = DISPUTE_EVENT_CLOSED_WON
    elif stripe_status == DISPUTE_STATUS_LOST:
        new_status = DISPUTE_EVENT_CLOSED_LOST
    else:
        # warning_closed / warning_needs_response / unknown → treat as won.
        logger.info(
            "charge.dispute.closed with status=%s — treating as closed_won (event=%s)",
            stripe_status,
            event_id,
        )
        new_status = DISPUTE_EVENT_CLOSED_WON

    # Apply the CAS state transition (raises 500 on out-of-order).
    _handle_dispute_event(sub_repo, user_repo, dispute, event_id, new_status)

    # For closed_lost: write the compensating ledger entry AFTER the state
    # transition so a concurrent reserve sees locked_at before the negative
    # delta lands (belt-and-braces; the advisory lock in the RPC already
    # serialises these).
    if new_status == DISPUTE_EVENT_CLOSED_LOST:
        user_id = _resolve_dispute_user_id(user_repo, dispute, event_id)
        if user_id and charge_id:
            sub_repo.call_credit_dispute_compensate(
                user_id=user_id,
                charge_id=charge_id,
                amount_milli=settings.CREDIT_PACK_V1_CREDITS_MILLI,
            )
            logger.info(
                "Dispute closed_lost compensating entry: user=%s charge=%s event=%s",
                user_id,
                charge_id,
                event_id,
            )
