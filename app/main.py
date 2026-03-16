"""NXME FastAPI application factory.

Initialises shared resources (Supabase client, Redis) during lifespan
and mounts all API routers.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import redis.asyncio as aioredis
from fastapi import FastAPI

from app.api import analyses, auth, entitlement, health
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
        logger.info(
            "Face analysis adapter is '%s' — skipping MediaPipe model load",
            settings.ADAPTER__FACE_ANALYSIS_ADAPTER,
        )

    logger.info("Supabase and Redis clients initialised")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    await app.state.redis.aclose()
    logger.info("NXME API shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="NXME API",
        description="AI-powered appearance improvement social platform",
        version="1.0.0",
        lifespan=lifespan,
        # Disable docs in production
        docs_url="/docs" if settings.APP_ENV != "production" else None,
        redoc_url="/redoc" if settings.APP_ENV != "production" else None,
    )

    # ── Routers ──────────────────────────────────────────────────────────────
    app.include_router(health.router)
    app.include_router(auth.router, prefix="/auth")
    app.include_router(entitlement.router)
    app.include_router(analyses.router)

    return app


app = create_app()
