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

from app.api import auth, entitlement, health
from app.config import settings
from app.db.client import get_supabase_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application-level resource lifecycle."""
    # ── Startup ─────────────────────────────────────────────────────────────
    logger.info("Starting NXME API (%s)", settings.APP_ENV)

    app.state.supabase = get_supabase_service()
    app.state.redis = aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        encoding="utf-8",
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

    return app


app = create_app()
