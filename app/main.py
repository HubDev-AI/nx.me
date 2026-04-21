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

from app.api import (
    admin,
    auth,
    blocks,
    entitlement,
    features,
    glowup,
    health,
    jobs,
    posts,
    public,
    refund,
    social,
    uploads,
    user_consent,
    users,
    webhooks,
)
from app.api.errors import (
    ApiError,
    RateLimitExceeded,
    api_error_handler,
    http_exception_handler,
    rate_limit_handler,
    validation_error_handler,
)
from app.api.middleware.logging import RequestLoggingMiddleware
from app.api.middleware.security_headers import SecurityHeadersMiddleware
from app.config import settings
from app.db.client import get_supabase_service
from app.logging_config import configure_logging

configure_logging()

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
            if attr.startswith("ADAPTER__") and getattr(settings, attr) in (
                "mock",
                "local",
            ):
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

    # Pre-fetch ES256 JWKS key for JWT validation (Supabase CLI v2+ uses ES256)
    from app.api.middleware.auth import prefetch_jwks_key

    await prefetch_jwks_key()

    # Pre-load MediaPipe FaceMesh model (AC-2: health check gates on this)
    if settings.ADAPTER__FACE_ANALYSIS_ADAPTER == "mediapipe":
        from app.face_analysis.landmark_extractor import preload_model

        preload_model()
        logger.info("MediaPipe FaceMesh model pre-loaded")
    else:
        logger.info(
            "Face analysis adapter is not mediapipe — skipping MediaPipe model load"
        )

    # G-10: Pre-load ArcFace model in API lifespan (not just worker) to avoid
    # first-request latency when identity_checker is called from the API process
    if settings.ADAPTER__IMAGE_GENERATION_ADAPTER != "mock":
        try:
            from app.generation.identity_checker import preload_arcface

            preload_arcface()
            logger.info("ArcFace identity model pre-loaded")
        except ImportError:
            logger.info("ArcFace preload not available — skipping")
        except Exception as exc:
            logger.warning("ArcFace preload failed (non-fatal): %s", exc)

    # Validate makeup preset YAML at startup — fail-fast on schema violation
    # so misconfigured presets don't reach production.
    from app.generation.preset_registry import load_presets

    load_presets()
    logger.info("Makeup preset registry validated")

    # ARQ pool for enqueuing generation jobs
    app.state.arq_pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))

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

    # ── Request logging (scrubs Authorization + X-Install-UUID) ─────────────
    app.add_middleware(RequestLoggingMiddleware)

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
        # M-6: Chunked Transfer-Encoding bypasses Content-Length check.
        # In production, the upstream reverse proxy (nginx / ALB / CloudFront)
        # MUST enforce client_max_body_size / payload size limits. Starlette's
        # ServerErrorMiddleware will close connections that exceed memory, but
        # the authoritative size gate is at the infrastructure layer. If no
        # reverse proxy is present (local dev), the Content-Length check above
        # still protects well-behaved clients.
        return await call_next(request)

    # M-25: CORS for local dev — allows Expo web preview to call the API.
    # Production should restrict origins to the actual domain.
    from fastapi.middleware.cors import CORSMiddleware

    if settings.APP_ENV == "development":
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[
                "http://localhost:8087",
                "http://localhost:19006",
                "http://localhost:8081",
            ],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

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

    # Admin endpoints — unversioned, keyed by X-Admin-Key header
    app.include_router(admin.router)

    # Public endpoints — no auth, no versioning, under /api prefix (legacy).
    app.include_router(public.router, prefix="/api")

    # All API routes under /v1 prefix — single place to manage API version
    from fastapi import APIRouter

    v1 = APIRouter(prefix="/v1")
    # Re-mount the public router under /v1 so new consumers (card-web
    # sitemap) can use the versioned path. The /api mount above is kept for
    # backwards compatibility with already-shipped mobile builds.
    v1.include_router(public.router)
    v1.include_router(features.router)  # public — no auth required
    v1.include_router(auth.router, prefix="/auth")
    v1.include_router(entitlement.router)
    # Tier-3 API: uploads + glowup feature namespace + jobs
    v1.include_router(uploads.router)
    v1.include_router(glowup.router)
    v1.include_router(jobs.router)
    v1.include_router(user_consent.router)
    # Legacy refund endpoint (/v1/analyses/{job_id}/refund) — still mounted
    # until mobile client is fully migrated (Phase 4). New code uses
    # POST /jobs/{job_id}/refund in app/api/jobs.py instead.
    v1.include_router(refund.router)
    v1.include_router(social.router)
    v1.include_router(posts.router)
    v1.include_router(blocks.router)
    v1.include_router(users.router)

    # Advisor routes always mounted; router-level require_app_feature("advisor_enabled")
    # returns 403 FEATURE_DISABLED when the flag is off.
    from app.api import advisor

    v1.include_router(advisor.router)

    app.include_router(v1)

    return app


app = create_app()
