"""Entitlement API — delegates to EntitlementService.

AC-D1: No direct credit_ledger or subscriptions reads in this file.
All entitlement logic routes through EntitlementService.

Unit 7: GET /entitlement returns new ledger-based EntitlementState shape.
Story 4-4 routes: POST /credits/purchase, POST /subscriptions, DELETE /subscriptions.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import (
    get_current_user,
    get_entitlement_service,
    get_payment_adapter,
    get_subscription_repo,
)
from app.api.middleware.auth import UserClaims
from app.config import settings
from app.entitlement.models import (
    ProOption,
    PurchaseOptions,
    SubscriptionStatus,
)
from app.entitlement.service import EntitlementService
from app.payment.ports import PaymentPort
from app.repositories.subscription_repo import SubscriptionRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["entitlement"])


async def _build_purchase_options(payment: PaymentPort) -> PurchaseOptions:
    """Build purchase options for paywall display (fail-soft on Stripe errors).

    Reads STRIPE_PRICE_PRO_V1 from settings (required env var, fail-fast at
    settings load). Stripe price retrieval failures are logged as warnings
    and result in a None field rather than an endpoint error.
    """
    pro: ProOption | None = None
    pro_price_id = settings.STRIPE_PRICE_PRO_V1
    try:
        pro_price = await payment.get_price(pro_price_id)
        pro = ProOption(
            price_id=pro_price_id,
            amount_cents=pro_price.amount_cents,
            currency=pro_price.currency,
        )
    except Exception as exc:
        logger.warning(
            "Pro option unavailable — Stripe price retrieval failed for %s: %s",
            pro_price_id,
            exc,
        )

    return PurchaseOptions(pro=pro)


@router.get("/entitlement")
async def get_entitlement(
    claims: UserClaims = Depends(get_current_user),
    svc: EntitlementService = Depends(get_entitlement_service),
    payment: PaymentPort = Depends(get_payment_adapter),
) -> dict:
    """Return the authenticated user's current entitlement snapshot.

    Returns new ledger-based shape (Unit 7):
      tier, remaining_glowups, approx_remaining_ada, subscription_status,
      period_end, grace_end, blocked_reason, plan_version_id, purchase_options.
    """
    user_id = UUID(claims["sub"])
    purchase_options = await _build_purchase_options(payment)
    state = await svc.get_entitlement(user_id, purchase_options=purchase_options)

    return {
        "tier": state.tier,
        "remaining_glowups": state.remaining_glowups,
        "approx_remaining_ada": state.approx_remaining_ada,
        "subscription_status": state.subscription_status.value,
        "period_end": state.period_end.isoformat() if state.period_end else None,
        "grace_end": state.grace_end.isoformat() if state.grace_end else None,
        "blocked_reason": state.blocked_reason.value,
        "plan_version_id": str(state.plan_version_id),
        "purchase_options": state.purchase_options.model_dump(),
    }


# ---------------------------------------------------------------------------
# Subscription management (Story 4-4)
# ---------------------------------------------------------------------------


class CreateSubscriptionResponse(BaseModel):
    checkout_url: str


class CancelSubscriptionResponse(BaseModel):
    status: str
    message: str


@router.post(
    "/subscriptions",
    response_model=CreateSubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_subscription(
    claims: UserClaims = Depends(get_current_user),
    payment: PaymentPort = Depends(get_payment_adapter),
    svc: EntitlementService = Depends(get_entitlement_service),
) -> CreateSubscriptionResponse:
    """Create a Stripe checkout session for Premium subscription."""
    user_id = claims["sub"]

    # Check if already subscribed (derive from subscription_status)
    purchase_options = await _build_purchase_options(payment)
    entitlement_state = await svc.get_entitlement(
        UUID(user_id), purchase_options=purchase_options
    )
    if entitlement_state.subscription_status in {
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.GRACE,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "ALREADY_SUBSCRIBED",
                    "message": "You already have an active subscription.",
                }
            },
        )

    # Use configured Pro price ID directly
    price_id = settings.STRIPE_PRICE_PRO_V1
    if not price_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "SUBSCRIPTION_NOT_CONFIGURED",
                    "message": "Subscription not available.",
                }
            },
        )

    checkout_url = await payment.create_checkout_session(
        user_id=user_id,
        price_id=price_id,
        mode="subscription",
        success_url=settings.STRIPE_SUCCESS_URL,
        cancel_url=settings.STRIPE_CANCEL_URL,
        metadata={"type": "subscription"},
    )

    logger.info("Subscription checkout created: user=%s", user_id)

    return CreateSubscriptionResponse(checkout_url=checkout_url)


@router.delete("/subscriptions", response_model=CancelSubscriptionResponse)
async def cancel_subscription(
    claims: UserClaims = Depends(get_current_user),
    sub_repo: SubscriptionRepository = Depends(get_subscription_repo),
    payment: PaymentPort = Depends(get_payment_adapter),
) -> CancelSubscriptionResponse:
    """Cancel active subscription at period end.

    AC-5: Premium access continues until billing_period_end.
    """
    user_id = claims["sub"]

    # Find active subscription
    active_sub = sub_repo.get_active_subscription(user_id)

    if not active_sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "NO_ACTIVE_SUBSCRIPTION",
                    "message": "No active subscription found.",
                }
            },
        )

    provider_sub_id = active_sub["provider_subscription_id"]

    # Cancel at period end via Stripe
    await payment.cancel_subscription(provider_sub_id)

    logger.info(
        "Subscription cancellation requested: user=%s, sub=%s", user_id, provider_sub_id
    )

    return CancelSubscriptionResponse(
        status="cancelling",
        message="Subscription will be cancelled at the end of the billing period.",
    )
