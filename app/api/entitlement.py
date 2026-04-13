"""Entitlement API — delegates to EntitlementService.

AC-D1: No direct credit_ledger or subscriptions reads in this file.
All entitlement logic routes through EntitlementService.

Story 4-4 adds: POST /credits/purchase, POST /subscriptions, DELETE /subscriptions.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import (
    get_analysis_user,
    get_current_user,
    get_entitlement_service,
    get_payment_adapter,
    get_subscription_repo,
)
from app.api.middleware.auth import UserClaims
from app.config import settings
from app.constants.tiers import SLUG_TO_TIER_NAME
from app.entitlement.service import EntitlementService
from app.payment.ports import PaymentPort
from app.repositories.subscription_repo import SubscriptionRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["entitlement"])

# Maps DB tier slug → public API tier identifier (AC-5: named constants only)
_SLUG_TO_TIER_NAME = SLUG_TO_TIER_NAME


class CreditPackOption(BaseModel):
    pack_id: str
    credits: int
    price_id: str


class PremiumOption(BaseModel):
    price_id: str
    name: str


class PurchaseOptions(BaseModel):
    credit_packs: list[CreditPackOption]
    premium: PremiumOption | None


class EntitlementResponse(BaseModel):
    tier: str
    trial_analyses_remaining: int
    credit_balance: int
    can_generate: bool
    subscription_status: str | None = None
    billing_period_end: str | None = None
    purchase_options: PurchaseOptions | None = None


def _build_purchase_options(svc: EntitlementService) -> PurchaseOptions | None:
    """Build purchase options for paywall display (AC-FR2)."""
    packs: list[CreditPackOption] = []
    for pack_id, credit_count in _CREDIT_PACKS.items():
        price_id = getattr(settings, f"STRIPE_PRICE_CREDITS_{credit_count}", "")
        if price_id:
            packs.append(
                CreditPackOption(
                    pack_id=pack_id, credits=credit_count, price_id=price_id
                )
            )

    premium_price_id = svc.get_tier_stripe_price_id("premium")
    premium = (
        PremiumOption(price_id=premium_price_id, name="Premium")
        if premium_price_id
        else None
    )

    if not packs and not premium:
        return None

    return PurchaseOptions(credit_packs=packs, premium=premium)


@router.get("/entitlement", response_model=EntitlementResponse)
async def get_entitlement(
    claims: UserClaims = Depends(get_analysis_user),
    svc: EntitlementService = Depends(get_entitlement_service),
) -> EntitlementResponse:
    """Return the authenticated user's current entitlement snapshot.

    Story 4-5: includes subscription_status, billing_period_end, and
    purchase_options for paywall display.
    """
    user_id = UUID(claims["sub"])
    state = await svc.get_entitlement(user_id)

    tier_name = _SLUG_TO_TIER_NAME.get(state.tier.slug, state.tier.slug.upper())

    # Subscription status
    sub_status: str | None = None
    billing_end: str | None = None
    if state.has_active_subscription:
        sub_status = "active"
        if state.subscription_billing_period_end:
            billing_end = state.subscription_billing_period_end.isoformat()

    # Include purchase options when user can't generate (paywall trigger)
    purchase_options: PurchaseOptions | None = None
    if not state.can_generate:
        purchase_options = _build_purchase_options(svc)

    return EntitlementResponse(
        tier=tier_name,
        trial_analyses_remaining=state.trial_analyses_remaining,
        credit_balance=state.credit_balance,
        can_generate=state.can_generate,
        subscription_status=sub_status,
        billing_period_end=billing_end,
        purchase_options=purchase_options,
    )


# ---------------------------------------------------------------------------
# Credit purchase (Story 4-4)
# ---------------------------------------------------------------------------

# Credit pack definitions — map pack ID to (price_id env var, credit count)
# Stripe price IDs are env-specific; configure via admin or env vars.
_CREDIT_PACKS: dict[str, int] = {
    "10_credits": 10,
    "25_credits": 25,
    "50_credits": 50,
}


class CreditPurchaseRequest(BaseModel):
    credit_pack_id: str


class CheckoutResponse(BaseModel):
    checkout_url: str


@router.post(
    "/credit-purchases",
    response_model=CheckoutResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_credit_purchase(
    body: CreditPurchaseRequest,
    claims: UserClaims = Depends(get_current_user),
    payment: PaymentPort = Depends(get_payment_adapter),
) -> CheckoutResponse:
    """Create a Stripe checkout session for credit pack purchase.

    AC-1: No card data flows through NXME — Stripe hosted payment sheet.
    """
    user_id = claims["sub"]

    credit_count = _CREDIT_PACKS.get(body.credit_pack_id)
    if credit_count is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "INVALID_CREDIT_PACK",
                    "message": f"Unknown credit pack: {body.credit_pack_id}",
                }
            },
        )

    # Credit pack price_id from Stripe product configuration.
    # Env var pattern: STRIPE_PRICE_CREDITS_10, STRIPE_PRICE_CREDITS_25, etc.
    price_id = getattr(settings, f"STRIPE_PRICE_CREDITS_{credit_count}", "")
    if not price_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "CREDIT_PACK_NOT_CONFIGURED",
                    "message": "Credit pack pricing not configured.",
                }
            },
        )

    checkout_url = await payment.create_checkout_session(
        user_id=user_id,
        price_id=price_id,
        mode="payment",
        success_url=settings.STRIPE_SUCCESS_URL,
        cancel_url=settings.STRIPE_CANCEL_URL,
        metadata={
            "type": "credit_purchase",
            "credits": str(credit_count),
        },
    )

    logger.info(
        "Credit purchase checkout created: user=%s, pack=%s",
        user_id,
        body.credit_pack_id,
    )

    return CheckoutResponse(checkout_url=checkout_url)


@router.post(
    "/credits/purchase",
    response_model=CheckoutResponse,
    status_code=status.HTTP_201_CREATED,
    deprecated=True,
)
async def purchase_credits(
    body: CreditPurchaseRequest,
    claims: UserClaims = Depends(get_current_user),
    payment: PaymentPort = Depends(get_payment_adapter),
) -> CheckoutResponse:
    """Deprecated alias — use POST /credit-purchases instead."""
    return await create_credit_purchase(body=body, claims=claims, payment=payment)


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

    # Check if already subscribed
    entitlement_state = await svc.get_entitlement(UUID(user_id))
    if entitlement_state.has_active_subscription:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "ALREADY_SUBSCRIBED",
                    "message": "You already have an active subscription.",
                }
            },
        )

    # Look up the premium tier's stripe_price_id
    price_id = svc.get_tier_stripe_price_id("premium")
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
