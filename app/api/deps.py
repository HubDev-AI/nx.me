"""FastAPI dependency providers.

Shared dependencies injected into route handlers via Depends().
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from supabase import Client

import redis.asyncio as aioredis

from app.api.middleware.auth import UserClaims, validate_jwt
from app.entitlement.models import EntitlementResult, PAYMENT_REQUIRED_CODES

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Infrastructure deps
# ---------------------------------------------------------------------------


def get_supabase(request: Request) -> Client:
    """Return the Supabase service-role client attached to app state."""
    return request.app.state.supabase


def get_redis(request: Request) -> aioredis.Redis:
    """Return the async Redis client attached to app state."""
    return request.app.state.redis


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    supabase: Client = Depends(get_supabase),  # noqa: ARG001 — reserved for token introspection
) -> UserClaims:
    """Validate the Bearer JWT and return the decoded claims.

    Delegates to ``validate_jwt`` (Story 2-2 interface contract).
    Raises HTTP 401 if the token is missing, expired, or invalid.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.removeprefix("Bearer ").strip()
    return validate_jwt(token)


# ---------------------------------------------------------------------------
# Entitlement (A-5)
# ---------------------------------------------------------------------------


def get_entitlement_service(
    request: Request,
) -> "EntitlementService":
    """Return an EntitlementService wired to app-level Supabase + Redis."""
    from app.entitlement.service import EntitlementService

    return EntitlementService(
        supabase=request.app.state.supabase,
        redis_client=request.app.state.redis,
    )


_ERROR_MESSAGES: dict[str, str] = {
    "TIER_LIMIT_DAILY": "Daily generation limit reached",
    "TIER_LIMIT_WEEKLY": "Weekly generation limit reached",
    "TIER_LIMIT_MONTHLY": "Monthly generation limit reached",
    "TIER_LIMIT_TOTAL": "Lifetime generation limit reached",
    "TIER_LIMIT_CREDITS": "No credits remaining",
    "TIER_FEATURE_LOCKED": "Feature not available on your current plan",
    "TIER_CONCURRENT_LIMIT": "A generation is already in progress",
}


def require_entitlement(action: str):
    """FastAPI dependency: check entitlement before route execution (A-5).

    Usage:
        @router.post("/generations")
        async def create_generation(
            _: None = Depends(require_entitlement("generation")),
            claims: UserClaims = Depends(get_current_user),
        ): ...
    """
    async def _check(
        claims: UserClaims = Depends(get_current_user),
        svc: "EntitlementService" = Depends(get_entitlement_service),
    ) -> None:
        from uuid import UUID

        user_id = UUID(claims["sub"])
        result: EntitlementResult = await svc.check(user_id, action)
        if not result.allowed:
            status_code = 402 if result.error_code in PAYMENT_REQUIRED_CODES else 429
            raise HTTPException(
                status_code=status_code,
                detail={
                    "error": {
                        "code": result.error_code,
                        "message": _ERROR_MESSAGES.get(result.error_code, "Entitlement check failed"),
                        "detail": {
                            "limit": result.limit,
                            "used": result.used,
                            "retry_after": result.retry_after.isoformat() if result.retry_after else None,
                            "reset_in_seconds": result.reset_in_seconds,
                            "upgrade_available": result.upgrade_available,
                        },
                    }
                },
            )

    return _check


def require_feature(feature: str):
    """FastAPI dependency: check feature flag on user's tier (A-5).

    Usage:
        @router.post("/advisor/messages")
        async def send_message(
            _: None = Depends(require_feature("advisor_chat")),
        ): ...
    """
    async def _check(
        claims: UserClaims = Depends(get_current_user),
        svc: "EntitlementService" = Depends(get_entitlement_service),
    ) -> None:
        from uuid import UUID

        user_id = UUID(claims["sub"])
        if not await svc.has_feature(user_id, feature):
            raise HTTPException(
                status_code=402,
                detail={
                    "error": {
                        "code": "TIER_FEATURE_LOCKED",
                        "message": f"Feature '{feature}' is not available on your current plan",
                        "detail": {"upgrade_available": True},
                    }
                },
            )

    return _check
