"""NXME FastAPI application factory.

Initialises shared resources (Supabase client, Redis) during lifespan
and mounts all API routers.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import redis.asyncio as aioredis
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError

from app.api import analyses, auth, entitlement, generation, health, posts, public, social, users, webhooks
from app.api.errors import (
    ApiError,
    RateLimitExceeded,
    api_error_handler,
    http_exception_handler,
    rate_limit_handler,
    validation_error_handler,
)
from app.api.middleware.security_headers import SecurityHeadersMiddleware
from app.config import settings
from app.db.client import get_supabase_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application-level resource lifecycle."""
    # ── Startup ─────────────────────────────────────────────────────────────
    logger.info("Starting NXME API (%s)", settings.APP_ENV)

    # CS-1 AC-5: Block mock/local adapters in non-development environments
    if settings.APP_ENV != "development":
        _mock_adapters = []
        for attr in dir(settings):
            if attr.startswith("ADAPTER__") and getattr(settings, attr) in ("mock", "local"):
                _mock_adapters.append(f"{attr}={getattr(settings, attr)}")
        if _mock_adapters:
            msg = f"FATAL: Mock/local adapters in {settings.APP_ENV}: {', '.join(_mock_adapters)}"
            logger.critical(msg)
            raise SystemExit(msg)

    # H-8: Block well-known demo JWT secrets in non-development environments
    _DEMO_SECRETS = {
        "super-secret-jwt-token-with-at-least-32-characters-long",
        "local-dev-secret-key-change-in-production",
    }
    if settings.APP_ENV != "development":
        if settings.SUPABASE_JWT_SECRET in _DEMO_SECRETS:
            msg = "FATAL: Well-known demo SUPABASE_JWT_SECRET in non-development environment"
            logger.critical(msg)
            raise SystemExit(msg)
        if settings.SECRET_KEY in _DEMO_SECRETS:
            msg = "FATAL: Well-known demo SECRET_KEY in non-development environment"
            logger.critical(msg)
            raise SystemExit(msg)

    # Validate required API keys for configured (non-mock) adapters
    adapter_key_map: dict[str, tuple[str, ...]] = {
        "falai": ("FAL_API_KEY",),
        "stripe": ("STRIPE_API_KEY", "STRIPE_WEBHOOK_SECRET"),
        "anthropic": ("ANTHROPIC_API_KEY",),
        "rekognition": ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"),
    }
    for adapter_name, required_keys in adapter_key_map.items():
        # Check if any ADAPTER__* setting is configured to use this adapter
        active = any(
            getattr(settings, attr) == adapter_name
            for attr in dir(settings)
            if attr.startswith("ADAPTER__")
        )
        if active:
            missing = [k for k in required_keys if not getattr(settings, k, "")]
            if missing:
                msg = (
                    f"Adapter '{adapter_name}' is active but required keys are empty: "
                    f"{', '.join(missing)}"
                )
                logger.critical(msg)
                raise SystemExit(msg)
    logger.info("Adapter API key validation passed")

    app.state.supabase = get_supabase_service()
    app.state.redis = aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        encoding="utf-8",
    )

    # Pre-load MediaPipe FaceMesh model (AC-2: health check gates on this)
    if settings.ADAPTER__FACE_ANALYSIS_ADAPTER == "mediapipe":
        from app.face_analysis.landmark_extractor import preload_model
        preload_model()
        logger.info("MediaPipe FaceMesh model pre-loaded")
    else:
        logger.info("Face analysis adapter is not mediapipe — skipping MediaPipe model load")

    # ARQ pool for enqueuing generation jobs
    app.state.arq_pool = await create_pool(
        RedisSettings.from_dsn(settings.REDIS_URL)
    )

    logger.info("Supabase, Redis, and ARQ pool initialised")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    await app.state.arq_pool.aclose()
    await app.state.redis.aclose()
    logger.info("NXME API shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="NXME API",
        description="AI-powered appearance improvement social platform",
        version="1.0.0",
        lifespan=lifespan,
        # M-2: Disable docs in all non-development environments
        docs_url="/docs" if settings.APP_ENV == "development" else None,
        redoc_url="/redoc" if settings.APP_ENV == "development" else None,
    )

    # ── Security headers ─────────────────────────────────────────────────────
    app.add_middleware(SecurityHeadersMiddleware)

    # ── C-2: Body size limit ──────────────────────────────────────────────────
    from fastapi.responses import JSONResponse as JSONResp

    max_body = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @app.middleware("http")
    async def limit_request_body(request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > max_body:
            return JSONResp(
                status_code=413,
                content={"detail": "Request body too large"},
            )
        return await call_next(request)

    # M-25: No CORSMiddleware — API consumed by mobile app (native HTTP, no CORS)
    # and card-web (server-side rendering). If browser-direct calls needed later,
    # add CORSMiddleware with explicit allow_origins (never "*").

    # ── Exception handlers ───────────────────────────────────────────────────
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

    # ── Routers ──────────────────────────────────────────────────────────────
    # Health check is unversioned (load balancer probes hit / directly)
    app.include_router(health.router)

    # Webhooks are unversioned (external providers call fixed URLs)
    app.include_router(webhooks.router)

    # Public endpoints — no auth, no versioning, under /api prefix
    app.include_router(public.router, prefix="/api")

    # All API routes under /v1 prefix — single place to manage API version
    from fastapi import APIRouter
    v1 = APIRouter(prefix="/v1")
    v1.include_router(auth.router, prefix="/auth")
    v1.include_router(entitlement.router)
    v1.include_router(analyses.router)
    v1.include_router(generation.router)
    v1.include_router(social.router)
    v1.include_router(posts.router)
    v1.include_router(users.router)

    if settings.ADVISOR_ENABLED:
        from app.api import advisor
        v1.include_router(advisor.router)
        logger.info("Advisor module enabled — routes registered")
    else:
        logger.info("Advisor module disabled (ADVISOR_ENABLED=False)")

    app.include_router(v1)

    return app


app = create_app()
