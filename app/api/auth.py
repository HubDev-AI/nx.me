"""Auth API — registration, email verification & trial grant.

Story 2-1:
  POST /auth/register      — create account
  POST /auth/verify-email  — trigger trial grant after email confirmed
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from supabase import Client

import redis.asyncio as aioredis

from app.api.deps import get_current_user, get_redis, get_supabase
from app.entitlement.trial_grantor import TrialGrantor
from app.services.disposable_email import is_disposable_email
from app.services.rate_limiter import check_registration_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

# Minimum age for account creation (AC-U7)
_MIN_AGE_YEARS = 13


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    username: str = Field(min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_]+$")
    display_name: str = Field(min_length=1, max_length=50)
    birth_year: int | None = Field(default=None, ge=1900, le=2100)
    guest_session_token: str | None = None


class RegisterResponse(BaseModel):
    user_id: str
    username: str
    email_verification_required: bool


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    request: Request,
    body: RegisterRequest,
    x_device_fingerprint: Annotated[str | None, Header()] = None,
    supabase: Client = Depends(get_supabase),
    r: aioredis.Redis = Depends(get_redis),
) -> RegisterResponse:
    """Register a new account with email + password.

    AC-3: Device fingerprint rate limit — ≥3 attempts in 24h → HTTP 429
    AC-4: Disposable email → HTTP 422
    AC-6: Age gate via birth_year → is_minor flag
    AC-1: User row created with tier = default, trial_analyses_remaining = 0
          (trial credited only after email verification via TrialGrantor.grant)
    """
    # --- Rate limiting (AC-3) ---------------------------------------------
    # Prefer explicit fingerprint header; fall back to client IP to prevent
    # a single shared "unknown" bucket locking out all fingerprint-less clients.
    client_ip = request.client.host if request.client else "unknown"
    fingerprint = x_device_fingerprint or client_ip
    allowed = await check_registration_rate_limit(fingerprint, r)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many registration attempts from this device. Try again in 24 hours.",
        )

    # --- Disposable email check (AC-4) ------------------------------------
    if is_disposable_email(str(body.email)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Disposable email addresses are not permitted.",
        )

    # --- Age gate (AC-6) --------------------------------------------------
    is_minor: bool | None = None
    if body.birth_year is not None:
        # Compute age at request time — avoid module-level constant that
        # becomes stale across year boundaries (e.g. server started Dec 2026).
        age = date.today().year - body.birth_year
        is_minor = age < _MIN_AGE_YEARS

    # --- Fetch default tier -----------------------------------------------
    tier_result = (
        supabase.table("tiers")
        .select("id")
        .eq("is_default", True)
        .eq("is_active", True)
        .single()
        .execute()
    )
    if not tier_result.data:
        logger.error("No active default tier found in database")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Service configuration error.",
        )
    default_tier_id: str = tier_result.data["id"]

    # --- Create Supabase auth user ----------------------------------------
    try:
        auth_response = supabase.auth.admin.create_user(
            {
                "email": str(body.email),
                "password": body.password,
                "email_confirm": False,  # require email verification
            }
        )
    except Exception as exc:
        _handle_supabase_auth_error(exc)

    if not auth_response.user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account creation failed.",
        )

    user_id = str(auth_response.user.id)

    # --- Insert public.users row ------------------------------------------
    user_row: dict = {
        "id": user_id,
        "username": body.username,
        "display_name": body.display_name,
        "email": str(body.email),
        "tier_id": default_tier_id,
        "trial_analyses_remaining": 0,  # granted after email verification
        "email_verified": False,
        "guest_session_token": body.guest_session_token,
    }
    if is_minor is not None:
        user_row["is_minor"] = is_minor

    try:
        supabase.table("users").insert(user_row).execute()
    except Exception as exc:
        # Roll back auth user to avoid orphaned auth records
        try:
            supabase.auth.admin.delete_user(user_id)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to roll back auth user %s after users insert failure", user_id)
        logger.error("users INSERT failed for %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account creation failed.",
        ) from exc

    logger.info("Registered user %s (%s)", user_id, body.email)

    return RegisterResponse(
        user_id=user_id,
        username=body.username,
        email_verification_required=True,
    )


# ---------------------------------------------------------------------------
# Email verification → trial grant (AC-2)
# ---------------------------------------------------------------------------


class VerifyEmailResponse(BaseModel):
    trial_analyses_remaining: int
    message: str


@router.post("/verify-email", response_model=VerifyEmailResponse)
def verify_email(
    claims: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
) -> VerifyEmailResponse:
    """Trigger trial grant after email verification.

    Called by the mobile client immediately after the user clicks the
    verification link and the Supabase SDK exchanges the magic link for a
    valid JWT session.

    AC-2: TrialGrantor.grant(user_id) is idempotent — calling this endpoint
    twice does not double-grant trial analyses.
    """
    from uuid import UUID

    user_id_str: str = claims["sub"]

    # Verify that Supabase auth has confirmed the email
    try:
        auth_user = supabase.auth.admin.get_user_by_id(user_id_str)
    except Exception as exc:
        logger.error("Failed to fetch auth user %s: %s", user_id_str, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not verify email status.",
        )

    if not auth_user.user or not auth_user.user.email_confirmed_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email address has not been verified yet.",
        )

    # Mark email_verified in our users table
    supabase.table("users").update({"email_verified": True}).eq(
        "id", user_id_str
    ).execute()

    # Grant trial analyses (idempotent)
    grantor = TrialGrantor(supabase)
    grantor.grant(UUID(user_id_str))

    # Read updated count for response
    user_result = (
        supabase.table("users")
        .select("trial_analyses_remaining")
        .eq("id", user_id_str)
        .single()
        .execute()
    )
    remaining: int = user_result.data["trial_analyses_remaining"] if user_result.data else 0

    logger.info("Email verified and trial granted for user %s", user_id_str)
    return VerifyEmailResponse(
        trial_analyses_remaining=remaining,
        message="Email verified. Your free analyses are ready.",
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _handle_supabase_auth_error(exc: Exception) -> NoReturn:
    """Map Supabase auth errors to appropriate HTTP responses."""
    msg = str(exc).lower()
    if "already registered" in msg or "unique" in msg or "duplicate" in msg:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )
    if "password" in msg and ("weak" in msg or "short" in msg):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password does not meet requirements.",
        )
    logger.error("Supabase auth.admin.create_user failed: %s", exc)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Account creation failed.",
    )
