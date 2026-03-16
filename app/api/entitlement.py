"""Entitlement API — delegates to EntitlementService.

AC-D1: No direct credit_ledger or subscriptions reads in this file.
All entitlement logic routes through EntitlementService.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_current_user, get_entitlement_service
from app.api.middleware.auth import UserClaims
from app.constants.tiers import CREDIT_HOLDER, PREMIUM, TRIAL
from app.entitlement.service import EntitlementService

router = APIRouter(tags=["entitlement"])

# Maps DB tier slug → public API tier identifier (AC-5: named constants only)
_SLUG_TO_TIER_NAME: dict[str, str] = {
    "free": TRIAL,
    "credits": CREDIT_HOLDER,
    "premium": PREMIUM,
}


class EntitlementResponse(BaseModel):
    tier: str
    trial_analyses_remaining: int
    credit_balance: int
    can_generate: bool


@router.get("/entitlement", response_model=EntitlementResponse)
async def get_entitlement(
    claims: UserClaims = Depends(get_current_user),
    svc: EntitlementService = Depends(get_entitlement_service),
) -> EntitlementResponse:
    """Return the authenticated user's current entitlement snapshot."""
    from uuid import UUID

    user_id = UUID(claims["sub"])
    state = await svc.get_entitlement(user_id)

    tier_name = _SLUG_TO_TIER_NAME.get(state.tier.slug, state.tier.slug.upper())

    return EntitlementResponse(
        tier=tier_name,
        trial_analyses_remaining=state.trial_analyses_remaining,
        credit_balance=state.credit_balance,
        can_generate=state.can_generate,
    )
