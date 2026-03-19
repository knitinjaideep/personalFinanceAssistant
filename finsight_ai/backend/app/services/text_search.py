"""
Text search service — FTS5 full-text search on document chunks.
"""

from __future__ import annotations

import re
from typing import Any

import structlog

from app.config import settings
from app.db.fts import search_fts

logger = structlog.get_logger(__name__)


async def search(query: str, limit: int | None = None) -> list[dict[str, Any]]:
    """Search document chunks using SQLite FTS5.

    Args:
        query: Natural language query (will be converted to FTS5 syntax).
        limit: Max results.

    Returns:
        List of matching chunks with snippets and metadata.
    """
    limit = limit or settings.search.fts_top_k

    # Convert natural language to FTS5-compatible query
    fts_query = _to_fts_query(query)
    if not fts_query:
        return []

    try:
        results = await search_fts(fts_query, limit=limit)
        logger.info("text_search.done", query=query[:80], results=len(results))
        return results
    except Exception as exc:
        logger.warning("text_search.failed", query=query[:80], error=str(exc))
        # Try simpler query on failure
        try:
            simple_query = _to_simple_fts_query(query)
            if simple_query:
                return await search_fts(simple_query, limit=limit)
        except Exception:
            pass
        return []


def _to_fts_query(query: str) -> str:
    """Convert natural language to FTS5 query syntax.

    FTS5 supports: word, "phrase", word1 OR word2, word1 AND word2, word*
    """
    # Remove common question words
    stop_words = {"what", "how", "much", "is", "are", "the", "my", "a", "an", "in", "on",
                  "for", "of", "to", "from", "do", "did", "does", "was", "were", "can",
                  "could", "would", "should", "tell", "me", "about", "show", "find", "list"}

    words = re.findall(r'\w+', query.lower())
    significant = [w for w in words if w not in stop_words and len(w) > 2]

    if not significant:
        return ""

    # Use OR for broad matching
    return " OR ".join(significant)


def _to_simple_fts_query(query: str) -> str:
    """Fallback: just use the longest word."""
    words = re.findall(r'\w+', query.lower())
    words = [w for w in words if len(w) > 3]
    if words:
        return max(words, key=len)
    return ""
