"""
Database engine and session factory.

Uses SQLAlchemy async engine with SQLite + aiosqlite driver.
All database interactions should use `get_session()` as a FastAPI dependency
or as an async context manager in services.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.config import settings

logger = structlog.get_logger(__name__)

# Module-level engine singleton — created once on startup
_engine: AsyncEngine | None = None
_async_session_factory: sessionmaker | None = None  # type: ignore[type-arg]


def _get_engine() -> AsyncEngine:
    """Return (or create) the async SQLAlchemy engine."""
    global _engine
    if _engine is None:
        database_url = settings.get_database_url()
        logger.info("database.engine.create", url=database_url)
        _engine = create_async_engine(
            database_url,
            echo=settings.database.echo_sql,
            # SQLite-specific: enable WAL mode for better concurrency
            connect_args={"check_same_thread": False},
        )
    return _engine


def _get_session_factory() -> sessionmaker:  # type: ignore[type-arg]
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _async_session_factory


async def init_db() -> None:
    """
    Create all database tables.

    Called once on application startup. Uses SQLModel.metadata to discover
    all registered table models (imported via database.models).
    """
    # Import all models to ensure they are registered in SQLModel.metadata
    import app.database.models         # noqa: F401
    import app.database.staged_models  # noqa: F401

    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    logger.info("database.tables.created")


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager yielding a database session.

    Usage in services:
        async with get_session() as session:
            result = await session.execute(...)

    Usage as FastAPI dependency: see api/deps.py
    """
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for injecting a database session.

    Use with Depends(get_db_session) in route handlers.
    The session is automatically committed on success and
    rolled back on exception.
    """
    async with get_session() as session:
        yield session
