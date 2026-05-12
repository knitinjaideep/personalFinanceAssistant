"""
Coral — FastAPI application entry point.

Simple, clean, no LangGraph, no Chroma, no MCP.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Configure logging before any other app imports that might log at import time.
from app.core.logger import configure_logging, get_logger

configure_logging()

from app.config import settings
from app.core.middleware import RequestTracingMiddleware
from app.db.engine import init_db

logger = get_logger(__name__)


def _log_startup_diagnostics(app: FastAPI) -> None:
    """Emit a structured startup summary."""
    try:
        import langgraph  # noqa: F401
        langgraph_installed = True
    except ImportError:
        langgraph_installed = False

    routes = [f"{m} {r.path}" for r in app.routes for m in getattr(r, "methods", []) or []]  # type: ignore[attr-defined]

    logger.info(
        "app_started",
        extra={
            "stage": "app_started",
            "environment": settings.environment,
            "debug": settings.debug,
            "log_level": settings.log_level,
            "database_path": str(settings.get_db_path()),
            "ollama_model": settings.ollama.chat_model,
            "embedding_model": settings.ollama.embedding_model,
            "langgraph_installed": langgraph_installed,
            "langgraph_wired_to_chat": False,
            "registered_routes": len(routes),
        },
    )

    if langgraph_installed:
        logger.warning(
            "langgraph_not_wired — LangGraph components exist but are not connected to chat route",
            extra={"stage": "startup_check"},
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await init_db()
    logger.info("db.initialized", extra={"stage": "db_initialized"})
    _log_startup_diagnostics(app)
    yield
    logger.info("coral.shutdown", extra={"stage": "app_shutdown"})


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Local-first AI financial statement analyzer.",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    # Request tracing must be outermost so req_id is available to all handlers.
    app.add_middleware(RequestTracingMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    # Register routers
    from app.api.documents import router as documents_router
    from app.api.chat import router as chat_router
    from app.api.analytics import router as analytics_router
    from app.api.scan import router as scan_router
    from app.api.dashboard import router as dashboard_router
    from app.api.health import router as health_router
    from app.api.catalog import router as catalog_router

    app.include_router(documents_router)
    app.include_router(chat_router)
    app.include_router(analytics_router)
    app.include_router(scan_router)
    app.include_router(dashboard_router)
    app.include_router(health_router)
    app.include_router(catalog_router)

    return app


app = create_app()
