"""
SQLite FTS5 full-text search setup and query functions.

FTS5 is the primary text search mechanism. The virtual table mirrors
text_chunks.content and allows fast full-text queries without external dependencies.
"""

from __future__ import annotations

import structlog
from sqlalchemy import text

from app.db.engine import get_session

logger = structlog.get_logger(__name__)


async def init_fts() -> None:
    """Create the FTS5 virtual table if it doesn't exist.

    Standalone FTS5 table (not external-content) — content is stored directly
    in the FTS index alongside UNINDEXED metadata columns for filtering.
    This avoids sync issues with external content tables.
    """
    async with get_session() as session:
        # Check if we need to migrate from the broken external-content table
        result = await session.execute(text(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='text_chunks_fts'"
        ))
        row = result.fetchone()
        if row and "content='text_chunks'" in (row[0] or ""):
            # Drop broken external-content FTS table and recreate as standalone
            await session.execute(text("DROP TABLE IF EXISTS text_chunks_fts"))
            logger.info("fts.dropped_external_content_table")

        await session.execute(text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS text_chunks_fts USING fts5(
                content,
                document_id UNINDEXED,
                chunk_id UNINDEXED,
                institution_type UNINDEXED,
                page_number UNINDEXED
            )
        """))
        await session.commit()
        logger.info("fts.initialized")


async def index_chunk(chunk_id: str, content: str, document_id: str,
                      institution_type: str = "", page_number: int | None = None) -> None:
    """Insert a single chunk into the FTS5 index."""
    async with get_session() as session:
        await session.execute(text("""
            INSERT INTO text_chunks_fts(content, document_id, chunk_id, institution_type, page_number)
            VALUES (:content, :document_id, :chunk_id, :institution_type, :page_number)
        """), {
            "content": content,
            "document_id": document_id,
            "chunk_id": chunk_id,
            "institution_type": institution_type,
            "page_number": str(page_number) if page_number else "",
        })


async def search_fts(query: str, limit: int = 10) -> list[dict]:
    """Search text chunks using FTS5.

    Returns list of dicts with chunk_id, document_id, content snippet, and rank.
    """
    async with get_session() as session:
        # FTS5 match with ranking
        result = await session.execute(text("""
            SELECT
                chunk_id,
                document_id,
                snippet(text_chunks_fts, 0, '<b>', '</b>', '...', 32) as snippet,
                institution_type,
                page_number,
                rank
            FROM text_chunks_fts
            WHERE text_chunks_fts MATCH :query
            ORDER BY rank
            LIMIT :limit
        """), {"query": query, "limit": limit})

        rows = result.fetchall()
        return [
            {
                "chunk_id": row[0],
                "document_id": row[1],
                "snippet": row[2],
                "institution_type": row[3],
                "page_number": row[4],
                "rank": row[5],
            }
            for row in rows
        ]


async def delete_fts_for_document(document_id: str) -> None:
    """Remove all FTS entries for a document."""
    async with get_session() as session:
        await session.execute(text("""
            DELETE FROM text_chunks WHERE document_id = :document_id
        """), {"document_id": document_id})
        # For standalone FTS5 tables, delete matching rows directly
        await session.execute(text("""
            DELETE FROM text_chunks_fts WHERE document_id = :document_id
        """), {"document_id": document_id})


