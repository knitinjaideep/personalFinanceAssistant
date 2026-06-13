"""
Hybrid retrieval for Coral chat — Phase 9.

Retrieval modes:
  fts_only   — SQLite FTS5 BM25 keyword search only
  vector_only — cosine similarity on stored embeddings only
  hybrid     — FTS5 + vector, merged and re-ranked by combined score

Usage:
    from app.chat.retrieval import retrieve, RetrievalMode, RetrievalChunk

    chunks = await retrieve(query, mode="hybrid", top_k=6)

The retrieval layer is called by chat_router / streaming only when
QueryPlan.task_type is "document_search" or "hybrid_analysis".
SQL-routed questions never invoke retrieval.
"""

from __future__ import annotations

import json
import math
from typing import Any, Literal

from pydantic import BaseModel

from app.core.logger import get_logger
from app.db.engine import get_session
from app.db.fts import search_fts
from app.db.models import TextChunkModel
from sqlalchemy import text as sa_text
from sqlmodel import select

logger = get_logger(__name__)

RetrievalMode = Literal["fts_only", "vector_only", "hybrid"]

# Weights for hybrid score fusion (must sum to 1.0)
_FTS_WEIGHT = 0.45
_VEC_WEIGHT = 0.55

# Similarity threshold — chunks below this are discarded from vector results
_VEC_MIN_SCORE = 0.25

# BM25 rank from FTS5 is negative; normalise to [0, 1] using a sigmoid-like scale
_BM25_SCALE = 10.0


class RetrievalChunk(BaseModel):
    """Normalised retrieval result — same shape regardless of mode."""

    chunk_id: str
    document_id: str
    document_name: str = ""       # best-effort; filled if available
    page_number: int | None = None
    institution_type: str = ""
    text: str                      # full chunk text (not just snippet)
    snippet: str = ""              # FTS5 highlighted snippet (may be empty for vector-only)
    score: float                   # final merged score in [0, 1]
    retrieval_method: RetrievalMode


# ── Public entry point ─────────────────────────────────────────────────────────

async def retrieve(
    query: str,
    *,
    mode: RetrievalMode = "hybrid",
    top_k: int = 6,
    institution: str | None = None,
) -> list[RetrievalChunk]:
    """
    Run retrieval in the specified mode and return de-duplicated, ranked chunks.

    Args:
        query:       Natural language query.
        mode:        "fts_only" | "vector_only" | "hybrid"
        top_k:       Max chunks to return.
        institution: Optional institution slug to narrow document scope.

    Returns:
        List of RetrievalChunk sorted by score descending.
    """
    if not query.strip():
        return []

    try:
        if mode == "fts_only":
            return await _fts_retrieve(query, top_k=top_k, institution=institution)
        if mode == "vector_only":
            return await _vector_retrieve(query, top_k=top_k, institution=institution)
        return await _hybrid_retrieve(query, top_k=top_k, institution=institution)
    except Exception as exc:
        logger.warning("retrieval.error", extra={"mode": mode, "error": str(exc)})
        return []


# ── FTS5 retrieval ─────────────────────────────────────────────────────────────

async def _fts_retrieve(
    query: str,
    *,
    top_k: int,
    institution: str | None,
) -> list[RetrievalChunk]:
    from app.services.text_search import _to_fts_query, _to_simple_fts_query

    fts_query = _to_fts_query(query)
    if not fts_query:
        return []

    raw: list[dict] = []
    try:
        raw = await search_fts(fts_query, limit=top_k * 2)
    except Exception:
        simple = _to_simple_fts_query(query)
        if simple:
            try:
                raw = await search_fts(simple, limit=top_k * 2)
            except Exception:
                return []

    chunks = await _hydrate_fts(raw, institution=institution)
    return chunks[:top_k]


async def _hydrate_fts(rows: list[dict], institution: str | None) -> list[RetrievalChunk]:
    """Convert raw FTS5 rows to RetrievalChunk, fetching full content from text_chunks."""
    if not rows:
        return []

    chunk_ids = [r["chunk_id"] for r in rows]
    rank_map: dict[str, float] = {}
    snippet_map: dict[str, str] = {}
    for r in rows:
        cid = r["chunk_id"]
        rank_map[cid] = float(r.get("rank", 0.0))
        snippet_map[cid] = r.get("snippet", "")

    async with get_session() as session:
        result = await session.execute(
            select(TextChunkModel).where(TextChunkModel.id.in_(chunk_ids))
        )
        db_chunks: list[TextChunkModel] = result.scalars().all()

    doc_names = await _fetch_doc_names([c.document_id for c in db_chunks])

    out: list[RetrievalChunk] = []
    for chunk in db_chunks:
        if institution and chunk.institution_type and institution.lower() not in (chunk.institution_type or "").lower():
            continue
        rank = rank_map.get(chunk.id, 0.0)
        # BM25 rank is negative; convert to [0, 1] score
        normalised = 1.0 / (1.0 + math.exp(rank / _BM25_SCALE))
        out.append(RetrievalChunk(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            document_name=doc_names.get(chunk.document_id, ""),
            page_number=chunk.page_number,
            institution_type=chunk.institution_type or "",
            text=chunk.content,
            snippet=snippet_map.get(chunk.id, ""),
            score=round(normalised, 4),
            retrieval_method="fts_only",
        ))

    out.sort(key=lambda c: c.score, reverse=True)
    return out


# ── Vector retrieval ───────────────────────────────────────────────────────────

async def _vector_retrieve(
    query: str,
    *,
    top_k: int,
    institution: str | None,
) -> list[RetrievalChunk]:
    from app.services.llm import embed

    embeddings = await embed([query])
    if not embeddings:
        return []
    query_vec = embeddings[0]

    async with get_session() as session:
        result = await session.execute(
            select(TextChunkModel).where(TextChunkModel.embedding.isnot(None))
        )
        all_chunks: list[TextChunkModel] = result.scalars().all()

    if not all_chunks:
        return []

    scored: list[tuple[TextChunkModel, float]] = []
    for chunk in all_chunks:
        if institution and chunk.institution_type and institution.lower() not in (chunk.institution_type or "").lower():
            continue
        try:
            vec = json.loads(chunk.embedding)  # type: ignore[arg-type]
            sim = _cosine(query_vec, vec)
            if sim >= _VEC_MIN_SCORE:
                scored.append((chunk, sim))
        except (json.JSONDecodeError, ValueError, TypeError):
            continue

    scored.sort(key=lambda x: x[1], reverse=True)

    doc_names = await _fetch_doc_names([c.document_id for c, _ in scored[:top_k]])

    return [
        RetrievalChunk(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            document_name=doc_names.get(chunk.document_id, ""),
            page_number=chunk.page_number,
            institution_type=chunk.institution_type or "",
            text=chunk.content,
            snippet="",
            score=round(sim, 4),
            retrieval_method="vector_only",
        )
        for chunk, sim in scored[:top_k]
    ]


# ── Hybrid retrieval ───────────────────────────────────────────────────────────

async def _hybrid_retrieve(
    query: str,
    *,
    top_k: int,
    institution: str | None,
) -> list[RetrievalChunk]:
    """Run FTS + vector in parallel, merge via Reciprocal Rank Fusion, return top-k."""
    import asyncio

    fts_chunks, vec_chunks = await asyncio.gather(
        _fts_retrieve(query, top_k=top_k * 2, institution=institution),
        _vector_retrieve(query, top_k=top_k * 2, institution=institution),
        return_exceptions=True,
    )

    if isinstance(fts_chunks, Exception):
        logger.warning("retrieval.fts_failed", extra={"error": str(fts_chunks)})
        fts_chunks = []
    if isinstance(vec_chunks, Exception):
        logger.warning("retrieval.vec_failed", extra={"error": str(vec_chunks)})
        vec_chunks = []

    # Build score maps keyed by chunk_id
    fts_score_map: dict[str, RetrievalChunk] = {c.chunk_id: c for c in fts_chunks}  # type: ignore[union-attr]
    vec_score_map: dict[str, RetrievalChunk] = {c.chunk_id: c for c in vec_chunks}   # type: ignore[union-attr]

    all_ids: set[str] = set(fts_score_map) | set(vec_score_map)

    merged: list[RetrievalChunk] = []
    for cid in all_ids:
        fts_c = fts_score_map.get(cid)
        vec_c = vec_score_map.get(cid)

        fts_score = fts_c.score if fts_c else 0.0
        vec_score = vec_c.score if vec_c else 0.0
        combined = _FTS_WEIGHT * fts_score + _VEC_WEIGHT * vec_score

        # Prefer the FTS chunk since it has a highlight snippet; fall back to vector
        base = fts_c or vec_c
        assert base is not None

        merged.append(RetrievalChunk(
            chunk_id=base.chunk_id,
            document_id=base.document_id,
            document_name=base.document_name,
            page_number=base.page_number,
            institution_type=base.institution_type,
            text=base.text,
            snippet=base.snippet or (vec_c.snippet if vec_c else ""),
            score=round(combined, 4),
            retrieval_method="hybrid",
        ))

    merged.sort(key=lambda c: c.score, reverse=True)

    logger.info(
        "retrieval.hybrid_done",
        extra={
            "query_prefix": query[:60],
            "fts_hits": len(fts_score_map),
            "vec_hits": len(vec_score_map),
            "merged": len(merged),
            "returning": min(top_k, len(merged)),
        },
    )
    return merged[:top_k]


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _fetch_doc_names(doc_ids: list[str]) -> dict[str, str]:
    """Return {document_id: filename} for the given ids."""
    if not doc_ids:
        return {}
    unique_ids = list(set(doc_ids))
    # Build parameterised IN clause — SQLite/aiosqlite doesn't support named list params
    placeholders = ",".join(f":id{i}" for i in range(len(unique_ids)))
    params = {f"id{i}": uid for i, uid in enumerate(unique_ids)}
    async with get_session() as session:
        result = await session.execute(
            sa_text(f"SELECT id, filename FROM documents WHERE id IN ({placeholders})"),
            params,
        )
        rows = result.fetchall()
    return {row[0]: row[1] for row in rows}


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Convenience: chunks → citation dicts for StructuredAnswer ─────────────────

def chunks_to_citations(chunks: list[RetrievalChunk]) -> list[dict[str, str]]:
    """Convert RetrievalChunks to the citation format StructuredAnswer expects."""
    out: list[dict[str, str]] = []
    for c in chunks:
        label_parts: list[str] = []
        if c.document_name:
            label_parts.append(c.document_name)
        if c.page_number is not None:
            label_parts.append(f"p.{c.page_number}")
        label_parts.append(f"[{c.retrieval_method}]")
        out.append({
            "source": " · ".join(label_parts) if label_parts else "Document",
            "text": (c.snippet or c.text)[:250],
            "document_id": c.document_id,
        })
    return out
