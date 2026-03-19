"""
Database engine and session factory.

Async SQLite via aiosqlite. FTS5 virtual table created separately in fts.py.
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

_engine: AsyncEngine | None = None
_session_factory: sessionmaker | None = None  # type: ignore[type-arg]


def _get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        url = settings.get_database_url()
        logger.info("db.engine.create", url=url)
        _engine = create_async_engine(
            url,
            echo=settings.database.echo_sql,
            connect_args={"check_same_thread": False},
        )
    return _engine


def _get_session_factory() -> sessionmaker:  # type: ignore[type-arg]
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _session_factory


async def init_db() -> None:
    """Create all tables on startup."""
    import app.db.models  # noqa: F401 — register all models

    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    # Initialize FTS5 virtual table
    from app.db.fts import init_fts
    await init_fts()

    logger.info("db.tables.created")


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for DB sessions. Auto-commits on success, rolls back on error."""
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for injecting a database session."""
    async with get_session() as session:
        yield session
