"""
Vector search service — optional semantic search using Ollama embeddings.

Embeddings stored as JSON arrays in the text_chunks table.
Uses cosine similarity for ranking.
"""

from __future__ import annotations

import json
import math
from typing import Any

import structlog

from app.config import settings
from app.db.engine import get_session
from app.db.models import TextChunkModel
from sqlmodel import select

logger = structlog.get_logger(__name__)


async def search(query: str, limit: int | None = None) -> list[dict[str, Any]]:
    """Semantic search using vector embeddings.

    Args:
        query: Natural language query.
        limit: Max results.

    Returns:
        List of matching chunks ranked by cosine similarity.
    """
    if not settings.search.vector_search_enabled:
        return []

    limit = limit or settings.search.vector_top_k

    try:
        # Generate query embedding
        from app.services.llm import embed
        embeddings = await embed([query])
        if not embeddings:
            return []
        query_vec = embeddings[0]

        # Fetch all chunks with embeddings and rank by cosine similarity
        async with get_session() as session:
            result = await session.execute(
                select(TextChunkModel).where(TextChunkModel.embedding.isnot(None))
            )
            chunks = result.scalars().all()

        if not chunks:
            return []

        # Compute cosine similarity for each chunk
        scored = []
        for chunk in chunks:
            try:
                chunk_vec = json.loads(chunk.embedding)
                similarity = _cosine_similarity(query_vec, chunk_vec)
                scored.append((chunk, similarity))
            except (json.JSONDecodeError, ValueError):
                continue

        # Sort by similarity descending
        scored.sort(key=lambda x: x[1], reverse=True)

        results = []
        for chunk, score in scored[:limit]:
            results.append({
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "content": chunk.content[:500],
                "page_number": chunk.page_number,
                "institution_type": chunk.institution_type,
                "similarity": round(score, 4),
            })

        logger.info("vector_search.done", query=query[:80], results=len(results))
        return results

    except Exception as exc:
        logger.warning("vector_search.failed", query=query[:80], error=str(exc))
        return []


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
