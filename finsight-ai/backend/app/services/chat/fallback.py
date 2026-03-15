"""
Fallback answer builder — produces a structured answer from retrieved chunks
without calling the LLM.  Used when Stage 3 (generation) times out or stalls.

Instead of dumping raw retrieval text, this module runs the same intent
classification and structured answer builders (numeric / table / comparison)
used by the normal LLM path.  The answer is clearly labelled with caveats so
the user knows no LLM synthesis occurred.
"""

from __future__ import annotations

from app.api.schemas.answer_schemas import (
    AnswerEvidence,
    EvidenceChunk,
    ProseAnswer,
    StructuredAnswer,
)
from app.rag.retriever import RetrievalResult
from app.services.answer_builder import build_structured_answer


def build_retrieval_only_answer(
    question: str,
    retrieval: RetrievalResult,
    reason: str = "generation unavailable",
) -> StructuredAnswer:
    """
    Build a structured answer from retrieval results without LLM generation.

    Runs the same intent classification (numeric / table / comparison / prose)
    and structured builders as the normal path, but with a synthetic prose
    summary assembled from the retrieved data.  Caveats are injected to inform
    the user that this is a retrieval-only answer.

    Args:
        question: The original user question.
        retrieval: The RetrievalResult from Stage 1.
        reason: Short human-readable reason why generation was skipped.

    Returns:
        A typed StructuredAnswer (Numeric / Table / Comparison / Prose).
    """
    # Build a synthetic prose summary from retrieved data so the structured
    # builders have something to populate summary_text fields with.
    chunks = retrieval.vector_chunks[:5]
    sql_results = retrieval.sql_results or []

    prose_parts: list[str] = []
    if sql_results:
        for row in sql_results[:5]:
            prose_parts.append(", ".join(f"{k}: {v}" for k, v in row.items()))
    if chunks:
        for chunk in chunks[:3]:
            excerpt = chunk.get("text", "").strip()
            if excerpt:
                meta = chunk.get("metadata", {})
                source = _format_source(meta)
                prose_parts.append(f"[{source}] {excerpt[:200]}")

    synthetic_prose = "\n".join(prose_parts) if prose_parts else "No relevant data found."

    # Delegate to the shared structured answer builder — this gives us proper
    # NumericAnswer / TableAnswer / ComparisonAnswer rendering.
    answer = build_structured_answer(
        question=question,
        prose_answer=synthetic_prose,
        retrieval=retrieval,
    )

    # Downgrade confidence and inject retrieval-only caveats.
    retrieval_caveats = [
        f"Retrieved directly from your data — LLM generation was skipped ({reason}).",
        "Values shown are from structured records or document excerpts and may be incomplete.",
    ]
    if hasattr(answer, "caveats"):
        answer.caveats = retrieval_caveats + list(answer.caveats)
    if hasattr(answer, "confidence") and answer.confidence is not None:
        # Cap at 0.55 — retrieval-only answers shouldn't appear high-confidence
        answer.confidence = min(answer.confidence, 0.55)

    return answer


def build_safe_error_answer(
    question: str,
    chunks_found: int,
    error_reason: str,
) -> ProseAnswer:
    """
    Absolute last-resort answer when both generation and retrieval-only fail.

    Tells the user how many documents were found and why the answer
    could not be produced.
    """
    evidence = AnswerEvidence(
        chunks=[],
        sql_query=None,
        sql_row_count=None,
        data_source="none",
    )
    text = (
        f"I found {chunks_found} relevant document(s) related to your question, "
        "but was unable to generate an answer at this time.\n\n"
        "Please try again in a moment. If the problem persists, check that the "
        "Ollama service is running and the model is available."
    )
    return ProseAnswer(
        answer_type="prose",
        title="Answer unavailable",
        text=text,
        highlights=[],
        sections=[],
        suggested_followups=["Try asking again", "Check Ollama status"],
        confidence=None,
        caveats=[f"Generation failed: {error_reason}"],
        evidence=evidence,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_source(meta: dict) -> str:
    parts: list[str] = []
    if inst := meta.get("institution_type"):
        parts.append(inst.replace("_", " ").title())
    if period := meta.get("statement_period"):
        parts.append(period)
    if page := meta.get("page_number"):
        parts.append(f"p.{page}")
    return " · ".join(parts) if parts else "Source document"
