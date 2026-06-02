"""
Bridges the user-facing ``ChatIntent`` taxonomy onto the internal
``QueryIntent`` handlers used by the existing SQL layer, plus a fast rule-based
classifier used as a fallback when the LLM is unavailable or returns garbage.

Keeping this mapping in one place means the SQL handlers in
``app.services.sql_query`` stay untouched.
"""

from __future__ import annotations

import re

from app.domain.classification import (
    ChatIntent,
    DataSource,
    ExtractedEntities,
    IntentClassificationResult,
    TimeRange,
)
from app.domain.enums import QueryIntent
from app.services.normalization import (
    normalize_category,
    normalize_institution,
)

# ── ChatIntent → internal QueryIntent ─────────────────────────────────────────

CHAT_TO_QUERY_INTENT: dict[ChatIntent, QueryIntent] = {
    ChatIntent.TRANSACTION_SEARCH: QueryIntent.TRANSACTION_LOOKUP,
    ChatIntent.SPENDING_SUMMARY: QueryIntent.SPENDING_BY_CATEGORY,
    ChatIntent.INCOME_SUMMARY: QueryIntent.CASH_FLOW_SUMMARY,
    ChatIntent.BALANCE_SUMMARY: QueryIntent.BALANCE_LOOKUP,
    ChatIntent.INVESTMENT_SUMMARY: QueryIntent.HOLDINGS_TOTAL,
    ChatIntent.FEES_SUMMARY: QueryIntent.FEE_SUMMARY,
    ChatIntent.DOCUMENT_LOOKUP: QueryIntent.TEXT_EXPLANATION,
    ChatIntent.ACCOUNT_SUMMARY: QueryIntent.BALANCE_LOOKUP,
    ChatIntent.COMPARISON: QueryIntent.SPENDING_BY_CATEGORY,
    ChatIntent.UNKNOWN: QueryIntent.HYBRID_FINANCIAL_QUESTION,
}

# Default data source recommendation per intent (used when LLM omits it).
DEFAULT_DATA_SOURCE: dict[ChatIntent, DataSource] = {
    ChatIntent.TRANSACTION_SEARCH: DataSource.SQL,
    ChatIntent.SPENDING_SUMMARY: DataSource.SQL,
    ChatIntent.INCOME_SUMMARY: DataSource.SQL,
    ChatIntent.BALANCE_SUMMARY: DataSource.SQL,
    ChatIntent.INVESTMENT_SUMMARY: DataSource.HYBRID,
    ChatIntent.FEES_SUMMARY: DataSource.HYBRID,
    ChatIntent.DOCUMENT_LOOKUP: DataSource.RAG,
    ChatIntent.ACCOUNT_SUMMARY: DataSource.SQL,
    ChatIntent.COMPARISON: DataSource.SQL,
    ChatIntent.UNKNOWN: DataSource.HYBRID,
}


def to_query_intent(intent: ChatIntent) -> QueryIntent:
    return CHAT_TO_QUERY_INTENT.get(intent, QueryIntent.HYBRID_FINANCIAL_QUESTION)


def default_data_source(intent: ChatIntent) -> DataSource:
    return DEFAULT_DATA_SOURCE.get(intent, DataSource.HYBRID)


# ── Rule-based fallback classifier ────────────────────────────────────────────
# Ordered most-specific → least-specific. First match wins.

_INTENT_RULES: list[tuple[ChatIntent, list[str]]] = [
    (ChatIntent.COMPARISON, [
        r"\bcompare\b", r"\bvs\.?\b", r"\bversus\b", r"\bcompared\s+to\b",
        r"\bdifference\s+between\b",
    ]),
    (ChatIntent.FEES_SUMMARY, [
        r"\bfees?\b", r"\bfee\s+(?:summary|breakdown)\b", r"\bcharged?\s+me\b.*\bfee",
        r"\badvisory\s+fee", r"\bfeez\b",  # common typo
    ]),
    (ChatIntent.INVESTMENT_SUMMARY, [
        r"\binvestment[s]?\b", r"\ballocation\b", r"\bportfolio\b", r"\bholdings?\b",
        r"\bpositions?\b", r"\bstocks?\b", r"\bnet\s+worth\b", r"\binvested\b",
    ]),
    (ChatIntent.INCOME_SUMMARY, [
        r"\bincome\b", r"\bsalary\b", r"\bdeposits?\b", r"\bearn(?:ed|ings)?\b",
        r"\bpaycheck\b", r"\bmoney\s+(?:came\s+in|in)\b",
    ]),
    (ChatIntent.BALANCE_SUMMARY, [
        r"\bbalance[s]?\b", r"\bhow\s+much\s+(?:do|did)\s+i\s+have\b",
        r"\bcash\s+(?:balance|on\s+hand)\b",
    ]),
    (ChatIntent.SPENDING_SUMMARY, [
        r"\bspend(?:ing)?\b", r"\bspent\b", r"\bhow\s+much\s+did\s+i\s+spend\b",
        r"\bexpenses?\b", r"\bspending\s+by\s+category\b",
    ]),
    (ChatIntent.DOCUMENT_LOOKUP, [
        r"\bstatement\s+say\b", r"\bwhat\s+does\s+(?:my|the)\b.*\b(?:statement|document)\b",
        r"\binterest\b.*\bstatement\b", r"\bshow\s+me\s+(?:my|the)\s+statement\b",
        r"\bdocument\b", r"\bdisclosure\b", r"\bterms\b",
    ]),
    (ChatIntent.TRANSACTION_SEARCH, [
        r"\btransactions?\b", r"\bcharges?\b", r"\bpurchases?\b", r"\bpayments?\b",
        r"\bshow\s+me\b.*\b(?:from|in|at)\b", r"\blist\b.*\btransactions?\b",
    ]),
    (ChatIntent.ACCOUNT_SUMMARY, [
        r"\baccount\s+summary\b", r"\bmy\s+accounts?\b", r"\boverview\b",
    ]),
]


def rule_classify(question: str) -> IntentClassificationResult:
    """Deterministic classifier used as a fallback when the LLM path fails.

    Extracts a best-effort intent + entities so the pipeline can still route.
    """
    q = question.lower().strip()
    intent = ChatIntent.UNKNOWN
    confidence = 0.0

    for candidate, patterns in _INTENT_RULES:
        if any(re.search(p, q) for p in patterns):
            intent, confidence = candidate, 0.6
            break

    # Entity extraction (best effort).
    inst_slug, _ = normalize_institution(q)
    category = normalize_category(q)

    entities = ExtractedEntities(
        category=category,
        merchant=None,
        institution=inst_slug,
        account=None,
        time_range=_rule_timerange(q),
    )

    data_source = default_data_source(intent)

    return IntentClassificationResult(
        intent=intent,
        confidence=confidence,
        entities=entities,
        data_source=data_source,
        needs_clarification=False,
        clarifying_question=None,
        source="rule_fallback",
    )


def _rule_timerange(q: str) -> TimeRange:
    """Detect a coarse relative time token for the rule fallback."""
    tokens = [
        ("last month", "last_month"), ("this month", "this_month"),
        ("last year", "last_year"), ("this year", "this_year"),
        ("year to date", "ytd"), ("ytd", "ytd"),
    ]
    for phrase, token in tokens:
        if phrase in q:
            return TimeRange(type="relative", value=token)
    m = re.search(r"\b(?:last|past)\s+(\d+)\s+months?\b", q)
    if m:
        return TimeRange(type="relative", value=f"last_{m.group(1)}_months")
    months = ["january", "february", "march", "april", "may", "june", "july",
              "august", "september", "october", "november", "december"]
    for name in months:
        if name in q:
            return TimeRange(type="absolute", value=name)
    m = re.search(r"\bq[1-4]\b.*?\d{0,4}", q)
    if m:
        return TimeRange(type="absolute", value=m.group(0).strip())
    return TimeRange(type="none")
