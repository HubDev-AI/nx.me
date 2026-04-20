"""FastAPI dependency providers.

Shared dependencies injected into route handlers via Depends().
"""

from __future__ import annotations

import ipaddress
import hmac
import logging
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from supabase import Client

import redis.asyncio as aioredis

from app.api.middleware.auth import UserClaims, validate_jwt
from app.db.async_helpers import run_sync

if TYPE_CHECKING:
    from arq import ArqRedis

    from app.advisor.embedding_port import EmbeddingPort
    from app.advisor.llm_port import LLMPort
    from app.entitlement.ledger import CreditLedger
    from app.entitlement.service import EntitlementService
    from app.payment.ports import PaymentPort
    from app.repositories.advisor_repo import AdvisorRepository
    from app.repositories.block_repo import BlockRepository
    from app.repositories.feed_repo import FeedRepository
    from app.repositories.glowup_analysis_repo import GlowupAnalysisRepository
    from app.repositories.guest_merge_repo import GuestMergeRepository
    from app.repositories.image_repo import ImageRepository
    from app.repositories.job_repo import JobRepository
    from app.repositories.orphaned_analyses_repo import OrphanedAnalysesRepository
    from app.repositories.orphaned_storage_repo import OrphanedStorageKeyRepository
    from app.repositories.post_repo import PostRepository
    from app.repositories.plan_version_repo import PlanVersionRepository
    from app.repositories.subscription_repo import SubscriptionRepository
    from app.repositories.upload_repo import UploadRepository
    from app.repositories.stripe_customer_dlq import StripeCustomerDLQRepository
    from app.repositories.user_repo import UserRepository
    from app.services.glowup_service import GlowupService
    from app.services.upload_service import UploadService

logger = logging.getLogger(__name__)

_TRUSTED_PROXY_NETWORKS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
)


def _is_trusted_proxy_host(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(ip in network for network in _TRUSTED_PROXY_NETWORKS)


def _get_forwarded_ip(forwarded_for: str) -> str | None:
    for candidate in reversed([part.strip() for part in forwarded_for.split(",")]):
        if not candidate:
            continue
        try:
            parsed = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if _is_trusted_proxy_host(candidate):
            continue
        if parsed.is_loopback or parsed.is_link_local or parsed.is_unspecified:
            continue
        return candidate
    return None


def get_client_ip(request: Request) -> str:
    """Get client IP, only trusting forwarded headers from known proxy ranges."""
    from app.config import settings

    socket_ip = request.client.host if request.client else ""

    if settings.TRUST_PROXY_HEADERS and socket_ip and _is_trusted_proxy_host(socket_ip):
        forwarded = request.headers.get("x-forwarded-for", "")
        forwarded_ip = _get_forwarded_ip(forwarded)
        if forwarded_ip:
            return forwarded_ip

    return socket_ip


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


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    supabase: Client = Depends(get_supabase),
    redis_client: aioredis.Redis = Depends(get_redis),
) -> UserClaims:
    """Validate the Bearer JWT and return the decoded claims.

    Delegates to ``validate_jwt`` (Story 2-2 interface contract).
    Raises HTTP 401 if the token is missing, expired, or invalid.
    Checks the user's ban status before returning claims.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.removeprefix("Bearer ").strip()
    claims = validate_jwt(token)

    # Ban check with Redis cache (C-1: avoids DB call on every request)
    user_id = claims["sub"]
    ban_key = f"ban:{user_id}"
    cached = await redis_client.get(ban_key)

    if cached is None:
        # Cache miss — query DB and cache for 60s
        # C-3: Wrap sync Supabase call to avoid blocking the event loop
        user_row = await run_sync(
            lambda: (
                supabase.table("users")
                .select("is_banned")
                .eq("id", user_id)
                .maybe_single()
                .execute()
            )
        )
        if not user_row or not user_row.data:
            is_banned = False
        else:
            is_banned = bool(user_row.data.get("is_banned"))
        await redis_client.set(ban_key, "1" if is_banned else "0", ex=60)
        cached = "1" if is_banned else "0"

    if cached == "1":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "ACCOUNT_BANNED",
                    "message": "Your account has been suspended.",
                }
            },
        )

    return claims


async def get_user_or_guest(
    authorization: Annotated[str | None, Header()] = None,
    x_guest_token: Annotated[str | None, Header(alias="X-Guest-Token")] = None,
    supabase: Client = Depends(get_supabase),
    redis_client: aioredis.Redis = Depends(get_redis),
) -> UserClaims:
    """Auth dep accepting JWT or X-Guest-Token.

    The token is resolved against the users.guest_session_token column — no
    Redis lookup, no tier-1 cache yet (cold path, one lookup per request).

    Falls through to normal JWT validation otherwise.
    """
    from app.db.guest import is_valid_guest_token_format, resolve_guest_by_token

    if x_guest_token and is_valid_guest_token_format(x_guest_token):
        guest_user_id = await run_sync(resolve_guest_by_token, supabase, x_guest_token)
        if guest_user_id is not None:
            return UserClaims(
                sub=str(guest_user_id),
                role="authenticated",
                exp=9999999999,
            )
        # Fall through to JWT — avoids leaking whether the token existed.

    # Fall through to normal JWT validation
    return await get_current_user(
        authorization=authorization,
        supabase=supabase,
        redis_client=redis_client,
    )


def require_admin(
    x_admin_key: Annotated[str | None, Header(alias="X-Admin-Key")] = None,
) -> None:
    """Require admin API key for admin endpoints."""
    from app.config import settings

    if not x_admin_key or not hmac.compare_digest(x_admin_key, settings.ADMIN_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )


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


def get_orphaned_storage_repo(request: Request) -> "OrphanedStorageKeyRepository":
    """Return an OrphanedStorageKeyRepository wired to the app's Supabase client."""
    from app.repositories.orphaned_storage_repo import OrphanedStorageKeyRepository

    return OrphanedStorageKeyRepository(request.app.state.supabase)


def get_orphaned_analyses_repo(request: Request) -> "OrphanedAnalysesRepository":
    """Return an OrphanedAnalysesRepository wired to the app's Supabase client."""
    from app.repositories.orphaned_analyses_repo import OrphanedAnalysesRepository

    return OrphanedAnalysesRepository(request.app.state.supabase)


def get_arq_pool(request: Request) -> "ArqRedis":
    """Return the shared ARQ pool (stored on ``app.state.arq_pool`` at startup).

    All ARQ enqueue sites across the API (glowup, social, delete_account)
    share the same pool instance via ``request.app.state.arq_pool`` — this
    dep simply exposes it as a FastAPI dependency so handlers can receive
    it via ``Depends``.
    """
    return request.app.state.arq_pool


def get_upload_repo(request: Request) -> "UploadRepository":
    """Return an UploadRepository wired to the app's Supabase client."""
    from app.repositories.upload_repo import UploadRepository

    return UploadRepository(request.app.state.supabase)


def get_glowup_analysis_repo(request: Request) -> "GlowupAnalysisRepository":
    """Return a GlowupAnalysisRepository wired to the app's Supabase client."""
    from app.repositories.glowup_analysis_repo import GlowupAnalysisRepository

    return GlowupAnalysisRepository(request.app.state.supabase)


def get_upload_service(request: Request) -> "UploadService":
    """Return an UploadService wired to the app's Supabase client."""
    from app.services.upload_service import UploadService

    return UploadService(request.app.state.supabase)


def get_glowup_service(request: Request) -> "GlowupService":
    """Return a GlowupService wired to the app's Supabase client."""
    from app.services.glowup_service import GlowupService

    return GlowupService(request.app.state.supabase)


def get_block_repo(request: Request) -> "BlockRepository":
    """Return a BlockRepository wired to the app's Supabase client."""
    from app.repositories.block_repo import BlockRepository

    return BlockRepository(request.app.state.supabase)


def get_post_repo(request: Request) -> "PostRepository":
    """Return a PostRepository wired to the app's Supabase client."""
    from app.repositories.post_repo import PostRepository

    return PostRepository(request.app.state.supabase)


def get_feed_repo(request: Request) -> "FeedRepository":
    """Return a FeedRepository wired to the app's Supabase client."""
    from app.repositories.feed_repo import FeedRepository

    return FeedRepository(request.app.state.supabase)


def get_subscription_repo(request: Request) -> "SubscriptionRepository":
    """Return a SubscriptionRepository wired to the app's Supabase client."""
    from app.repositories.subscription_repo import SubscriptionRepository

    return SubscriptionRepository(request.app.state.supabase)


def get_plan_version_repo(request: Request) -> "PlanVersionRepository":
    """Return a PlanVersionRepository wired to the app's Supabase client."""
    from app.repositories.plan_version_repo import PlanVersionRepository

    return PlanVersionRepository(request.app.state.supabase)


def get_credit_ledger(request: Request) -> "CreditLedger":
    """Return a CreditLedger wired to the app's Supabase client."""
    from app.entitlement.ledger import CreditLedger

    return CreditLedger(request.app.state.supabase)


def get_advisor_repo(request: Request) -> "AdvisorRepository":
    """Return an AdvisorRepository wired to the app's Supabase client."""
    from app.repositories.advisor_repo import AdvisorRepository

    return AdvisorRepository(request.app.state.supabase)


def get_entitlement_service(
    request: Request,
) -> "EntitlementService":
    """Return an EntitlementService wired to app-level Supabase + Redis."""
    from app.entitlement.service import EntitlementService

    return EntitlementService(
        supabase=request.app.state.supabase,
        redis_client=request.app.state.redis,
    )


def get_payment_adapter(request=None) -> "PaymentPort":
    """Return the configured payment adapter (Stripe or mock).

    When resolved as a FastAPI ``Depends`` (inside a route) ``request`` is
    injected automatically and its ``app.state.supabase`` is forwarded to
    ``StripePaymentAdapter`` so the adapter's lazy ``stripe_customer_id``
    cache can hit/miss the ``users`` table. Direct calls from contexts
    without a ``Request`` (e.g. the Stripe webhook handler's raw
    ``get_payment_adapter()`` invocation, or unit tests) pass ``None`` and
    the adapter falls back to its legacy ``Customer.search`` path — the
    cache is advisory, not required for correctness.
    """
    from app.config import settings

    if settings.ADAPTER__PAYMENT_ADAPTER == "stripe":
        from app.payment.adapters.stripe_adapter import StripePaymentAdapter

        supabase_client = request.app.state.supabase if request is not None else None
        return StripePaymentAdapter(supabase_client=supabase_client)
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


def get_embedding_adapter() -> "EmbeddingPort":
    """Return the configured embedding adapter (OpenAI, Ollama, or mock).

    Selection driven by ADAPTER__EMBEDDING_ADAPTER config value. Decoupled
    from get_llm_adapter so any chat backend can pair with any embedding
    backend (e.g. Anthropic chat + Ollama embeddings for local dev).

    Unknown values raise loudly — silently falling back to the mock adapter
    would write deterministic-but-meaningless vectors to the DB and corrupt
    similarity search without any error visibility.
    """
    from app.config import settings

    choice = settings.ADAPTER__EMBEDDING_ADAPTER
    if choice == "openai":
        from app.advisor.adapters.embeddings.openai import OpenAIEmbeddingAdapter

        return OpenAIEmbeddingAdapter()
    if choice == "ollama":
        from app.advisor.adapters.embeddings.ollama import OllamaEmbeddingAdapter

        return OllamaEmbeddingAdapter()
    if choice == "mock":
        from app.advisor.adapters.embeddings.mock import MockEmbeddingAdapter

        return MockEmbeddingAdapter()
    raise ValueError(
        f"Unknown ADAPTER__EMBEDDING_ADAPTER={choice!r}; "
        "expected one of: openai, ollama, mock"
    )


def require_feature(feature: str):
    """FastAPI dependency: Ada/feature gate (credits-only engine, Unit 7).

    The credits-only engine is ledger-gated, not tier-gated. This
    dependency is a no-op stub — ``ADVISOR_ENABLED`` and credit-ledger
    checks inside the service layer enforce access. The stub is kept so
    route signatures that already declare ``Depends(require_feature(...))``
    continue to compile without change.

    Usage:
        @router.post("/advisor/messages")
        async def send_message(
            _: None = Depends(require_feature("advisor_chat")),
        ): ...
    """

    async def _check() -> None:
        return

    return _check


def require_app_feature(feature: str):
    """FastAPI dependency: gate a route behind a global feature flag.

    Distinct from `require_feature` (which checks per-tier entitlement).
    `require_app_feature` checks the app-wide toggle exposed via
    GET /v1/features. When disabled, returns 403 FEATURE_DISABLED.

    Usage:
        router = APIRouter(
            prefix="/posts",
            dependencies=[Depends(require_app_feature("social_enabled"))],
        )
    """
    from app.features import is_enabled

    async def _check() -> None:
        if not is_enabled(feature):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": {
                        "code": "FEATURE_DISABLED",
                        "message": "This feature is not currently available.",
                        "detail": {"feature": feature},
                    }
                },
            )

    return _check


def get_guest_merge_repo(request: Request) -> "GuestMergeRepository":
    """Return a GuestMergeRepository wired to the app's Supabase client."""
    from app.repositories.guest_merge_repo import GuestMergeRepository

    return GuestMergeRepository(request.app.state.supabase)


def get_stripe_customer_dlq_repo(request: Request) -> "StripeCustomerDLQRepository":
    """Return a StripeCustomerDLQRepository wired to the app's Supabase client."""
    from app.repositories.stripe_customer_dlq import StripeCustomerDLQRepository

    return StripeCustomerDLQRepository(request.app.state.supabase)
