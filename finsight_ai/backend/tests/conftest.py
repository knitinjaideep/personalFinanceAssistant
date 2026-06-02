"""
Shared pytest fixtures.

Provides an isolated, file-backed SQLite database per test so the reprocess /
ingestion-health tests never touch the developer's real finsight.db.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def temp_db(tmp_path: Path, monkeypatch):
    """Point the app at a fresh temp SQLite DB and rebuild the engine.

    Yields nothing useful — tests use repositories / services which read the
    module-global engine that this fixture rebuilds.
    """
    from app.config import settings
    from app.db import engine as engine_mod

    # Disable embeddings so tests don't require a running Ollama.
    monkeypatch.setattr(settings.search, "vector_search_enabled", False, raising=False)

    # Point the DB at a unique temp file (relative to base_dir, as the app expects).
    rel = f"data/db/test_{uuid.uuid4().hex}.db"
    abs_path = settings.base_dir / rel
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings.database, "path", rel, raising=False)

    # Reset cached engine/session factory so they pick up the new path.
    engine_mod._engine = None
    engine_mod._session_factory = None

    await engine_mod.init_db()

    yield

    # Teardown: dispose engine and remove the temp DB file.
    if engine_mod._engine is not None:
        await engine_mod._engine.dispose()
    engine_mod._engine = None
    engine_mod._session_factory = None
    try:
        abs_path.unlink(missing_ok=True)
    except OSError:
        pass
