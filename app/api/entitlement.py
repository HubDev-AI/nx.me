"""Entitlement API — read-only tier and credit status.

Story 2-1: GET /entitlement
Full EntitlementService (Story 4-1) will replace the query logic here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from supabase import Client

from app.api.deps import get_current_user, get_supabase

router = APIRouter(tags=["entitlement"])


class EntitlementResponse(BaseModel):
    tier: str
    trial_analyses_remaining: int
    credit_balance: int
    can_generate: bool


@router.get("/entitlement", response_model=EntitlementResponse)
def get_entitlement(
    claims: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
) -> EntitlementResponse:
    """Return the authenticated user's current entitlement snapshot.

    AC-5: Returns { tier, trial_analyses_remaining, credit_balance, can_generate }
    """
    user_id: str = claims["sub"]

    # Fetch user row with tier display_name
    user_result = (
        supabase.table("users")
        .select("trial_analyses_remaining, tier_id, tiers(display_name)")
        .eq("id", user_id)
        .is_("deleted_at", "null")
        .single()
        .execute()
    )
    if not user_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    row = user_result.data
    trial_remaining: int = row["trial_analyses_remaining"]
    tier_display: str = row["tiers"]["display_name"] if row.get("tiers") else "Unknown"

    # Credit balance: sum of credit_ledger deltas
    ledger_result = (
        supabase.rpc("sum_credit_balance", {"p_user_id": user_id}).execute()
    )
    # Fallback: if RPC not available, compute client-side
    credit_balance: int = 0
    if ledger_result.data is not None:
        credit_balance = int(ledger_result.data or 0)
    else:
        entries = (
            supabase.table("credit_ledger")
            .select("delta")
            .eq("user_id", user_id)
            .execute()
        )
        credit_balance = sum(e["delta"] for e in (entries.data or []))

    can_generate = trial_remaining > 0 or credit_balance > 0

    return EntitlementResponse(
        tier=tier_display,
        trial_analyses_remaining=trial_remaining,
        credit_balance=credit_balance,
        can_generate=can_generate,
    )
