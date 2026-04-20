"""Auth API — registration, email verification, login, logout & account deletion.

Story 2-1:
  POST /auth/register      — create account (gated by AUTH_PROVIDER_EMAIL_ENABLED)
  POST /auth/verify-email  — trigger trial grant after email confirmed

Story 2-2:
  POST /auth/login         — social login via id_token (Google / Apple, gated)
  POST /auth/email-login   — email + password login (gated by AUTH_PROVIDER_EMAIL_ENABLED)
  POST /auth/tiktok-login  — TikTok OAuth code exchange (gated by AUTH_PROVIDER_TIKTOK_ENABLED)
  POST /auth/refresh       — exchange refresh_token for new session
  POST /auth/logout        — server-side session invalidation
  DELETE /auth/account     — hard-delete account + 180-day username reservation
  GET  /auth/providers     — list enabled auth providers (for mobile UI)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Annotated, Literal, NoReturn

if TYPE_CHECKING:
    from app.payment.ports import PaymentPort
from uuid import UUID, uuid4

from arq import ArqRedis
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, StringConstraints, field_validator
from slugify import slugify
from supabase import Client

import redis.asyncio as aioredis

from app.api.deps import (
    get_arq_pool,
    get_client_ip,
    get_credit_ledger,
    get_current_user,
    get_image_repo,
    get_orphaned_storage_repo,
    get_payment_adapter,
    get_redis,
    get_stripe_customer_dlq_repo,
    get_supabase,
    get_user_repo,
)
from app.entitlement.ledger import CreditLedger
from app.api.middleware.auth import UserClaims
from app.config import settings
from app.db.async_helpers import run_sync
from app.repositories.image_repo import ImageRepository
from app.repositories.orphaned_storage_repo import OrphanedStorageKeyRepository
from app.repositories.stripe_customer_dlq import StripeCustomerDLQRepository
from app.repositories.user_repo import UserRepository
from app.services.disposable_email import is_disposable_email
from app.services.rate_limiter import (
    check_delete_account_rate_limit,
    check_ip_registration_rate_limit,
    check_login_rate_limit,
    check_registration_rate_limit,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


# Minimum age for account creation (AC-U7)
_MIN_AGE_YEARS = 13

# Social providers accepted by the /auth/login endpoint (id_token flow).
# TikTok uses a separate endpoint (/auth/tiktok-login) because it doesn't
# support id_token verification via Supabase GoTrue.
_ACCEPTED_PROVIDERS = frozenset({"google", "apple"})


def _get_enabled_providers() -> list[str]:
    """Return the list of auth providers currently enabled via config flags."""
    providers: list[str] = []
    if settings.AUTH_PROVIDER_TIKTOK_ENABLED:
        providers.append("tiktok")
    if settings.AUTH_PROVIDER_GOOGLE_ENABLED:
        providers.append("google")
    if settings.AUTH_PROVIDER_APPLE_ENABLED:
        providers.append("apple")
    if settings.AUTH_PROVIDER_EMAIL_ENABLED:
        providers.append("email")
    return providers


def _derive_tiktok_password(open_id: str) -> str:
    """Derive a deterministic password for TikTok users.

    Used to create Supabase auth accounts for TikTok users who don't have
    a real password.  The HMAC is keyed with SECRET_KEY so passwords are
    unique per deployment and can never be guessed from the open_id alone.
    """
    return hmac.new(
        settings.SECRET_KEY.encode(),
        f"tiktok:{open_id}".encode(),
        hashlib.sha256,
    ).hexdigest()


# ---------------------------------------------------------------------------
# GET /auth/providers — enabled auth providers (for mobile UI)
# ---------------------------------------------------------------------------


class FeatureFlags(BaseModel):
    onboarding_enabled: bool


class ProvidersResponse(BaseModel):
    providers: list[str]
    features: FeatureFlags


@router.get("/providers", response_model=ProvidersResponse)
async def get_providers() -> ProvidersResponse:
    """Return enabled auth providers and feature flags.

    The mobile app calls this on startup to decide which login buttons
    to render and which features to show.  No authentication required.
    """
    return ProvidersResponse(
        providers=_get_enabled_providers(),
        features=FeatureFlags(
            onboarding_enabled=settings.FEATURE_ONBOARDING_ENABLED,
        ),
    )


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    username: str = Field(min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_]+$")
    display_name: str = Field(min_length=1, max_length=50)
    birth_year: int | None = Field(default=None, ge=1900, le=2100)

    @field_validator("display_name")
    @classmethod
    def display_name_no_html_chars(cls, v: str) -> str:
        if any(ch in v for ch in '<>"'):
            raise ValueError('display_name must not contain <, >, or " characters')
        return v


class RegisterResponse(BaseModel):
    user_id: str
    username: str
    access_token: str
    refresh_token: str
    expires_at: int


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
    x_install_uuid: Annotated[str | None, Header()] = None,
    supabase: Client = Depends(get_supabase),
    r: aioredis.Redis = Depends(get_redis),
    user_repo: UserRepository = Depends(get_user_repo),
) -> RegisterResponse:
    """Register a new account with email + password.

    AC-3: Device fingerprint rate limit — ≥3 attempts in 24h → HTTP 429
    AC-4: Disposable email → HTTP 422
    AC-6: Age gate via birth_year → is_minor flag
    AC-1: User row created; signup grant applied via ARQ job (Unit 9).
    """
    # --- Provider gate: reject if email auth is disabled ---------------------
    if not settings.AUTH_PROVIDER_EMAIL_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email registration is not enabled.",
        )

    # --- Rate limiting (Story 2-2 AC-4): per-IP limit ≥4/hour → 429 ------
    client_ip = get_client_ip(request)
    if not client_ip:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot determine client IP address.",
        )
    ip_allowed, ip_ttl = await check_ip_registration_rate_limit(client_ip, r)
    if not ip_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many registration attempts from this IP. Try again in 1 hour.",
            headers={"Retry-After": str(ip_ttl)},
        )

    # --- Rate limiting (AC-3): per-device fingerprint ≥3/24h → 429 ------
    # Prefer explicit fingerprint header; fall back to client IP to prevent
    # a single shared "unknown" bucket locking out all fingerprint-less clients.
    fingerprint = x_device_fingerprint or client_ip
    allowed, fp_ttl = await check_registration_rate_limit(fingerprint, r)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many registration attempts from this device. Try again in 24 hours.",
            headers={"Retry-After": str(fp_ttl)},
        )

    # --- Disposable email check (AC-4) ------------------------------------
    if is_disposable_email(str(body.email)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Disposable email addresses are not permitted.",
        )

    # --- Username availability (AC-FR3: reservation enforcement) ----------
    # Must be checked before auth user creation to avoid orphaned auth records.
    result = await run_sync(user_repo.check_username_availability, body.username)
    if not result["available"]:
        reason = result.get("reason", "taken")
        detail = (
            "Username is reserved from a recent account deletion."
            if reason == "reserved"
            else "Username is already taken."
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

    # --- Age gate (AC-6) --------------------------------------------------
    is_minor: bool | None = None
    if body.birth_year is not None:
        # Compute age at request time — avoid module-level constant that
        # becomes stale across year boundaries (e.g. server started Dec 2026).
        age = date.today().year - body.birth_year
        is_minor = age < _MIN_AGE_YEARS

    # --- Create Supabase auth user ----------------------------------------
    logger.info("Creating auth user for %s / %s", body.email, body.username)
    try:
        auth_response = await run_sync(
            user_repo.auth_create_user, str(body.email), body.password
        )
    except Exception as exc:
        logger.error("auth_create_user raised %s: %s", type(exc).__name__, exc)
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
        "email_verified": True,  # auto-confirmed via admin API
    }
    if is_minor is not None:
        user_row["is_minor"] = is_minor

    try:
        await run_sync(user_repo.insert, user_row)
    except Exception as exc:
        # Roll back auth user to avoid orphaned auth records
        try:
            await run_sync(user_repo.auth_delete_user, user_id)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to roll back auth user %s after users insert failure", user_id
            )
        logger.error("users INSERT failed for %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account creation failed.",
        ) from exc

    # Trial credit grant removed — signup grants are handled by Unit 9
    # (fingerprint-based signup grant via ARQ job). No trial credits here.

    # --- Signup grant (Unit 9) -------------------------------------------
    # Fire after merge so the 2x-cap accounting in the RPC is correct.
    await _apply_signup_grant(supabase, user_id, x_install_uuid)

    # --- Auto-login: sign in to get session tokens -----------------------
    # IMPORTANT: use a SEPARATE Supabase client for sign_in_with_password.
    # sign_in_with_password mutates the client's internal auth session,
    # which would corrupt the shared service-role client for all future requests.
    from app.db.client import get_supabase_service

    login_client = get_supabase_service()
    try:
        session_response = await run_sync(
            login_client.auth.sign_in_with_password,
            {"email": str(body.email), "password": body.password},
        )
    except Exception as exc:
        logger.error("Auto-login after registration failed for %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account created but login failed. Please log in manually.",
        ) from exc

    if not session_response.session:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account created but login failed. Please log in manually.",
        )

    session = session_response.session
    logger.info("Registered and auto-logged in user %s", user_id)

    return RegisterResponse(
        user_id=user_id,
        username=body.username,
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_at=int(session.expires_at) if session.expires_at else 0,
    )


# ---------------------------------------------------------------------------
# Email verification → trial grant (AC-2)
# ---------------------------------------------------------------------------


class VerifyEmailResponse(BaseModel):
    trial_analyses_remaining: int
    message: str


@router.post("/verify-email", response_model=VerifyEmailResponse)
async def verify_email(
    claims: UserClaims = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
    user_repo: UserRepository = Depends(get_user_repo),
) -> VerifyEmailResponse:
    """Trigger trial grant after email verification.

    Called by the mobile client immediately after the user clicks the
    verification link and the Supabase SDK exchanges the magic link for a
    valid JWT session.

    AC-2: previously triggered TrialGrantor.grant (removed Unit 7); kept
    as the email-verification confirmation endpoint for mobile compat.
    """
    user_id_str: str = claims["sub"]

    # Verify that Supabase auth has confirmed the email
    # M-1: Wrap sync Supabase calls to avoid blocking the event loop
    try:
        auth_user = await run_sync(user_repo.auth_get_user, user_id_str)
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
    await run_sync(user_repo.set_email_verified, user_id_str)

    # Trial grant removed — signup grants handled by Unit 9 (fingerprint-based ARQ job).
    # trial_analyses_remaining column dropped in migration 0054; always 0 now.

    logger.info("Email verified for user %s", user_id_str)
    return VerifyEmailResponse(
        trial_analyses_remaining=0,
        message="Email verified. Your free analyses are ready.",
    )


# ---------------------------------------------------------------------------
# Current User Profile — GET /auth/me
# ---------------------------------------------------------------------------


class MeResponse(BaseModel):
    user_id: str
    username: str
    display_name: str
    email: str


@router.get("/me", response_model=MeResponse)
async def get_me(
    claims: UserClaims = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_user_repo),
) -> MeResponse:
    """Return the authenticated user's profile.

    Requires a valid Bearer JWT. Extracts user_id from the token's ``sub``
    claim and queries the users table for the core profile fields.
    """
    user_id: str = claims["sub"]

    row = await run_sync(user_repo.get_profile_by_id, user_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found.",
        )

    return MeResponse(
        user_id=row["id"],
        username=row["username"],
        display_name=row["display_name"],
        email=row["email"],
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_invalid_token_error(exc: Exception) -> bool:
    """Check if Supabase error indicates invalid/expired token.

    NOTE: String matching is fragile across Supabase versions.
    Update patterns if Supabase client error format changes.
    """
    msg = str(exc).lower()
    return any(keyword in msg for keyword in ("invalid", "expired", "nonce", "claim"))


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
    # "User not allowed" can mean duplicate email OR password policy violation.
    # Supabase GoTrue uses this for multiple rejection reasons.
    if "not allowed" in msg:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )
    logger.error("Supabase auth.admin.create_user failed: %s", exc)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Account creation failed.",
    )


async def _apply_signup_grant(
    supabase: Client,
    user_id: str,
    x_install_uuid: str | None,
) -> None:
    """Invoke the ``credit_apply_signup_grant`` RPC after account creation.

    Web signups (no ``X-Install-UUID`` header) pass all-NULL hash/salt args;
    the RPC grants unconditionally and writes no fingerprint row. Mobile
    signups supply all three fingerprint args; the RPC deduplicates via the
    ``signup_grants_issued`` table.

    Non-fatal: errors are logged but never bubble to the caller — the user
    account is already created and the session tokens already returned by the
    time this runs. A failed grant is visible in the credit_ledger audit trail
    (or its absence) and can be replayed by ops if needed.
    """
    from app.entitlement.fingerprint import (
        compute_deterministic_hash,
        compute_protected_hash,
        generate_salt,
        get_primary_secret,
    )

    deterministic_hash: str | None = None
    protected_hash: str | None = None
    salt: str | None = None

    if x_install_uuid is not None:
        server_secret = get_primary_secret()
        det_bytes = compute_deterministic_hash(x_install_uuid, server_secret)
        salt_bytes = generate_salt()
        prot_bytes = compute_protected_hash(x_install_uuid, salt_bytes)
        # Supabase expects BYTEA as hex-encoded strings prefixed with \x
        deterministic_hash = f"\\x{det_bytes.hex()}"
        protected_hash = f"\\x{prot_bytes.hex()}"
        salt = f"\\x{salt_bytes.hex()}"

    try:
        await run_sync(
            supabase.rpc(
                "credit_apply_signup_grant",
                {
                    "p_user_id": user_id,
                    "p_deterministic_hash": deterministic_hash,
                    "p_protected_hash": protected_hash,
                    "p_salt": salt,
                    "p_signup_grant_milli": settings.SIGNUP_GRANT_MILLI,
                },
            ).execute
        )
    except Exception:
        logger.exception(
            "credit_apply_signup_grant RPC failed for user %s (install_uuid present=%s)",
            user_id,
            x_install_uuid is not None,
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
    username: str
    access_token: str
    refresh_token: str
    expires_at: int  # Unix timestamp


class RefreshRequest(BaseModel):
    """Refresh an expired session using a refresh_token."""

    refresh_token: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1)
    ]


async def _resolve_login_username(
    user_repo: UserRepository,
    user_id: str,
    *,
    fallback: str | None = None,
) -> str:
    """Return the canonical username for login responses."""
    row = await run_sync(user_repo.get_profile_by_id, user_id)
    username = row.get("username") if row else None
    if isinstance(username, str) and username:
        return username
    if fallback:
        logger.warning("Falling back to derived username for user %s", user_id)
        return fallback
    logger.error("No username found for authenticated user %s", user_id)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="User profile is incomplete.",
    )


@router.post("/login", response_model=LoginResponse)
async def social_login(
    request: Request,
    body: LoginRequest,
    x_install_uuid: Annotated[str | None, Header()] = None,
    supabase: Client = Depends(get_supabase),
    r: aioredis.Redis = Depends(get_redis),
    user_repo: UserRepository = Depends(get_user_repo),
) -> LoginResponse:
    """Authenticate via a social provider id_token (Google or Apple).

    AC-1: id_token claims (iss, aud, exp, nonce) are validated by Supabase
    GoTrue when we call sign_in_with_id_token. Implicit-flow tokens are
    never accepted because we only accept `id_token` — not `access_token`
    or `code`.  Custom URI scheme redirects are rejected because the backend
    does not implement a redirect URI callback flow at all.

    CS-1 AC-4: Per-IP rate limit on login (same window as registration).
    """
    # --- Provider gate: reject if this specific provider is disabled ------
    _provider_flag = {
        "google": settings.AUTH_PROVIDER_GOOGLE_ENABLED,
        "apple": settings.AUTH_PROVIDER_APPLE_ENABLED,
    }
    if not _provider_flag.get(body.provider, False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"The '{body.provider}' login method is not enabled.",
        )

    # Per-IP rate limit (CS-1 T-3)
    client_ip = get_client_ip(request)
    if not client_ip:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot determine client IP address.",
        )
    login_allowed, login_ttl = await check_login_rate_limit(client_ip, r)
    if not login_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts from this IP. Try again later.",
            headers={"Retry-After": str(login_ttl)},
        )

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

    from app.db.client import get_supabase_service

    login_client = get_supabase_service()
    try:
        auth_response = await run_sync(
            login_client.auth.sign_in_with_id_token, credentials
        )
    except Exception as exc:
        logger.warning(
            "sign_in_with_id_token failed for provider %s: %s", body.provider, exc
        )
        if _is_invalid_token_error(exc):
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

    # Build a DB-safe username: email prefix slugified to [a-zA-Z0-9_],
    # or fallback to first 20 chars of the UUID (also slugified).
    raw_username = user.email.split("@")[0] if user.email else user_id[:20]
    auto_username = (
        slugify(raw_username, separator="_", lowercase=False, max_length=30) or "user"
    )

    # P2-5: Guarantee unique username — retry with random suffix on collision (M-2/M-3)
    # Also consults username_reservations so a recently-deleted handle can't be
    # silently claimed by a new social signup (COR-001).
    base_username = auto_username
    max_retries = 3
    for attempt in range(max_retries):
        # Check if username is taken or reserved
        result = await run_sync(
            user_repo.check_username_availability, auto_username, user_id
        )
        if not result["available"]:
            # Either "taken" (by another active user) or "reserved" (from a
            # recent account deletion). Either way, generate a new suffix and
            # re-check before attempting the upsert.
            suffix = f"_{uuid4().hex[:6]}"
            # Truncate base to stay within 30-char limit (M-3)
            if len(base_username) + len(suffix) > 30:
                base_username = base_username[: 30 - len(suffix)]
            auto_username = f"{base_username}{suffix}"
            continue

        # Upsert public.users row — new social users won't have a row yet.
        # On conflict (existing account) do nothing to preserve existing data.
        try:
            await run_sync(
                user_repo.upsert,
                {
                    "id": user_id,
                    "email": user.email or "",
                    "username": auto_username,
                    "display_name": (user.user_metadata or {}).get("full_name", "")
                    or (user.email or user_id),
                    "email_verified": True,
                },
                "id",
                True,
            )
            break
        except Exception as exc:
            if "unique" in str(exc).lower() and attempt < max_retries - 1:
                # Username collision on insert, retry with new suffix
                suffix = f"_{uuid4().hex[:6]}"
                if len(base_username) + len(suffix) > 30:
                    base_username = base_username[: 30 - len(suffix)]
                auto_username = f"{base_username}{suffix}"
                continue
            logger.error("users upsert failed for social user %s: %s", user_id, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user profile. Please try again.",
            ) from exc

    # --- Signup grant (Unit 9) — new accounts only -----------------------
    # Supabase upsert (ignore_duplicates=True) gives no "was inserted" signal.
    # Use created_at recency: if the auth account was created within the last
    # 60 s this is a genuine new signup; existing users returning via social
    # login have a created_at well in the past.
    _now = datetime.now(tz=timezone.utc)
    _account_age = _now - user.created_at.replace(tzinfo=timezone.utc)
    if _account_age < timedelta(seconds=60):
        await _apply_signup_grant(supabase, user_id, x_install_uuid)

    username = await _resolve_login_username(user_repo, user_id, fallback=auto_username)

    logger.info(
        "Social login successful for user %s (provider=%s)", user_id, body.provider
    )
    return LoginResponse(
        user_id=user_id,
        username=username,
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_at=int(session.expires_at) if session.expires_at else 0,
    )


# ---------------------------------------------------------------------------
# Email/Password Login — POST /auth/email-login
# ---------------------------------------------------------------------------


class EmailLoginRequest(BaseModel):
    """Email + password login.

    Used by the mobile app login screen which sends email/password credentials
    directly (as opposed to social login which sends a provider id_token).
    """

    email: EmailStr
    password: str = Field(min_length=1)


@router.post("/email-login", response_model=LoginResponse)
async def email_login(
    request: Request,
    body: EmailLoginRequest,
    supabase: Client = Depends(get_supabase),
    r: aioredis.Redis = Depends(get_redis),
    user_repo: UserRepository = Depends(get_user_repo),
) -> LoginResponse:
    """Authenticate with email and password.

    Calls Supabase auth.sign_in_with_password and returns the session tokens.
    Applies the same per-IP rate limiting as social login (CS-1 AC-4).
    """
    # --- Provider gate: reject if email auth is disabled ---------------------
    if not settings.AUTH_PROVIDER_EMAIL_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email login is not enabled.",
        )

    # Per-IP rate limit (same as social login)
    client_ip = get_client_ip(request)
    if not client_ip:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot determine client IP address.",
        )
    login_allowed, login_ttl = await check_login_rate_limit(client_ip, r)
    if not login_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts from this IP. Try again later.",
            headers={"Retry-After": str(login_ttl)},
        )

    # Sign in with Supabase email/password auth
    from app.db.client import get_supabase_service

    login_client = get_supabase_service()
    try:
        auth_response = await run_sync(
            login_client.auth.sign_in_with_password,
            {"email": str(body.email), "password": body.password},
        )
    except Exception as exc:
        msg = str(exc).lower()
        logger.warning("sign_in_with_password failed for %s: %s", body.email, exc)
        if (
            "invalid" in msg
            or "credentials" in msg
            or "wrong" in msg
            or "not confirmed" in msg
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication service error.",
        )

    if not auth_response.session or not auth_response.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    session = auth_response.session
    user_id = str(auth_response.user.id)
    username = await _resolve_login_username(user_repo, user_id)

    logger.info("Email login successful for user %s", user_id)
    return LoginResponse(
        user_id=user_id,
        username=username,
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_at=int(session.expires_at) if session.expires_at else 0,
    )


# ---------------------------------------------------------------------------
# TikTok Login — POST /auth/tiktok-login
# ---------------------------------------------------------------------------


class TikTokLoginRequest(BaseModel):
    """TikTok authorization code from the native SDK (react-native-tiktok).

    The mobile app uses the TikTok native SDK which handles the OAuth flow
    natively and returns an auth_code (+ code_verifier on Android).
    The backend exchanges this code for an access_token via TikTok's API.
    """

    auth_code: str = Field(min_length=1)
    code_verifier: str | None = None  # Provided by Android SDK for PKCE


@router.post("/tiktok-login", response_model=LoginResponse)
async def tiktok_login(
    request: Request,
    body: TikTokLoginRequest,
    x_install_uuid: Annotated[str | None, Header()] = None,
    supabase: Client = Depends(get_supabase),
    r: aioredis.Redis = Depends(get_redis),
    user_repo: UserRepository = Depends(get_user_repo),
) -> LoginResponse:
    """Authenticate via TikTok OAuth2 authorization code.

    Flow:
    1. Exchange the authorization code for an access_token via TikTok API.
    2. Fetch the user's TikTok profile (open_id, display_name).
    3. Find or create a Supabase auth user linked to this TikTok identity.
    4. Return session tokens.

    TikTok doesn't produce an id_token that Supabase GoTrue can verify
    directly, so we use a deterministic-password approach: each TikTok
    user gets a Supabase auth account with a synthetic email and an
    HMAC-derived password.  This gives us real Supabase sessions with
    working token refresh.
    """
    # --- Provider gate ---
    if not settings.AUTH_PROVIDER_TIKTOK_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="TikTok login is not enabled.",
        )

    # --- Credential gate ---
    if not settings.TIKTOK_CLIENT_KEY or not settings.TIKTOK_CLIENT_SECRET:
        logger.error(
            "TikTok login attempted but TIKTOK_CLIENT_KEY/SECRET not configured"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TikTok login is not configured.",
        )

    # --- Per-IP rate limit (same window as other login methods) ---
    client_ip = get_client_ip(request)
    if not client_ip:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot determine client IP address.",
        )
    login_allowed, login_ttl = await check_login_rate_limit(client_ip, r)
    if not login_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts from this IP. Try again later.",
            headers={"Retry-After": str(login_ttl)},
        )

    # --- Step 1+2: Exchange code + fetch user profile (single httpx client) ---
    from app.services.tiktok_auth import TikTokAuthError, authenticate

    try:
        open_id, tiktok_user = await authenticate(
            code=body.auth_code,
            code_verifier=body.code_verifier,
        )
    except TikTokAuthError as exc:
        logger.warning("TikTok authentication failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="TikTok authentication failed. Please try again.",
        ) from exc

    # --- Step 3: Find or create Supabase user ---
    synthetic_email = f"tiktok_{open_id}@{settings.TIKTOK_SYNTHETIC_EMAIL_DOMAIN}"
    derived_password = _derive_tiktok_password(open_id)

    # Check if user already exists by tiktok_open_id
    existing_user = await run_sync(user_repo.find_by_tiktok_open_id, open_id)

    from app.db.client import get_supabase_service

    if existing_user:
        # --- Existing user: sign in with derived password ---
        login_client = get_supabase_service()
        try:
            session_response = await run_sync(
                login_client.auth.sign_in_with_password,
                {"email": synthetic_email, "password": derived_password},
            )
        except Exception as exc:
            logger.error(
                "TikTok sign-in failed for existing user %s: %s",
                existing_user["id"],
                exc,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Authentication service error.",
            )

        if not session_response.session:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Authentication service error.",
            )

        session = session_response.session

        logger.info("TikTok login successful for existing user %s", existing_user["id"])
        existing_username = await _resolve_login_username(
            user_repo,
            existing_user["id"],
            fallback=existing_user.get("username"),
        )
        return LoginResponse(
            user_id=existing_user["id"],
            username=existing_username,
            access_token=session.access_token,
            refresh_token=session.refresh_token,
            expires_at=int(session.expires_at) if session.expires_at else 0,
        )

    # --- New user: create Supabase auth account + users row ---
    # Create auth user with synthetic email and derived password
    try:
        auth_response = await run_sync(
            user_repo.auth_create_user,
            synthetic_email,
            derived_password,
        )
    except Exception as exc:
        logger.error(
            "Failed to create Supabase auth user for TikTok %s: %s", open_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account creation failed.",
        )

    if not auth_response.user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account creation failed.",
        )

    user_id = str(auth_response.user.id)

    # Generate a unique username from TikTok display_name
    raw_username = tiktok_user.display_name or f"user_{open_id[:8]}"
    auto_username = (
        slugify(raw_username, separator="_", lowercase=False, max_length=30) or "user"
    )

    base_username = auto_username
    max_retries = 3
    for attempt in range(max_retries):
        # Check if username is taken or reserved (COR-001)
        result = await run_sync(
            user_repo.check_username_availability, auto_username, user_id
        )
        if not result["available"]:
            # Either "taken" (by another active user) or "reserved" (from a
            # recent account deletion). Generate a new suffix and re-check.
            suffix = f"_{uuid4().hex[:6]}"
            if len(base_username) + len(suffix) > 30:
                base_username = base_username[: 30 - len(suffix)]
            auto_username = f"{base_username}{suffix}"
            continue

        try:
            await run_sync(
                user_repo.insert,
                {
                    "id": user_id,
                    "email": synthetic_email,
                    "username": auto_username,
                    "display_name": tiktok_user.display_name or auto_username,
                    "email_verified": True,
                    "tiktok_open_id": open_id,
                },
            )
            break
        except Exception as exc:
            exc_msg = str(exc).lower()
            # tiktok_open_id collision → concurrent first-login race.
            # Roll back this auth user and fall through to the existing-user sign-in path.
            if "tiktok_open_id" in exc_msg or (
                "unique" in exc_msg and "tiktok" in exc_msg
            ):
                try:
                    await run_sync(user_repo.auth_delete_user, user_id)
                except Exception:
                    logger.exception(
                        "Failed to roll back auth user %s after tiktok_open_id race",
                        user_id,
                    )
                logger.info(
                    "tiktok_open_id race detected for %s, falling back to sign-in",
                    open_id,
                )
                # Re-fetch the user that won the race and sign them in
                race_winner = await run_sync(user_repo.find_by_tiktok_open_id, open_id)
                if race_winner:
                    login_client = get_supabase_service()
                    session_response = await run_sync(
                        login_client.auth.sign_in_with_password,
                        {"email": synthetic_email, "password": derived_password},
                    )
                    if session_response.session:
                        race_username = await _resolve_login_username(
                            user_repo,
                            race_winner["id"],
                            fallback=race_winner.get("username"),
                        )
                        return LoginResponse(
                            user_id=race_winner["id"],
                            username=race_username,
                            access_token=session_response.session.access_token,
                            refresh_token=session_response.session.refresh_token,
                            expires_at=int(session_response.session.expires_at)
                            if session_response.session.expires_at
                            else 0,
                        )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Account creation failed. Please try again.",
                )
            # Username collision → retry with new suffix
            if "unique" in exc_msg and attempt < max_retries - 1:
                suffix = f"_{uuid4().hex[:6]}"
                if len(base_username) + len(suffix) > 30:
                    base_username = base_username[: 30 - len(suffix)]
                auto_username = f"{base_username}{suffix}"
                continue
            # Roll back auth user
            try:
                await run_sync(user_repo.auth_delete_user, user_id)
            except Exception:
                logger.exception("Failed to roll back auth user %s", user_id)
            logger.error("users INSERT failed for TikTok user %s: %s", user_id, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Account creation failed.",
            ) from exc

    # Trial credit grant removed — signup grants handled by Unit 9 (fingerprint-based ARQ job).

    # --- Signup grant (Unit 9) -------------------------------------------
    await _apply_signup_grant(supabase, user_id, x_install_uuid)

    # Sign in to get session tokens
    login_client = get_supabase_service()
    try:
        session_response = await run_sync(
            login_client.auth.sign_in_with_password,
            {"email": synthetic_email, "password": derived_password},
        )
    except Exception as exc:
        logger.error(
            "Auto-login after TikTok registration failed for %s: %s", user_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account created but login failed. Please try again.",
        ) from exc

    if not session_response.session:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account created but login failed. Please try again.",
        )

    session = session_response.session
    logger.info(
        "TikTok registration + login successful for user %s (open_id=%s)",
        user_id,
        open_id,
    )
    new_username = await _resolve_login_username(
        user_repo, user_id, fallback=auto_username
    )

    return LoginResponse(
        user_id=user_id,
        username=new_username,
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_at=int(session.expires_at) if session.expires_at else 0,
    )


# ---------------------------------------------------------------------------
# Token Refresh — POST /auth/refresh
# ---------------------------------------------------------------------------


@router.post("/refresh", response_model=LoginResponse)
async def refresh_token(
    request: Request,
    body: RefreshRequest,
    supabase: Client = Depends(get_supabase),
    r: aioredis.Redis = Depends(get_redis),
    user_repo: UserRepository = Depends(get_user_repo),
) -> LoginResponse:
    """Exchange a refresh_token for a new session (access + refresh tokens).

    No auth dependency is required — the caller is refreshing precisely
    because their access token has expired.  The refresh_token itself is
    validated by Supabase GoTrue.

    Per-IP rate limited to block refresh-token stuffing with stolen or
    brute-forced tokens. Uses the same `check_login_rate_limit` window as
    /v1/auth/login so an attacker can't side-step login throttling by hammering
    /refresh.
    """
    client_ip = get_client_ip(request)
    if not client_ip:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot determine client IP address.",
        )
    login_allowed, login_ttl = await check_login_rate_limit(client_ip, r)
    if not login_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many refresh attempts from this IP. Try again later.",
            headers={"Retry-After": str(login_ttl)},
        )

    from app.db.client import get_supabase_service

    refresh_client = get_supabase_service()
    try:
        auth_response = await run_sync(
            refresh_client.auth.refresh_session, body.refresh_token
        )
    except Exception as exc:
        logger.warning("refresh_session failed: %s", exc)
        if _is_invalid_token_error(exc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token is invalid or expired.",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication service error.",
        )

    if not auth_response.session or not auth_response.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session refresh failed.",
        )

    session = auth_response.session
    user_id = str(auth_response.user.id)
    username = await _resolve_login_username(user_repo, user_id)

    logger.info("Token refreshed for user %s", user_id)
    return LoginResponse(
        user_id=user_id,
        username=username,
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_at=int(session.expires_at) if session.expires_at else 0,
    )


# ---------------------------------------------------------------------------
# Logout — POST /auth/logout
# ---------------------------------------------------------------------------


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def logout(
    claims: UserClaims = Depends(get_current_user),
    authorization: Annotated[str | None, Header()] = None,
    user_repo: UserRepository = Depends(get_user_repo),
) -> Response:
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
        # M-2: Wrap sync Supabase call to avoid blocking the event loop
        await run_sync(user_repo.auth_sign_out, token)
        logger.info("Session invalidated for user %s", user_id)
    except Exception as exc:
        logger.error("sign_out failed for user %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "code": "REVOCATION_FAILED",
                    "message": "Session revocation failed. Clear local tokens and retry.",
                }
            },
            # The token will expire naturally even if server revocation failed.
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Account Deletion — DELETE /auth/account (hard-delete)
# ---------------------------------------------------------------------------


# Users with more blobs than this threshold have their storage wipe pushed
# to an ARQ job so the HTTP request doesn't time out. The ``wipe_deleted_user_blobs``
# worker is introduced in T5.5; until then, enqueued jobs will log as
# "unknown task" in ARQ. Large-user deletion paths are exercised via test only.
_INLINE_BLOB_WIPE_THRESHOLD = 500

# Known per-user ARQ job_id prefixes drained on account deletion (Unit 11).
# Each prefix is combined with the user_id as ``f"{prefix}:{user_id}"`` to form
# the job_id used at enqueue time. Extend this tuple when new per-user ARQ
# jobs are introduced so they are always cancelled on delete.
_USER_SCOPED_JOB_PREFIXES = ("delete_account",)

# Per-user Redis key formats swept on account deletion (Unit 6).
# Keep format strings here — never inline in the sweep block. When a new
# per-user Redis namespace is introduced, add a constant and wire it into
# the sweep in ``delete_account`` below so there are no silent remnants.
_SWEEP_CHAT_SEEDS_COOLDOWN_FMT = "advisor:chat_seeds:cooldown:{user_id}"
_SWEEP_CHAT_SEEDS_PREFIX_FMT = "advisor:chat_seeds:{user_id}:*"
_SWEEP_CHAT_SEEDS_LOCK_PREFIX_FMT = "advisor:chat_seeds:lock:{user_id}:*"
_SWEEP_POST_GLOWUP_RAPID_RETRY_PREFIX_FMT = "advisor:nudge:post_glowup:{user_id}:*"
_SWEEP_SCAN_COUNT = 100


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_account(
    claims: UserClaims = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_user_repo),
    image_repo: ImageRepository = Depends(get_image_repo),
    orphan_repo: OrphanedStorageKeyRepository = Depends(get_orphaned_storage_repo),
    ledger: CreditLedger = Depends(get_credit_ledger),
    redis_client: aioredis.Redis = Depends(get_redis),
    arq_pool: ArqRedis = Depends(get_arq_pool),
    payment: "PaymentPort" = Depends(get_payment_adapter),
    dlq_repo: StripeCustomerDLQRepository = Depends(get_stripe_customer_dlq_repo),
) -> Response:
    """Permanently delete the authenticated user and every owned artifact.

    Ordering (do NOT re-order — see docs/plans/delete-account-hard-reset):
    1.   Fetch the user. Missing → idempotent 204.
    1.5. Drain in-flight credit reservations via credit_release RPC (Unit 11).
    1.6. Abort known per-user ARQ jobs (Unit 11).
    2.   Release active credit reservations (legacy ledger.release path).
    3.   Enumerate owned blob keys (before CASCADE kills enumeration).
    3.5. Delete Stripe customer; on failure write to stripe_customer_dlq (Unit 11).
    4.   Delete the Supabase auth identity FIRST — failure is retry-safe.
    5.   Wipe blobs (inline for small users, ARQ for large ones; DLQ on failure).
    6.   Hard-delete the users row — CASCADE fans out the rest.
    7.   Insert the username reservation (only if step 6 actually deleted a row).
    8.   Redis cleanup via scan_iter (never KEYS).

    Idempotent: a second call on a user that's already gone returns 204.
    """
    user_id: str = claims["sub"]

    allowed, retry_after = await check_delete_account_rate_limit(user_id, redis_client)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many account-deletion attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    now_utc = datetime.now(tz=timezone.utc)
    reserved_until = now_utc + timedelta(days=settings.USERNAME_RESERVATION_DAYS)

    user = await run_sync(user_repo.get_profile_by_id, user_id)
    if not user:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    username: str = user["username"]
    stripe_customer_id: str | None = user.get("stripe_customer_id")

    # Step 1.5 — drain in-flight reservations (Unit 11) ----------------------
    # Best-effort: call credit_release (via ledger.release) for every reserved
    # reservation. Failures per-row are logged and skipped — a single bad row
    # must not abort the overall delete. Enumeration failure is also best-effort
    # (warn + continue) since reservations are eventually expired by the DB.
    try:
        active_reservations = await run_sync(user_repo.get_active_reservations, user_id)
        for res in active_reservations:
            try:
                await run_sync(ledger.release, UUID(res["id"]))
            except Exception as release_exc:  # noqa: BLE001
                logger.warning(
                    "delete_account: failed to credit_release reservation %s: %s",
                    res["id"],
                    release_exc,
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "delete_account: failed to enumerate reservations for drain (user=%s): %s",
            user_id,
            exc,
        )

    # Step 1.6 — drain scheduled ARQ jobs (Unit 11) --------------------------
    # Best-effort: abort known per-user ARQ jobs so they don't fire post-delete.
    for prefix in _USER_SCOPED_JOB_PREFIXES:
        job_id = f"{prefix}:{user_id}"
        try:
            job = await arq_pool.job(job_id)
            if job is not None:
                await job.abort()
        except Exception as abort_exc:  # noqa: BLE001
            logger.warning(
                "delete_account: failed to abort ARQ job %s: %s", job_id, abort_exc
            )

    # 2. Collect blob keys BEFORE cascade makes enumeration impossible. -----
    # Fail fast if enumeration fails — otherwise we'd hard-delete the auth
    # identity with zero blob wipes, losing the only source of truth for
    # what to wipe. The user row is still intact, so retry is safe.
    try:
        keys_by_bucket = await run_sync(user_repo.list_user_storage_keys, user_id)
    except Exception as exc:
        logger.error("Failed to enumerate storage keys for %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account deletion failed — could not enumerate user storage.",
        ) from exc

    total_blobs = sum(len(k) for k in keys_by_bucket.values())

    # 3. Delete Supabase auth identity FIRST. Failure = retry-safe (row intact).
    try:
        await run_sync(user_repo.auth_delete_user, user_id)
    except Exception as exc:
        logger.error("auth.admin.delete_user failed for %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication service error — account was not deleted.",
        ) from exc

    # 4. Blob wipe — inline for small users, ARQ for large ones. ------------
    if total_blobs <= _INLINE_BLOB_WIPE_THRESHOLD:
        for bucket, keys in keys_by_bucket.items():
            if not keys:
                continue
            try:
                await run_sync(image_repo.remove, bucket, keys)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Blob wipe failed for user %s in bucket %s: %s — enqueueing DLQ",
                    user_id,
                    bucket,
                    exc,
                )
                for key in keys:
                    await run_sync(orphan_repo.record, bucket, key, "delete_account")
    else:
        logger.info(
            "delete_account: %d blobs — offloading wipe to ARQ for user %s",
            total_blobs,
            user_id,
        )
        # NOTE: the ``wipe_deleted_user_blobs`` task is registered by T5.5;
        # until that lands ARQ will log "unknown task" for large-user deletes.
        # ARQ dedup: enqueue_job returns None if a job with the same _job_id
        # already sits in the 24h result-key TTL. Log and continue — the prior
        # wipe snapshot will still run; there's no reason to block the rest
        # of the delete flow on it.
        job = await arq_pool.enqueue_job(
            "wipe_deleted_user_blobs",
            user_id=user_id,
            keys_by_bucket=keys_by_bucket,
            _job_id=f"delete_account:{user_id}",
        )
        if job is None:
            logger.warning(
                "delete_account: ARQ job delete_account:%s was deduped "
                "(already enqueued within last 24h) — previous wipe snapshot will run",
                user_id,
            )

    # Step 3.5 — delete Stripe customer (Unit 11) ----------------------------
    # Best-effort: on failure write to DLQ for nightly reconciliation.
    # Never fails the overall delete — auth identity is already gone.
    if stripe_customer_id:
        try:
            await payment.delete_customer(stripe_customer_id)
        except Exception as stripe_exc:  # noqa: BLE001
            logger.warning(
                "delete_account: delete_customer failed for user=%s customer=%s: %s — "
                "writing to stripe_customer_dlq",
                user_id,
                stripe_customer_id,
                stripe_exc,
            )
            await run_sync(
                dlq_repo.record,
                stripe_customer_id,
                "delete_account",
                str(stripe_exc),
            )

    # 5. Hard-delete the user row. CASCADE fans out everything owned. -------
    try:
        deleted = await run_sync(user_repo.delete, user_id)
    except Exception as exc:
        logger.error("users DELETE failed for %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account deletion failed.",
        ) from exc

    if not deleted:
        # Auth identity is gone but the row vanished between steps.
        logger.info("delete_account: user %s row vanished mid-flow", user_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # 6. Reservation — only if step 5 actually deleted a row. ---------------
    try:
        await run_sync(user_repo.insert_username_reservation, username, reserved_until)
    except Exception as exc:
        logger.warning(
            "Reservation insert failed post-delete for user %s: %s",
            user_id,
            exc,
        )

    # Do NOT log the username — PII on a deleted row.
    logger.info(
        "Account hard-deleted for user %s (reserved until %s)",
        user_id,
        reserved_until.date(),
    )

    # 7. Redis cleanup — SCAN, not KEYS (non-blocking). ---------------------
    try:
        redis_keys_to_delete = [
            f"advisor_chat_rate:{user_id}",
            f"concurrent:{user_id}",
            _SWEEP_CHAT_SEEDS_COOLDOWN_FMT.format(user_id=user_id),
        ]
        async for key in redis_client.scan_iter(
            match=f"gen:user_daily:{user_id}:*", count=_SWEEP_SCAN_COUNT
        ):
            redis_keys_to_delete.append(key)
        async for key in redis_client.scan_iter(
            match=_SWEEP_CHAT_SEEDS_PREFIX_FMT.format(user_id=user_id),
            count=_SWEEP_SCAN_COUNT,
        ):
            redis_keys_to_delete.append(key)
        async for key in redis_client.scan_iter(
            match=_SWEEP_CHAT_SEEDS_LOCK_PREFIX_FMT.format(user_id=user_id),
            count=_SWEEP_SCAN_COUNT,
        ):
            redis_keys_to_delete.append(key)
        async for key in redis_client.scan_iter(
            match=_SWEEP_POST_GLOWUP_RAPID_RETRY_PREFIX_FMT.format(user_id=user_id),
            count=_SWEEP_SCAN_COUNT,
        ):
            redis_keys_to_delete.append(key)
        if redis_keys_to_delete:
            await redis_client.delete(*redis_keys_to_delete)
    except Exception as exc:
        logger.warning("Redis cleanup failed for deleted user %s: %s", user_id, exc)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
