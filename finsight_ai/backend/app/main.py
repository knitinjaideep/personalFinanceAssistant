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
            "ollama_model": settings.ollama.model,
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


async def _check_ollama_model() -> None:
    """Verify the configured chat model is available in Ollama at startup.

    Logs a clear, actionable error (with the exact `ollama pull` command) if the
    model is missing or Ollama is unreachable. Does not crash the app — the chat
    pipeline degrades to its rule-based fallback if the model is absent.
    """
    from app.services import llm

    model = settings.ollama.model
    try:
        health = await llm.check_health()
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "ollama_unreachable",
            extra={"stage": "startup_check", "error": str(exc), "model": model,
                   "hint": settings.ollama.pull_hint},
        )
        return

    if health.get("status") != "ok":
        logger.error(
            "ollama_unreachable",
            extra={"stage": "startup_check", "error": health.get("error"),
                   "model": model, "hint": settings.ollama.pull_hint},
        )
        return

    available = health.get("models", [])
    # Match on exact name or base name (e.g. "gemma4:latest" vs "gemma4").
    base = model.split(":")[0]
    found = any(m == model or m.split(":")[0] == base for m in available)
    if found:
        logger.info(
            "ollama_model_ready",
            extra={"stage": "startup_check", "model": model},
        )
    else:
        logger.error(
            "ollama_model_unavailable — chat model not installed. %s",
            settings.ollama.pull_hint,
            extra={
                "stage": "startup_check",
                "model": model,
                "available_models": available,
                "hint": settings.ollama.pull_hint,
            },
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await init_db()
    logger.info("db.initialized", extra={"stage": "db_initialized"})
    _log_startup_diagnostics(app)
    await _check_ollama_model()
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
