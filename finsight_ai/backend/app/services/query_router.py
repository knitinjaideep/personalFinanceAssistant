"""
Query router — classifies user questions into structured intents,
then dispatches to the appropriate retrieval path.

SQL-first for numeric/accounting questions.
FTS for document text explanation.
Hybrid for complex financial questions.
"""

from __future__ import annotations

import re
from typing import Any

import structlog

from app.domain.enums import QueryIntent, QueryPath, INTENT_QUERY_PATH
from app.domain.errors import QueryRoutingError

logger = structlog.get_logger(__name__)


# ── Rule-based intent patterns ───────────────────────────────────────────────

_INTENT_PATTERNS: list[tuple[QueryIntent, list[str]]] = [
    (QueryIntent.FEE_SUMMARY, [
        r"(?:total|how much|what)\s+(?:are|were|in)\s+fees",
        r"fee\s+(?:summary|breakdown|total|analysis)",
        r"(?:advisory|management|trading)\s+fees?",
        r"how\s+much\s+(?:did|do)\s+(?:i|we)\s+pay\s+in\s+fees",
    ]),
    (QueryIntent.TRANSACTION_LOOKUP, [
        r"(?:show|list|find|search)\s+(?:my\s+)?transactions",
        r"(?:recent|last|latest)\s+transactions",
        r"transactions?\s+(?:from|for|in|on|at|to)",
        r"(?:did|was|is)\s+there\s+a\s+(?:charge|payment|deposit|purchase)",
        r"spending\s+(?:at|on|for)",
    ]),
    (QueryIntent.BALANCE_LOOKUP, [
        r"(?:what|how\s+much)\s+(?:is|was|are)\s+(?:my|the)\s+balance",
        r"(?:account|total|current)\s+balance",
        r"how\s+much\s+(?:do|did)\s+(?:i|we)\s+have",
        r"(?:net\s+worth|total\s+(?:value|assets))",
    ]),
    (QueryIntent.HOLDINGS_LOOKUP, [
        r"(?:what|which|show|list)\s+(?:are|my)\s+(?:holdings|positions|stocks|investments)",
        r"(?:portfolio|holdings?)\s+(?:summary|breakdown|allocation)",
        r"(?:do|did)\s+(?:i|we)\s+(?:hold|own|have)\s+",
        r"(?:stock|bond|fund|etf)\s+(?:holdings?|positions?)",
    ]),
    (QueryIntent.CASH_FLOW_SUMMARY, [
        r"cash\s+flow",
        r"(?:income|deposits?)\s+(?:vs|versus|and)\s+(?:expenses?|withdrawals?|spending)",
        r"(?:net|total)\s+(?:income|deposits|withdrawals)",
        r"(?:how\s+much)\s+(?:came\s+in|went\s+out|deposited|withdrew)",
    ]),
    (QueryIntent.DOCUMENT_AVAILABILITY, [
        r"(?:what|which)\s+(?:documents?|statements?)\s+(?:do|did|are|have)",
        r"(?:upload|document|statement)\s+(?:status|list|count)",
        r"(?:how\s+many)\s+(?:documents?|statements?|files?)",
    ]),
    (QueryIntent.INSTITUTION_COVERAGE, [
        r"(?:what|which)\s+(?:banks?|institutions?|brokerages?)",
        r"(?:do|did)\s+(?:i|we)\s+have\s+(?:from|at|with)",
        r"institution\s+(?:coverage|summary|list)",
    ]),
    (QueryIntent.STATEMENT_COVERAGE, [
        r"(?:what|which)\s+(?:months?|periods?|dates?)\s+(?:do|are|have)",
        r"statement\s+(?:coverage|range|periods?|dates?)",
        r"(?:from\s+when|earliest|latest|oldest|newest)\s+statement",
    ]),
    (QueryIntent.TEXT_EXPLANATION, [
        r"(?:explain|what\s+does|what\s+is|tell\s+me\s+about|describe)",
        r"(?:what|where)\s+(?:does|did)\s+(?:it|the\s+statement)\s+(?:say|mention)",
        r"(?:read|quote|extract)\s+(?:from|the\s+(?:section|part|paragraph))",
    ]),
]


def classify_intent(question: str) -> tuple[QueryIntent, float]:
    """Classify a user question into a query intent using rule-based patterns.

    Returns:
        Tuple of (intent, confidence).
    """
    question_lower = question.lower().strip()

    # Try pattern matching
    for intent, patterns in _INTENT_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, question_lower):
                return intent, 0.85

    # Fallback heuristics
    if any(word in question_lower for word in ["how much", "total", "sum", "count", "average"]):
        return QueryIntent.HYBRID_FINANCIAL_QUESTION, 0.6

    if any(word in question_lower for word in ["explain", "why", "what does", "describe"]):
        return QueryIntent.TEXT_EXPLANATION, 0.6

    # Default to hybrid
    return QueryIntent.HYBRID_FINANCIAL_QUESTION, 0.4


def get_query_path(intent: QueryIntent) -> QueryPath:
    """Map intent to the primary query path."""
    return INTENT_QUERY_PATH.get(intent, QueryPath.HYBRID)


async def classify_intent_llm(question: str) -> tuple[QueryIntent, float]:
    """Use LLM for intent classification when rule-based is uncertain.

    Only called as a fallback when rule-based confidence is < 0.5.
    """
    from app.services.llm import generate_json

    intents_list = ", ".join(i.value for i in QueryIntent)
    prompt = f"""Classify this financial question into exactly one intent.

Question: {question}

Available intents: {intents_list}

Respond with JSON: {{"intent": "<intent_value>", "confidence": <0.0-1.0>}}"""

    try:
        result = await generate_json(
            prompt,
            system="You are a financial question classifier. Respond with JSON only.",
        )
        intent_str = result.get("intent", "hybrid_financial_question")
        confidence = float(result.get("confidence", 0.5))
        try:
            intent = QueryIntent(intent_str)
        except ValueError:
            intent = QueryIntent.HYBRID_FINANCIAL_QUESTION
        return intent, confidence
    except Exception as exc:
        logger.warning("query_router.llm_classify_failed", error=str(exc))
        return QueryIntent.HYBRID_FINANCIAL_QUESTION, 0.3


async def route_question(question: str) -> tuple[QueryIntent, QueryPath, float]:
    """Full routing: classify intent, optionally use LLM fallback, return path.

    Returns:
        Tuple of (intent, query_path, confidence).
    """
    intent, confidence = classify_intent(question)

    # Use LLM fallback if rule-based confidence is low
    if confidence < 0.5:
        try:
            llm_intent, llm_confidence = await classify_intent_llm(question)
            if llm_confidence > confidence:
                intent, confidence = llm_intent, llm_confidence
        except Exception:
            pass  # Stick with rule-based result

    path = get_query_path(intent)
    logger.info("query.routed", question=question[:80], intent=intent.value,
               path=path.value, confidence=confidence)
    return intent, path, confidence
