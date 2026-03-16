"""Auth API — registration, email verification, social login, logout & account deletion.

Story 2-1:
  POST /auth/register      — create account
  POST /auth/verify-email  — trigger trial grant after email confirmed

Story 2-2:
  POST /auth/login         — social login via id_token (Google / Apple)
  POST /auth/logout        — server-side session invalidation
  DELETE /auth/account     — soft delete + 180-day username reservation
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal, NoReturn

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from supabase import Client

import redis.asyncio as aioredis

from app.api.deps import get_current_user, get_redis, get_supabase
from app.api.middleware.auth import UserClaims
from app.config import settings
from app.entitlement.trial_grantor import TrialGrantor
from app.services.disposable_email import is_disposable_email
from slugify import slugify
from app.services.rate_limiter import (
    check_ip_registration_rate_limit,
    check_registration_rate_limit,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

# Minimum age for account creation (AC-U7)
_MIN_AGE_YEARS = 13

# Social providers accepted by the login endpoint
_ACCEPTED_PROVIDERS = frozenset({"google", "apple"})


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
    # --- Rate limiting (Story 2-2 AC-4): per-IP limit ≥4/hour → 429 ------
    client_ip = request.client.host if request.client else "unknown"
    ip_allowed = await check_ip_registration_rate_limit(client_ip, r)
    if not ip_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many registration attempts from this IP. Try again in 1 hour.",
        )

    # --- Rate limiting (AC-3): per-device fingerprint ≥3/24h → 429 ------
    # Prefer explicit fingerprint header; fall back to client IP to prevent
    # a single shared "unknown" bucket locking out all fingerprint-less clients.
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

    # --- Username availability (AC-FR3: reservation enforcement) ----------
    # Must be checked before auth user creation to avoid orphaned auth records.
    username_rows = (
        supabase.table("users")
        .select("id, deleted_at, username_reserved_until")
        .eq("username", body.username)
        .execute()
    )
    if username_rows.data:
        row = username_rows.data[0]
        if row.get("deleted_at") is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username is already taken.",
            )
        reserved_until_str = row.get("username_reserved_until")
        if reserved_until_str:
            reserved_until = datetime.fromisoformat(reserved_until_str)
            if reserved_until.tzinfo is None:
                reserved_until = reserved_until.replace(tzinfo=timezone.utc)
            if reserved_until > datetime.now(tz=timezone.utc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Username is temporarily reserved.",
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


# ===========================================================================
# Story 2-2 — Social Login, Logout & Account Deletion
# ===========================================================================

# ---------------------------------------------------------------------------
# Social Login — POST /auth/login
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    """Social login via id_token (AC-1).

    The mobile client completes the OAuth PKCE flow with the provider
    (Google / Apple), receives an id_token, and sends it here.  The backend
    never sees a redirect URI — implicit-flow tokens and custom URI schemes
    are rejected at the endpoint level.
    """

    provider: Literal["google", "apple"]
    id_token: str = Field(min_length=1)
    nonce: str | None = None  # required by Apple; optional for Google


class LoginResponse(BaseModel):
    user_id: str
    access_token: str
    refresh_token: str
    expires_at: int  # Unix timestamp


@router.post("/login", response_model=LoginResponse)
def social_login(
    body: LoginRequest,
    supabase: Client = Depends(get_supabase),
) -> LoginResponse:
    """Authenticate via a social provider id_token (Google or Apple).

    AC-1: id_token claims (iss, aud, exp, nonce) are validated by Supabase
    GoTrue when we call sign_in_with_id_token. Implicit-flow tokens are
    never accepted because we only accept `id_token` — not `access_token`
    or `code`.  Custom URI scheme redirects are rejected because the backend
    does not implement a redirect URI callback flow at all.
    """
    if body.provider not in _ACCEPTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Provider '{body.provider}' is not supported.",
        )

    # Exchange id_token for a Supabase session.
    # Supabase GoTrue validates iss, aud, exp, nonce internally (AC-A9).
    credentials: dict = {"provider": body.provider, "token": body.id_token}
    if body.nonce is not None:
        credentials["nonce"] = body.nonce

    try:
        auth_response = supabase.auth.sign_in_with_id_token(credentials)
    except Exception as exc:
        msg = str(exc).lower()
        logger.warning("sign_in_with_id_token failed for provider %s: %s", body.provider, exc)
        if "invalid" in msg or "expired" in msg or "nonce" in msg or "claim" in msg:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Social login token is invalid or expired.",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication service error.",
        )

    if not auth_response.session or not auth_response.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Social login failed.",
        )

    session = auth_response.session
    user = auth_response.user
    user_id = str(user.id)

    # Fetch default tier for new social users (existing users already have one;
    # ignore_duplicates=True ensures we don't overwrite it).
    tier_result = (
        supabase.table("tiers")
        .select("id")
        .eq("is_default", True)
        .eq("is_active", True)
        .single()
        .execute()
    )
    if not tier_result.data:
        logger.error("No active default tier found — cannot create social user %s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Service configuration error.",
        )
    default_tier_id: str = tier_result.data["id"]

    # Build a DB-safe username: email prefix slugified to [a-zA-Z0-9_],
    # or fallback to first 20 chars of the UUID (also slugified).
    raw_username = user.email.split("@")[0] if user.email else user_id[:20]
    auto_username = slugify(raw_username, separator="_", lowercase=False, max_length=30) or "user"

    # Upsert public.users row — new social users won't have a row yet.
    # On conflict (existing account) do nothing to preserve existing data.
    try:
        supabase.table("users").upsert(
            {
                "id": user_id,
                "email": user.email or "",
                "username": auto_username,
                "display_name": (user.user_metadata or {}).get("full_name", "") or (user.email or user_id),
                "email_verified": True,
                "trial_analyses_remaining": 0,
                "tier_id": default_tier_id,
            },
            on_conflict="id",
            ignore_duplicates=True,
        ).execute()
    except Exception as exc:
        # Non-fatal: session was created, profile upsert is best-effort.
        logger.error("users upsert failed for social user %s: %s", user_id, exc)

    logger.info("Social login successful for user %s (provider=%s)", user_id, body.provider)
    return LoginResponse(
        user_id=user_id,
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_at=int(session.expires_at) if session.expires_at else 0,
    )


# ---------------------------------------------------------------------------
# Logout — POST /auth/logout
# ---------------------------------------------------------------------------


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    claims: UserClaims = Depends(get_current_user),
    authorization: Annotated[str | None, Header()] = None,
    supabase: Client = Depends(get_supabase),
) -> None:
    """Invalidate the current session server-side (AC-2).

    Calls supabase.auth.admin.sign_out() which revokes the token in
    Supabase GoTrue within ≤1 second.  Subsequent requests bearing this
    token will receive HTTP 401.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    token = authorization.removeprefix("Bearer ").strip()
    user_id: str = claims["sub"]

    try:
        supabase.auth.admin.sign_out(token)
        logger.info("Session invalidated for user %s", user_id)
    except Exception as exc:
        logger.error("sign_out failed for user %s: %s", user_id, exc)
        # Do not surface the error — the client should treat 204 as success.
        # The token will expire naturally even if server revocation failed.


# ---------------------------------------------------------------------------
# Account Deletion — DELETE /auth/account
# ---------------------------------------------------------------------------


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    claims: UserClaims = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
) -> None:
    """Permanently delete the authenticated user's account (AC-3).

    Actions:
    1. Soft-delete the public.users row (deleted_at = NOW()).
    2. Reserve the username for 180 days (username_reserved_until).
    3. Delete the Supabase auth identity (removes login capability).

    Primary storage (images, glow-up results) is deleted asynchronously
    within 72 hours by a background job (deferred to Story 6-x).
    Shareable card URLs return HTTP 410 once deleted_at is set (Story 6-1).
    """
    user_id: str = claims["sub"]
    now_utc = datetime.now(tz=timezone.utc)
    reserved_until = now_utc + timedelta(days=settings.USERNAME_RESERVATION_DAYS)

    # --- Soft delete + username reservation --------------------------------
    try:
        supabase.table("users").update(
            {
                "deleted_at": now_utc.isoformat(),
                "username_reserved_until": reserved_until.isoformat(),
            }
        ).eq("id", user_id).is_("deleted_at", "null").execute()
    except Exception as exc:
        logger.error("users soft-delete failed for %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account deletion failed.",
        ) from exc

    # --- Remove Supabase auth identity -----------------------------------
    try:
        supabase.auth.admin.delete_user(user_id)
        logger.info("Account deleted for user %s; username reserved until %s", user_id, reserved_until.date())
    except Exception as exc:
        logger.error("auth.admin.delete_user failed for %s: %s", user_id, exc)
        # Soft delete already committed — log the failure, do not surface it.
        # A cleanup job can retry auth deletion using the deleted_at flag.
