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
    get_user_or_guest,
    get_current_user,
    get_entitlement_service,
    get_payment_adapter,
    get_subscription_repo,
)
from app.api.middleware.auth import UserClaims
from app.config import settings
from app.entitlement.models import (
    PackOption,
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

    Reads STRIPE_PRICE_CREDITS_PACK_V1 and STRIPE_PRICE_PRO_V1 from settings.
    Both are required env vars (fail-fast at settings load). Stripe price
    retrieval failures are logged as warnings and result in None fields
    rather than endpoint errors.
    """
    pack: PackOption | None = None
    pack_price_id = settings.STRIPE_PRICE_CREDITS_PACK_V1
    try:
        pack_price = await payment.get_price(pack_price_id)
        pack = PackOption(
            pack_id="credits_pack_v1",
            milli_credits=100,
            price_id=pack_price_id,
            amount_cents=pack_price.amount_cents,
            currency=pack_price.currency,
        )
    except Exception as exc:
        logger.warning(
            "Credit pack unavailable — Stripe price retrieval failed for %s: %s",
            pack_price_id,
            exc,
        )

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

    return PurchaseOptions(pack=pack, pro=pro)


@router.get("/entitlement")
async def get_entitlement(
    claims: UserClaims = Depends(get_user_or_guest),
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


class CreditPurchaseIntentRequest(BaseModel):
    credit_pack_id: str


class CreditPurchaseIntentResponse(BaseModel):
    payment_intent_client_secret: str
    ephemeral_key: str
    customer_id: str
    publishable_key: str


# Webhook disambiguator for PaymentIntent.succeeded — only our Payment
# Sheet flow sets this value, so legacy Checkout-mode PaymentIntents
# are ignored by the new handler.
FLOW_PAYMENT_SHEET = "payment_sheet"


def _resolve_credit_pack_or_raise(credit_pack_id: str) -> tuple[int, str]:
    """Shared lookup for credit pack id + configured Stripe price.

    Returns ``(credit_count, price_id)``. Raises HTTPException with the
    same status codes the legacy Checkout endpoint uses so mobile error
    handling stays consistent across the two flows.
    """
    credit_count = _CREDIT_PACKS.get(credit_pack_id)
    if credit_count is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "INVALID_CREDIT_PACK",
                    "message": f"Unknown credit pack: {credit_pack_id}",
                }
            },
        )

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
    return credit_count, price_id


@router.post(
    "/credit-purchases",
    response_model=CheckoutResponse,
    status_code=status.HTTP_201_CREATED,
    deprecated=True,
)
async def create_credit_purchase(
    body: CreditPurchaseRequest,
    claims: UserClaims = Depends(get_current_user),
    payment: PaymentPort = Depends(get_payment_adapter),
) -> CheckoutResponse:
    """Create a Stripe Checkout session for credit pack purchase.

    AC-1: No card data flows through NXME — Stripe hosted payment sheet.

    Deprecated (PR6): prefer ``POST /credit-purchases/intent`` which
    returns a PaymentIntent bundle for the in-app Stripe Payment Sheet.
    This endpoint is retained for back-compat with older mobile builds
    and will be removed once rollout bake-time completes.
    """
    user_id = claims["sub"]

    credit_count, price_id = _resolve_credit_pack_or_raise(body.credit_pack_id)

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

    logger.warning(
        "Legacy Checkout credit purchase: user=%s, pack=%s — migrate to /credit-purchases/intent",
        user_id,
        body.credit_pack_id,
    )

    return CheckoutResponse(checkout_url=checkout_url)


@router.post(
    "/credit-purchases/intent",
    response_model=CreditPurchaseIntentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_credit_purchase_intent(
    body: CreditPurchaseIntentRequest,
    claims: UserClaims = Depends(get_current_user),
    payment: PaymentPort = Depends(get_payment_adapter),
) -> CreditPurchaseIntentResponse:
    """Create a Stripe PaymentIntent for the in-app Payment Sheet.

    Replaces the redirect-based Checkout flow for credit packs. Metadata
    is stamped with ``flow=payment_sheet`` so the webhook handler can
    disambiguate from the legacy ``checkout.session.completed`` path.
    """
    user_id = claims["sub"]

    credit_count, price_id = _resolve_credit_pack_or_raise(body.credit_pack_id)

    bundle = await payment.create_payment_intent(
        user_id=user_id,
        price_id=price_id,
        metadata={
            "type": "credit_purchase",
            "credits": str(credit_count),
            "pack_id": body.credit_pack_id,
            "flow": FLOW_PAYMENT_SHEET,
        },
    )

    logger.info(
        "Credit purchase PaymentIntent created: user=%s, pack=%s",
        user_id,
        body.credit_pack_id,
    )

    return CreditPurchaseIntentResponse(
        payment_intent_client_secret=bundle.client_secret,
        ephemeral_key=bundle.ephemeral_key,
        customer_id=bundle.customer_id,
        publishable_key=bundle.publishable_key,
    )


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
