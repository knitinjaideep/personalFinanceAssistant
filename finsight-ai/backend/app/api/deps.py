"""
FastAPI dependency injection factories.

All route handlers receive their dependencies via Depends() — never
import concrete implementations directly in route modules.
"""

from __future__ import annotations

from typing import AsyncGenerator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.engine import get_db_session
from app.rag.chroma_store import ChromaStore
from app.services.chat_service import ChatService
from app.services.ingestion_service import IngestionService
from app.services.analytics_service import AnalyticsService


async def get_session(
    session: AsyncSession = Depends(get_db_session),
) -> AsyncSession:
    """Dependency: async DB session."""
    return session


def get_chroma(request: Request) -> ChromaStore:
    """Dependency: the initialized ChromaStore from app state."""
    return request.app.state.chroma


def get_ingestion_service() -> IngestionService:
    return IngestionService()


def get_chat_service() -> ChatService:
    return ChatService()


def get_analytics_service(
    session: AsyncSession = Depends(get_db_session),
) -> AnalyticsService:
    return AnalyticsService(session)
