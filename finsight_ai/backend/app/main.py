"""
Coral — FastAPI application entry point.

Simple, clean, no LangGraph, no Chroma, no MCP.
"""

from __future__ import annotations

import structlog
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.engine import init_db

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("coral.startup", version=settings.app_version, env=settings.environment)
    await init_db()
    logger.info("db.initialized")
    yield
    logger.info("coral.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Local-first AI financial statement analyzer.",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    from app.api.documents import router as documents_router
    from app.api.chat import router as chat_router
    from app.api.analytics import router as analytics_router
    from app.api.scan import router as scan_router
    from app.api.dashboard import router as dashboard_router
    from app.api.health import router as health_router

    app.include_router(documents_router)
    app.include_router(chat_router)
    app.include_router(analytics_router)
    app.include_router(scan_router)
    app.include_router(dashboard_router)
    app.include_router(health_router)

    return app


app = create_app()
