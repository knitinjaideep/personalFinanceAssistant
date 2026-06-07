"""
Query router — classifies user questions into structured intents,
then dispatches to the appropriate retrieval path.

SQL-first for all numeric/accounting questions.
FTS for document text explanation.
Hybrid for complex open-ended financial questions.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logger import get_logger, get_request_id
from app.domain.enums import QueryIntent, QueryPath, INTENT_QUERY_PATH
from app.domain.entities import QueryContext
from app.domain.errors import QueryRoutingError
from app.services.query_context import extract_context

logger = get_logger(__name__)


# ── Rule-based intent patterns ────────────────────────────────────────────────
# Ordered from most-specific to least-specific.  First match wins.

_INTENT_PATTERNS: list[tuple[QueryIntent, list[str]]] = [

    # ── Subscriptions / recurring ────────────────────────────────────────────
    (QueryIntent.SUBSCRIPTION_LOOKUP, [
        r"\bsubscription[s]?\b",
        r"\brecurring\s+(?:charge[s]?|payment[s]?|expense[s]?|bill[s]?)\b",
        r"\bwhat\s+(?:am\s+i|do\s+i)\s+(?:paying|subscribed)\b",
        r"\bmonthly\s+(?:charge[s]?|bill[s]?|subscription[s]?)\b",
        r"\bnetflix|spotify|hulu|apple\s+(?:music|tv|one)|disney\+|prime\b",
    ]),

    # ── Total invested / portfolio value ─────────────────────────────────────
    (QueryIntent.HOLDINGS_TOTAL, [
        r"\btotal\s+invested\b",
        r"\btotal\s+(?:portfolio|investment)\s+(?:value|worth|amount)\b",
        r"\bhow\s+much\s+(?:do\s+i\s+have\s+)?invested\b",
        r"\bwhat\s+is\s+my\s+(?:total\s+)?(?:portfolio|investment)\s+(?:worth|value)\b",
        r"\bnet\s+worth\b",
        r"\btotal\s+(?:assets|wealth)\b",
    ]),

    # ── Spending by category ─────────────────────────────────────────────────
    (QueryIntent.SPENDING_BY_CATEGORY, [
        r"\bhow\s+much\s+(?:did\s+i|have\s+i)\s+spend\b",
        r"\bspend(?:ing)?\s+on\s+\w+",
        r"\bspent\s+on\b",
        r"\bspend(?:ing)?\s+by\s+category\b",
        r"\bcategory\s+breakdown\b",
        r"\bwhat\s+(?:did\s+i|have\s+i)\s+spend\b",
        r"\bhow\s+much\s+(?:for|on)\s+(?:groceries|food|dining|restaurants?|travel|shopping|gas|entertainment|utilities|healthcare|subscriptions?)\b",
        r"\bspend\s+(?:last|this|in)\b",
        r"\bmonthly\s+spend(?:ing)?\b",
    ]),

    # ── Fee summary ──────────────────────────────────────────────────────────
    (QueryIntent.FEE_SUMMARY, [
        r"(?:total|how\s+much|what)\s+(?:are|were|in)\s+fees?",
        r"fee\s+(?:summary|breakdown|total|analysis)",
        r"(?:advisory|management|trading|account)\s+fees?",
        r"how\s+much\s+(?:did|do)\s+(?:i|we)\s+pay\s+in\s+fees?",
        r"what\s+fees?\s+(?:did|do|have)\s+(?:i|we)",
        r"fees?\s+(?:charged|paid|from|by|at)",
        r"morgan\s+stanley\s+fees?",
        r"etrade\s+fees?",
        r"advisory\s+fee",
    ]),

    # ── Transaction lookup (explicit) ────────────────────────────────────────
    (QueryIntent.TRANSACTION_LOOKUP, [
        r"(?:show|list|find|search|get)\s+(?:my\s+)?transactions?",
        r"(?:recent|last|latest)\s+transactions?",
        r"transactions?\s+(?:from|for|in|on|at|to)",
        r"(?:did|was|is)\s+there\s+a\s+(?:charge|payment|deposit|purchase)",
        r"(?:show|list)\s+(?:my\s+)?(?:charges?|payments?|purchases?)",
        r"what\s+(?:did|have)\s+(?:i|we)\s+(?:buy|purchase|pay\s+for)",
    ]),

    # ── Balance lookup ───────────────────────────────────────────────────────
    (QueryIntent.BALANCE_LOOKUP, [
        r"(?:what|how\s+much)\s+(?:is|was|are)\s+(?:my|the)\s+balance",
        r"(?:account|total|current)\s+balance",
        r"how\s+much\s+(?:do|did)\s+(?:i|we)\s+have\s+(?:in|at|with)",
        r"what\s+(?:is|are)\s+my\s+account\s+balance",
        r"balance\s+(?:for|at|in)\b",
        r"cash\s+(?:balance|on\s+hand)\b",
    ]),

    # ── Document availability ────────────────────────────────────────────────
    # (before holdings — "do i have" would otherwise match holdings_lookup)
    (QueryIntent.DOCUMENT_AVAILABILITY, [
        r"(?:what|which)\s+(?:documents?|statements?|files?)\s+(?:do|did|are|have)",
        r"(?:upload|document|statement)\s+(?:status|list|count)",
        r"how\s+many\s+(?:documents?|statements?|files?)",
        r"(?:did|have)\s+(?:you|i)\s+(?:upload|ingest|process|parse)",
        r"(?:are|were|is)\s+(?:my\s+)?(?:documents?|statements?|files?)\s+(?:uploaded|parsed|processed|available)",
        r"(?:show|list)\s+(?:my\s+)?(?:uploaded|available|ingested)\s+(?:documents?|statements?|files?)",
        r"(?:bank\s+of\s+america|chase|amex|discover|morgan\s+stanley|etrade).*(?:upload|document|statement|parsed|processed)",
        r"(?:upload|document|statement|parsed|processed).*(?:bank\s+of\s+america|chase|amex|discover|morgan\s+stanley|etrade)",
    ]),

    # ── Institution coverage ─────────────────────────────────────────────────
    (QueryIntent.INSTITUTION_COVERAGE, [
        r"(?:what|which)\s+(?:banks?|institutions?|brokerages?|accounts?)\s+(?:do|did|are|have)\s+(?:i|we)",
        r"institution\s+(?:coverage|summary|list)",
        r"(?:what|which)\s+institutions?\s+(?:am\s+i\s+connected|have\s+data)",
        r"(?:what|which)\s+(?:banks?|accounts?|institutions?)\s+(?:have\s+(?:you|i)|(?:are|is)\s+(?:there|connected|available))",
        r"(?:do|does)\s+(?:it|coral|the\s+app)\s+have\s+(?:data\s+for|access\s+to)",
        r"(?:which|what)\s+banks?\s+(?:do\s+(?:i|you)\s+have|have\s+(?:data|statements?))",
    ]),

    # ── Statement coverage ───────────────────────────────────────────────────
    (QueryIntent.STATEMENT_COVERAGE, [
        r"(?:what|which)\s+(?:months?|periods?|dates?)\s+(?:do|are|have)",
        r"statement\s+(?:coverage|range|periods?|dates?)",
        r"(?:from\s+when|earliest|latest|oldest|newest)\s+statement",
    ]),

    # ── Holdings lookup ──────────────────────────────────────────────────────
    (QueryIntent.HOLDINGS_LOOKUP, [
        r"(?:what|which|show|list)\s+(?:are|my)\s+(?:holdings?|positions?|stocks?|investments?)",
        r"(?:portfolio|holdings?)\s+(?:summary|breakdown|allocation|positions?)",
        r"(?:do|did)\s+(?:i|we)\s+(?:hold|own|have)\s+(?:any\s+)?(?:holdings?|stocks?|positions?|investments?|funds?|bonds?|etfs?)",
        r"(?:stock|bond|fund|etf)\s+(?:holdings?|positions?)",
        r"what\s+(?:stocks?|funds?|etfs?|bonds?)\s+(?:do|did)\s+(?:i|we)\s+(?:own|hold|have)",
    ]),

    # ── Cash-flow summary ────────────────────────────────────────────────────
    (QueryIntent.CASH_FLOW_SUMMARY, [
        r"\bcash\s+flow\b",
        r"(?:income|deposits?)\s+(?:vs\.?|versus|and)\s+(?:expenses?|withdrawals?|spending)",
        r"(?:net|total)\s+(?:income|deposits?|withdrawals?)",
        r"how\s+much\s+(?:came\s+in|went\s+out|deposited|withdrew)",
        r"money\s+(?:in|out|coming\s+in|going\s+out)\b",
    ]),

    # ── Text / explanation ───────────────────────────────────────────────────
    (QueryIntent.TEXT_EXPLANATION, [
        r"(?:explain|what\s+does|what\s+is|tell\s+me\s+about|describe)",
        r"(?:what|where)\s+(?:does|did)\s+(?:it|the\s+statement)\s+(?:say|mention|show)",
        r"(?:read|quote|extract)\s+(?:from|the)\s+(?:section|part|statement|document)",
    ]),
]


def classify_intent(question: str, ctx: QueryContext) -> tuple[QueryIntent, float]:
    """Classify intent using rule-based patterns, then apply context signals."""
    q = question.lower().strip()

    for intent, patterns in _INTENT_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, q):
                # Boost confidence when supporting context was also extracted
                if _context_supports(intent, ctx):
                    return intent, 0.92
                return intent, 0.85

    # Context-driven fallbacks
    if ctx.is_recurring_only:
        return QueryIntent.SUBSCRIPTION_LOOKUP, 0.75
    if ctx.category:
        return QueryIntent.SPENDING_BY_CATEGORY, 0.70
    if ctx.merchant:
        return QueryIntent.TRANSACTION_LOOKUP, 0.70

    # Generic heuristics
    if any(w in q for w in ["how much", "total", "sum", "amount", "spent", "spend"]):
        return QueryIntent.SPENDING_BY_CATEGORY, 0.60
    if any(w in q for w in ["explain", "why", "what does", "describe", "tell me"]):
        return QueryIntent.TEXT_EXPLANATION, 0.60

    return QueryIntent.HYBRID_FINANCIAL_QUESTION, 0.40


def _context_supports(intent: QueryIntent, ctx: QueryContext) -> bool:
    """Return True when extracted context is consistent with the detected intent."""
    if intent == QueryIntent.SPENDING_BY_CATEGORY and (ctx.category or ctx.date_from):
        return True
    if intent == QueryIntent.FEE_SUMMARY and (ctx.institution or ctx.date_from):
        return True
    if intent == QueryIntent.TRANSACTION_LOOKUP and (ctx.merchant or ctx.date_from):
        return True
    if intent == QueryIntent.SUBSCRIPTION_LOOKUP and ctx.is_recurring_only:
        return True
    if intent == QueryIntent.HOLDINGS_TOTAL:
        return True
    return False


def get_query_path(intent: QueryIntent) -> QueryPath:
    return INTENT_QUERY_PATH.get(intent, QueryPath.HYBRID)


async def classify_intent_llm(question: str) -> tuple[QueryIntent, float]:
    """LLM fallback — only called when rule-based confidence < 0.5."""
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
        logger.warning(
            "query_router.llm_classify_failed",
            extra={"request_id": get_request_id(), "error": str(exc)},
        )
        return QueryIntent.HYBRID_FINANCIAL_QUESTION, 0.3


async def route_question(question: str) -> tuple[QueryIntent, QueryPath, float, QueryContext]:
    """Full routing: extract context → classify intent → optionally use LLM fallback.

    Returns:
        (intent, query_path, confidence, query_context)
    """
    ctx = extract_context(question)
    intent, confidence = classify_intent(question, ctx)

    if confidence < 0.5:
        try:
            llm_intent, llm_confidence = await classify_intent_llm(question)
            if llm_confidence > confidence:
                intent, confidence = llm_intent, llm_confidence
        except Exception:
            pass

    path = get_query_path(intent)
    logger.info(
        "query.routed",
        extra={
            "stage": "query_routed",
            "request_id": get_request_id(),
            "intent": intent.value,
            "route": path.value,
            "confidence": round(confidence, 3),
            "timeframe": ctx.timeframe_label or None,
            "date_from": str(ctx.date_from) if ctx.date_from else None,
            "date_to": str(ctx.date_to) if ctx.date_to else None,
            "category": ctx.category,
            "merchant": ctx.merchant,
            "institution": ctx.institution,
        },
    )
    return intent, path, confidence, ctx
