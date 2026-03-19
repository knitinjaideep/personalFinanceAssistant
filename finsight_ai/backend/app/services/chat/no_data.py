"""
Deterministic no-data and partial-data answer builders.

These run when retrieval returns no (or very few) chunks and no SQL rows.
They NEVER call the LLM — they build a polished, bucket-aware response from
structured logic alone.

Design goals:
- Never say "The provided context does not include..."
- Always ground the message in the specific bucket / institution searched
- Make the response feel like a financial assistant, not a generic RAG bot
- Always emit a response_complete terminal event so the pipeline never gets stuck
"""

from __future__ import annotations

from typing import Optional

from app.api.schemas.answer_schemas import (
    AnswerEvidence,
    EvidenceChunk,
    NoDataAnswer,
    PartialDataAnswer,
)
from app.rag.retriever import RetrievalResult


# ---------------------------------------------------------------------------
# Bucket-aware context helpers
# ---------------------------------------------------------------------------

def _bucket_phrase(bucket_label: Optional[str], institution_labels: list[str]) -> str:
    """
    Build a grounding phrase like "in the Banking bucket" or
    "in your Chase and Morgan Stanley documents".
    """
    if bucket_label and institution_labels:
        insts = _join_list(institution_labels)
        return f"in the {bucket_label} bucket ({insts})"
    elif bucket_label:
        return f"in the {bucket_label} bucket"
    elif institution_labels:
        insts = _join_list(institution_labels)
        return f"in your {insts} documents"
    return "in your uploaded documents"


def _join_list(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _infer_topic(question: str) -> str:
    """Return a short human-readable topic label from the question."""
    q = question.lower()
    if any(w in q for w in ("transaction", "charge", "purchase", "payment")):
        return "transaction data"
    if any(w in q for w in ("fee", "fees")):
        return "fee data"
    if any(w in q for w in ("balance", "account balance")):
        return "account balance data"
    if any(w in q for w in ("holding", "investment", "portfolio", "stock")):
        return "investment data"
    if any(w in q for w in ("deposit", "withdrawal", "transfer")):
        return "cash flow data"
    if any(w in q for w in ("statement", "document")):
        return "statement data"
    return "financial data"


def _suggest_followups_for_no_data(question: str) -> list[str]:
    """Context-sensitive follow-up suggestions when nothing is found."""
    q = question.lower()
    base = [
        "Which statements have been uploaded and parsed?",
        "Show me what data is available.",
    ]
    if any(w in q for w in ("transaction", "charge", "purchase")):
        base.insert(0, "What is the date range of my uploaded statements?")
    elif any(w in q for w in ("fee",)):
        base.insert(0, "Show my largest transactions instead.")
    elif any(w in q for w in ("balance", "account")):
        base.insert(0, "List my accounts and their last known balances.")
    else:
        base.insert(0, "What financial institutions do I have data for?")
    return base[:3]


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------

def build_no_data_answer(
    question: str,
    retrieval: RetrievalResult,
    bucket_label: Optional[str] = None,
    institution_labels: Optional[list[str]] = None,
) -> NoDataAnswer:
    """
    Build a polished NoDataAnswer without calling the LLM.

    Called when retrieval returns 0 vector chunks AND 0 SQL rows.

    Args:
        question:            The user's original question.
        retrieval:           The empty RetrievalResult.
        bucket_label:        Human-readable bucket name, e.g. 'Banking'.
        institution_labels:  List of institution names searched, e.g. ['Chase'].

    Returns:
        A fully-typed NoDataAnswer with grounded, product-quality copy.
    """
    insts = institution_labels or []
    topic = _infer_topic(question)
    scope_phrase = _bucket_phrase(bucket_label, insts)

    # Build grounded summary — conversational, not robotic
    if insts:
        inst_str = _join_list(insts)
        summary = (
            f"I looked for {topic} across your {inst_str} statements "
            f"{scope_phrase}, but didn't find any matching records yet."
        )
    else:
        summary = (
            f"I searched for {topic} {scope_phrase}, "
            "but there aren't any matching records yet."
        )

    what_was_checked: list[str] = [
        "Document text and indexed chunks",
        "Structured records (transactions, fees, balances, holdings)",
    ]
    if bucket_label:
        what_was_checked.append(f"Scoped to {bucket_label}")

    possible_reasons = [
        "No statements have been uploaded for this area yet.",
        "Statements were uploaded but may not have parsed successfully — check the document list on the Home tab.",
        "The date range or account type in your question may not match what's been uploaded.",
    ]
    if bucket_label:
        other_bucket = "Investments" if bucket_label == "Banking" else "Banking"
        possible_reasons.append(
            f"Try switching to {other_bucket} if you're looking for a different account type."
        )

    return NoDataAnswer(
        title=f"No {topic} found",
        summary=summary,
        what_was_checked=what_was_checked,
        possible_reasons=possible_reasons,
        suggested_followups=_suggest_followups_for_no_data(question),
        confidence=0.0,
        caveats=[],
        evidence=AnswerEvidence(
            chunks=[],
            sql_query=retrieval.sql_query,
            sql_row_count=0,
            data_source="none",
        ),
        bucket_label=bucket_label,
        institution_labels=insts,
    )


def build_partial_data_answer(
    question: str,
    retrieval: RetrievalResult,
    bucket_label: Optional[str] = None,
    institution_labels: Optional[list[str]] = None,
) -> PartialDataAnswer:
    """
    Build a PartialDataAnswer when some context exists but is insufficient
    for a precise answer.

    Called when retrieval returns 1–2 chunks and no SQL rows, or when SQL
    returns rows but they appear incomplete.

    Args:
        question:            The user's original question.
        retrieval:           The sparse RetrievalResult (some chunks, no SQL).
        bucket_label:        Human-readable bucket name.
        institution_labels:  Institution names found in the chunks.

    Returns:
        A fully-typed PartialDataAnswer.
    """
    insts = institution_labels or []
    topic = _infer_topic(question)
    chunk_count = len(retrieval.vector_chunks)
    scope_phrase = _bucket_phrase(bucket_label, insts)

    summary = (
        f"I found {chunk_count} document excerpt{'' if chunk_count == 1 else 's'} "
        f"related to {topic} {scope_phrase}, but not enough to give you a complete answer. "
        "The information below is the best I could retrieve from your uploaded statements."
    )

    what_was_found: list[str] = []
    for chunk in retrieval.vector_chunks[:3]:
        meta = chunk.get("metadata", {})
        inst = meta.get("institution_type", "")
        period = meta.get("statement_period", "")
        section = meta.get("section", "")
        parts = [p for p in [inst.replace("_", " ").title() if inst else "", period, section] if p]
        what_was_found.append(" · ".join(parts) if parts else "Document excerpt")

    what_is_missing = [
        "Structured transaction or fee records (not yet available in the database)",
        f"More complete statements covering the period in your question",
    ]

    evidence_chunks: list[EvidenceChunk] = [
        EvidenceChunk(
            id=c.get("id", ""),
            document_id=c.get("metadata", {}).get("document_id", ""),
            chunk_text=c.get("text", ""),
            page_number=c.get("metadata", {}).get("page_number"),
            section=c.get("metadata", {}).get("section"),
            institution_type=c.get("metadata", {}).get("institution_type"),
            statement_period=c.get("metadata", {}).get("statement_period"),
            relevance_score=c.get("score"),
        )
        for c in retrieval.vector_chunks[:5]
    ]

    return PartialDataAnswer(
        title=f"Limited {topic} available",
        summary=summary,
        what_was_found=what_was_found,
        what_is_missing=what_is_missing,
        suggested_followups=_suggest_followups_for_no_data(question),
        confidence=0.20,
        caveats=[
            "Only partial data was found. The answer may be incomplete.",
            "Upload additional statements to improve coverage.",
        ],
        evidence=AnswerEvidence(
            chunks=evidence_chunks,
            sql_query=retrieval.sql_query,
            sql_row_count=len(retrieval.sql_results) if retrieval.sql_results else None,
            data_source="vector" if retrieval.vector_chunks else "none",
        ),
        bucket_label=bucket_label,
        institution_labels=insts,
    )
