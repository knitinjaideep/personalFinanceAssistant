"""
FinSight AI — FastAPI application entry point.

Responsibilities:
- Create the FastAPI app instance
- Register all routers
- Configure CORS, lifespan (startup/shutdown hooks)
- Initialize the database and vector store on startup
"""

from __future__ import annotations

import structlog
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database.engine import init_db
from app.rag.chroma_store import ChromaStore
from app.api.routes import documents, statements, chat, analytics, buckets, review, reconciliation, corrections, metrics

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Handle application startup and shutdown lifecycle."""
    logger.info("finsight_ai.startup", version=settings.app_version, env=settings.environment)

    # Initialize relational database (create tables if not exist)
    await init_db()
    logger.info("database.initialized")

    # Warm up Chroma vector store
    chroma = ChromaStore()
    await chroma.initialize()
    logger.info("chroma.initialized", collection=settings.chroma.collection_name)

    # Store shared resources on app state for dependency injection
    app.state.chroma = chroma

    yield

    logger.info("finsight_ai.shutdown")


def create_app() -> FastAPI:
    """Application factory — creates and configures the FastAPI instance."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Local-first AI financial intelligence system. "
            "Analyzes financial statements from multiple institutions privately."
        ),
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    # CORS — allow the React frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(documents.router, prefix="/api/v1/documents", tags=["Documents"])
    app.include_router(statements.router, prefix="/api/v1/statements", tags=["Statements"])
    app.include_router(chat.router, prefix="/api/v1/chat", tags=["Chat"])
    app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["Analytics"])
    app.include_router(buckets.router, prefix="/api/v1/buckets", tags=["Buckets"])
    app.include_router(review.router, prefix="/api/v1/review", tags=["Review"])
    app.include_router(reconciliation.router, prefix="/api/v1/reconciliation", tags=["Reconciliation"])
    app.include_router(corrections.router, prefix="/api/v1/corrections", tags=["Corrections"])
    app.include_router(metrics.router, prefix="/api/v1/metrics", tags=["Metrics"])

    @app.get("/health", tags=["Health"])
    async def health_check() -> JSONResponse:
        return JSONResponse({"status": "ok", "version": settings.app_version})

    return app


app = create_app()
