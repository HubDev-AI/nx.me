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
from app.entitlement.models import ENTITLEMENT_ERROR_MESSAGES, EntitlementResult, PAYMENT_REQUIRED_CODES

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


def get_user_repo(request: Request) -> "UserRepository":
    """Return a UserRepository wired to the app's Supabase client."""
    from app.repositories.user_repo import UserRepository

    return UserRepository(request.app.state.supabase)


def get_job_repo(request: Request) -> "JobRepository":
    """Return a JobRepository wired to the app's Supabase client."""
    from app.repositories.job_repo import JobRepository

    return JobRepository(request.app.state.supabase)


def get_image_repo(request: Request) -> "ImageRepository":
    """Return an ImageRepository wired to the app's Supabase client."""
    from app.repositories.image_repo import ImageRepository

    return ImageRepository(request.app.state.supabase)


def get_post_repo(request: Request) -> "PostRepository":
    """Return a PostRepository wired to the app's Supabase client."""
    from app.repositories.post_repo import PostRepository

    return PostRepository(request.app.state.supabase)


def get_feed_repo(request: Request) -> "FeedRepository":
    """Return a FeedRepository wired to the app's Supabase client."""
    from app.repositories.feed_repo import FeedRepository

    return FeedRepository(request.app.state.supabase)


def get_tier_repo(request: Request) -> "TierRepository":
    """Return a TierRepository wired to the app's Supabase + Redis clients."""
    from app.entitlement.tier_repo import TierRepository

    return TierRepository(request.app.state.supabase, request.app.state.redis)


def get_entitlement_service(
    request: Request,
) -> "EntitlementService":
    """Return an EntitlementService wired to app-level Supabase + Redis."""
    from app.entitlement.service import EntitlementService

    return EntitlementService(
        supabase=request.app.state.supabase,
        redis_client=request.app.state.redis,
    )


_ERROR_MESSAGES = ENTITLEMENT_ERROR_MESSAGES


def get_payment_adapter() -> "PaymentPort":
    """Return the configured payment adapter (Stripe or mock)."""
    from app.config import settings

    if settings.ADAPTER__PAYMENT_ADAPTER == "stripe":
        from app.payment.adapters.stripe_adapter import StripePaymentAdapter
        return StripePaymentAdapter()
    from app.payment.adapters.mock import MockPaymentAdapter
    return MockPaymentAdapter()


def get_llm_adapter() -> "LLMPort":
    """Return the configured LLM adapter (Anthropic or mock).

    Selection driven by ADAPTER__LLM_ADAPTER config value.
    """
    from app.config import settings

    if settings.ADAPTER__LLM_ADAPTER == "anthropic":
        from app.advisor.adapters.anthropic_adapter import AnthropicAdapter
        return AnthropicAdapter()
    from app.advisor.adapters.mock import MockLLMAdapter
    return MockLLMAdapter()


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
