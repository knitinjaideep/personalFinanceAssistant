"""
Bridges the user-facing ``ChatIntent`` taxonomy onto the internal
``QueryIntent`` handlers used by the SQL layer, plus a comprehensive
rule-based classifier that is the PRIMARY classification path.

The LLM classifier is only invoked for questions that the rule classifier
cannot confidently resolve (confidence < RULE_CONFIDENCE_THRESHOLD).
"""

from __future__ import annotations

import re

from app.domain.classification import (
    ChatIntent,
    DataSource,
    ExtractedEntities,
    IntentClassificationResult,
    RouteDecision,
    RouteRisk,
    RouteType,
    TimeRange,
)
from app.domain.enums import QueryIntent
from app.services.normalization import (
    normalize_category,
    normalize_institution,
)

# Minimum rule-classifier confidence before we skip the LLM entirely.
RULE_CONFIDENCE_THRESHOLD = 0.75

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
    ChatIntent.COMPARISON: QueryIntent.SPENDING_COMPARISON,
    ChatIntent.RECURRING_TRANSACTIONS: QueryIntent.RECURRING_TRANSACTIONS,
    ChatIntent.UNKNOWN: QueryIntent.HYBRID_FINANCIAL_QUESTION,
}

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
    ChatIntent.RECURRING_TRANSACTIONS: DataSource.SQL,
    ChatIntent.UNKNOWN: DataSource.HYBRID,
}


def to_query_intent(intent: ChatIntent) -> QueryIntent:
    return CHAT_TO_QUERY_INTENT.get(intent, QueryIntent.HYBRID_FINANCIAL_QUESTION)


def default_data_source(intent: ChatIntent) -> DataSource:
    return DEFAULT_DATA_SOURCE.get(intent, DataSource.HYBRID)


# ── Intent rule definitions ────────────────────────────────────────────────────
# Each rule: (intent, strong_patterns, weak_patterns)
#   strong: any single match → high confidence (0.92)
#   weak:   need 2+ matches OR combined with other signals → medium (0.78)
# Rules are ordered most-specific first; first strong match wins.

_RULES: list[tuple[ChatIntent, list[str], list[str]]] = [
    (ChatIntent.COMPARISON, [
        r"\bcompare\b",
        r"\bvs\.?\b",
        r"\bversus\b",
        r"\bcompared\s+to\b",
        r"\bdifference\s+between\b",
        r"\bmore\s+(?:than|in|on)\b.{0,40}\b(?:january|february|march|april|may|june|july|august|september|october|november|december|last\s+month|this\s+month|the\s+month\s+before|previous\s+month)\b",
        r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b.{0,30}\bvs\b",
        r"\b(?:last\s+month|this\s+month|previous\s+month).{0,40}\b(?:or|vs\.?)\b.{0,40}\b(?:month\s+before|previous\s+month|prior\s+month)\b",
        r"\bdid\s+i\s+spend\s+more\b",
    ], []),

    (ChatIntent.RECURRING_TRANSACTIONS, [
        r"\brecurring\b",
        r"\bsubscriptions?\b",
        r"\bmemberships?\b",
        r"\bauto-?pay\b",
        r"\bautomatic\s+(?:payment|charge|bill)\b",
        r"\bmonthly\s+(?:charge|bill|payment)\b",
        r"\brepeat(?:ing|ed)?\s+(?:charge|payment|transaction)\b",
        r"\bwhat\s+(?:am\s+i|do\s+i)\s+paying\s+(?:monthly|every\s+month|regularly)\b",
    ], [
        r"\bnetflix\b", r"\bspotify\b", r"\bhulu\b", r"\bdisney\+?\b",
    ]),

    (ChatIntent.FEES_SUMMARY, [
        r"\bfees?\s+(?:summary|breakdown|total|charged|paid)\b",
        r"\badvisory\s+fee\b",
        r"\bmanagement\s+fee\b",
        r"\btrading\s+fee\b",
        r"\bwhat\s+fees?\b",
        r"\bhow\s+much\s+(?:in\s+)?fees?\b",
        r"\bfees?\s+(?:did|do|have)\b",
        r"\btotal\s+fees?\b",
        r"\bfees?\s+(?:in|for|charged|paid)\b",
        r"\b(?:morgan\s*stan(?:ley|ly|ley|ely)|chase|amex|discover|etrade|fidelity|schwab)\b.{0,30}\bfee[zs]?\b",
        r"\bfee[zs]?\b.{0,30}\b(?:morgan\s*stan(?:ley|ly|ley|ely)|chase|amex|discover|etrade)\b",
    ], [
        r"\bfee[zs]?\b", r"\bcharged?\s+(?:me|us)\b", r"\bpenalt(?:y|ies)\b",
    ]),

    (ChatIntent.INVESTMENT_SUMMARY, [
        r"\bportfolio\b",
        r"\bholdings?\b",
        r"\ballocation\b",
        r"\bnet\s+worth\b",
        r"\binvestment\s+(?:summary|total|value|balance|performance)\b",
        r"\bhow\s+much\s+(?:is\s+)?(?:my\s+)?(?:portfolio|invested|in\s+stocks|in\s+etf|in\s+bonds)\b",
        r"\bpositions?\b",
        r"\bwhat\s+(?:am\s+i|do\s+i\s+have)\s+invested\b",
        r"\bstock\s+(?:holdings?|positions?|portfolio)\b",
        r"\b(?:morgan\s+stanley|etrade|e\*trade)\b.{0,40}\b(?:total|balance|value|holding)\b",
        r"\btotal\s+invested\b",
        r"\bhow\s+much\s+(?:is|are)\s+(?:my\s+)?(?:total\s+)?invest(?:ed|ment|ments)\b",
        r"\bmy\s+(?:total\s+)?invested\s+(?:amount|value|balance)\b",
    ], [
        r"\binvested?\b", r"\bstocks?\b", r"\bbonds?\b", r"\betf\b",
        r"\bequit(?:y|ies)\b", r"\bsecurities\b",
    ]),

    (ChatIntent.INCOME_SUMMARY, [
        r"\bincome\s+(?:summary|total|this\s+month|last\s+month|ytd|this\s+year)\b",
        r"\bhow\s+much\s+(?:did\s+i|have\s+i)\s+(?:earned?|made|received|brought\s+in)\b",
        r"\bhow\s+much\s+(?:did\s+i|have\s+i)\s+earn(?:ed)?\b",
        r"\bpaycheck\b",
        r"\bdirect\s+deposit\b",
        r"\bsalary\b",
        r"\bwages?\b",
        r"\bmoney\s+(?:coming\s+in|i\s+received|deposited)\b",
        r"\btotal\s+(?:deposits?|income|inflow)\b",
        r"\bhow\s+much\s+(?:did\s+i|have\s+i)\s+(?:made?|received?)\b",
        r"\bhow\s+much\s+money\s+(?:came\s+in|did\s+i\s+(?:receive|make|earn|get))\b",
    ], [
        r"\bdeposit\b", r"\bearned?\b", r"\bincome\b",
    ]),

    (ChatIntent.BALANCE_SUMMARY, [
        r"\b(?:what(?:'s|\s+is)\s+(?:my\s+)?(?:\w+\s+){0,3})balance[s]?\b",
        r"\bhow\s+much\s+(?:do|did)\s+i\s+have\b",
        r"\bcash\s+(?:balance|on\s+hand)\b",
        r"\baccount\s+balances?\b",
        r"\bending\s+balance\b",
        r"\bcurrent\s+(?:balance|amount)\b",
        r"\bwhat\s+do\s+i\s+have\s+in\b",
        r"\bwhat\s+(?:are|is)\s+my\s+(?:\w+\s+){0,4}balance[s]?\b",
        r"\bmy\s+(?:\w+\s+){0,3}balance[s]?\b",
    ], [
        r"\bbalances?\b",
    ]),

    (ChatIntent.DOCUMENT_LOOKUP, [
        r"\bwhat\s+does\s+(?:my|the)\b.{0,30}\b(?:statement|document)\s+say\b",
        r"\bshow\s+me\s+(?:my|the)\s+(?:full\s+)?statement\b",
        r"\bstatement\s+(?:say|states?|mentions?|shows?)\b",
        r"\bdisclosure\b",
        r"\bterms\s+and\s+conditions\b",
        r"\binterest\s+rate\s+(?:on|in|from)\s+(?:my|the)\s+statement\b",
        r"\bwhat\s+(?:does|did)\s+(?:amex|chase|discover|morgan|etrade)\b.{0,30}\bsay\b",
        r"\bwhat\s+statements?\s+(?:do\s+i\s+have|are\s+available|have\s+i\s+uploaded)\b",
        r"\bstatements?\s+(?:do\s+i\s+have|available|uploaded|from)\b",
    ], [
        r"\bdocument\b", r"\bstatement\b.{0,20}\b(?:says?|shows?|mentions?|have|from)\b",
    ]),

    # spending_summary must come before transaction_search (more specific)
    (ChatIntent.SPENDING_SUMMARY, [
        r"\bhow\s+much\s+(?:did\s+i\s+|have\s+i\s+)?spent?\b",
        r"\bhow\s+much\s+(?:did\s+i\s+|have\s+i\s+)?spend\b",
        r"\btotal\s+(?:spent?|spending|spend|expenses?)\b",
        r"\bspending\s+(?:by\s+category|breakdown|summary|this\s+month|last\s+month|in\s+\w+)\b",
        r"\bexpense\s+(?:summary|breakdown|report|total)\b",
        r"\bwhat\s+(?:did\s+i|have\s+i)\s+(?:spent?|spend)\b",
        r"\bmonthly\s+(?:spend|spending|expenses?)\b",
        r"\bspend(?:ing)?\s+by\b",
        r"\btop\s+\d*\s*(?:categories|merchants?|expenses?|spending)\b",
        r"\b(?:dining|grocery|groceries|food|restaurant|entertainment|travel|shopping|utilities|gas|fuel|healthcare|medical)\s+(?:spend|spending|expenses?)\b",
        r"\b(?:my\s+)?(?:dining|grocery|groceries|food|restaurant|entertainment|travel|shopping)\s+(?:budget|cost|costs|total|amount)\b",
        r"\bwhy\s+(?:did|was|is|are)\s+(?:my\s+)?(?:\w+\s+){0,3}(?:spending|spend|expenses?|charges?|bill)\b",
        r"\bhow\s+much\s+(?:is\s+)?(?:my\s+)?(?:\w+\s+){0,3}(?:spend|spending)\b",
        r"\bwhat\s+about\b.{0,40}\b(?:dining|grocery|groceries|food|restaurant|entertainment|travel|shopping|spending|spend|expenses?)\b",
        r"\bwhat\s+about\b.{0,30}\b(?:january|february|march|april|may|june|july|august|september|october|november|december|last\s+month|this\s+month|this\s+quarter|this\s+year)\b",
    ], [
        r"\bspend(?:ing)?\b", r"\bspent\b", r"\bexpenses?\b",
    ]),

    (ChatIntent.TRANSACTION_SEARCH, [
        r"\bshow\s+(?:me\s+)?(?:\w+\s+){0,4}transactions?\b",
        r"\blist\b.{0,25}\b(?:transactions?|charges?|purchases?|payments?)\b",
        r"\bfind\s+(?:all\s+|the\s+)?transactions?\b",
        r"\bwhat\s+(?:transactions?|charges?|purchases?)\b",
        r"\brecent\s+(?:transactions?|charges?|purchases?|activity)\b",
        r"\blast\s+\d+\s+(?:transactions?|charges?|purchases?)\b",
        r"\b(?:charges?|purchases?)\s+(?:from|at|to|on)\b",
        r"\btransactions?\s+(?:from|at|in|on|over|under|above|below|between)\b",
        r"\bpayments?\s+(?:to|from|made|i\s+made)\b",
        r"\bwhere\s+did\s+i\s+(?:spend|buy|shop|pay)\b",
        r"\bshow\s+(?:me\s+)?(?:all\s+)?(?:my\s+)?(?:\w+\s+){0,5}(?:charges?|transactions?|purchases?)\b",
        r"\bfind\s+(?:\w+\s+){0,3}charges?\b",
    ], [
        r"\btransactions?\b", r"\bcharges?\b", r"\bpurchases?\b",
    ]),

    (ChatIntent.ACCOUNT_SUMMARY, [
        r"\baccount\s+(?:summary|overview|details?)\b",
        r"\bmy\s+accounts?\s+(?:overview|summary)\b",
        r"\boverall\s+(?:summary|overview)\b",
        r"\bwhat\s+accounts?\s+do\s+i\s+have\b",
        r"\bgive\s+me\s+(?:a\s+)?(?:summary|overview)\s+of\s+(?:my\s+)?accounts?\b",
    ], [
        r"\boverview\b", r"\bsummary\b",
    ]),
]


# ── Merchant extraction ────────────────────────────────────────────────────────

# Known merchants to detect directly from question text
_KNOWN_MERCHANTS: list[str] = [
    "amazon", "whole foods", "trader joe", "target", "walmart", "costco",
    "starbucks", "mcdonald", "chipotle", "uber eats", "doordash", "grubhub",
    "netflix", "spotify", "hulu", "disney", "apple", "google",
    "shell", "chevron", "exxon", "bp",
    "delta", "united", "southwest", "american airlines",
    "marriott", "hilton", "airbnb",
    "cvs", "walgreens", "rite aid",
    "zelle", "venmo", "paypal",
]

_AT_MERCHANT_RE = re.compile(
    r"\b(?:at|from|to|for|with)\s+([A-Za-z][A-Za-z0-9'\s\*\-]{1,30}?)(?:\s+(?:in|on|last|this|from|for|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d)|\s*$|[,?!])",
    re.IGNORECASE,
)


def _extract_merchant(q: str) -> str | None:
    """Extract a merchant name from the lowercased question."""
    for m in _KNOWN_MERCHANTS:
        if m in q:
            return m
    # "at TARGET", "from Amazon", "to Venmo"
    _REJECT_CANDIDATES = {
        "chase", "amex", "discover", "morgan stanley", "etrade",
        "bank of america", "marcus",
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
        "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
        "last month", "this month", "last year", "this year",
    }
    m = _AT_MERCHANT_RE.search(q)
    if m:
        candidate = m.group(1).strip().lower()
        if candidate not in _REJECT_CANDIDATES:
            return candidate
    return None


# ── Amount filter extraction ───────────────────────────────────────────────────

_AMOUNT_OVER_RE = re.compile(r"\b(?:over|above|more\s+than|greater\s+than|exceeding)\s+\$?([\d,]+(?:\.\d{1,2})?)\b", re.IGNORECASE)
_AMOUNT_UNDER_RE = re.compile(r"\b(?:under|below|less\s+than|smaller\s+than)\s+\$?([\d,]+(?:\.\d{1,2})?)\b", re.IGNORECASE)
_AMOUNT_BETWEEN_RE = re.compile(r"\bbetween\s+\$?([\d,]+(?:\.\d{1,2})?)\s+and\s+\$?([\d,]+(?:\.\d{1,2})?)\b", re.IGNORECASE)


def _extract_amounts(q: str) -> tuple[float | None, float | None]:
    m = _AMOUNT_BETWEEN_RE.search(q)
    if m:
        return float(m.group(1).replace(",", "")), float(m.group(2).replace(",", ""))
    lo = _AMOUNT_OVER_RE.search(q)
    hi = _AMOUNT_UNDER_RE.search(q)
    amount_min = float(lo.group(1).replace(",", "")) if lo else None
    amount_max = float(hi.group(1).replace(",", "")) if hi else None
    return amount_min, amount_max


# ── Time range extraction ──────────────────────────────────────────────────────

_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2,
    "march": 3, "mar": 3, "april": 4, "apr": 4,
    "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

_MONTH_PATTERN = r"\b(" + "|".join(_MONTHS) + r")\b"
_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_QUARTER_RE = re.compile(r"\bq([1-4])\b(?:\s+(?:of\s+)?(20\d{2}))?\b", re.IGNORECASE)
_LAST_N_MONTHS_RE = re.compile(r"\b(?:last|past)\s+(\d+)\s+months?\b", re.IGNORECASE)


def _extract_timerange(q: str) -> TimeRange:
    # Explicit relative phrases (ordered longest first to avoid partial matches)
    relative_tokens = [
        ("last month", "last_month"),
        ("previous month", "last_month"),
        ("prior month", "last_month"),
        ("this month", "this_month"),
        ("current month", "this_month"),
        ("last year", "last_year"),
        ("previous year", "last_year"),
        ("this year", "this_year"),
        ("current year", "this_year"),
        ("year to date", "ytd"),
        ("ytd", "ytd"),
        ("last week", "last_week"),
        ("this week", "this_week"),
        ("last quarter", "last_quarter"),
        ("this quarter", "this_quarter"),
    ]
    for phrase, token in relative_tokens:
        if phrase in q:
            return TimeRange(type="relative", value=token)

    m = _LAST_N_MONTHS_RE.search(q)
    if m:
        return TimeRange(type="relative", value=f"last_{m.group(1)}_months")

    # Quarter
    m = _QUARTER_RE.search(q)
    if m:
        qnum = m.group(1)
        year = m.group(2) or ""
        token = f"q{qnum}_{year}".strip("_")
        return TimeRange(type="absolute", value=token)

    # "January 2025" or just "January"
    month_re = re.search(_MONTH_PATTERN, q, re.IGNORECASE)
    if month_re:
        month_name = month_re.group(1).lower()
        year_m = _YEAR_RE.search(q)
        if year_m:
            return TimeRange(type="absolute", value=f"{month_name}_{year_m.group(1)}")
        return TimeRange(type="absolute", value=month_name)

    # Bare year
    year_m = _YEAR_RE.search(q)
    if year_m:
        return TimeRange(type="absolute", value=year_m.group(1))

    return TimeRange(type="none")


# ── Core rule classifier ───────────────────────────────────────────────────────

def rule_classify(question: str) -> IntentClassificationResult:
    """Deterministic classifier — primary classification path.

    Returns confidence >= 0.92 for strong keyword matches, 0.78 for weak
    multi-signal matches, 0.0 for UNKNOWN.

    This is intentionally the first (and usually only) classifier called.
    The LLM is only invoked when confidence < RULE_CONFIDENCE_THRESHOLD.
    """
    q = question.lower().strip()

    intent = ChatIntent.UNKNOWN
    confidence = 0.0

    for candidate, strong_patterns, weak_patterns in _RULES:
        # Strong match: any single pattern → high confidence
        if any(re.search(p, q) for p in strong_patterns):
            intent, confidence = candidate, 0.92
            break
        # Weak match: need 2+ weak signals (avoids false positives on common words)
        if weak_patterns:
            weak_hits = sum(1 for p in weak_patterns if re.search(p, q))
            if weak_hits >= 2:
                intent, confidence = candidate, 0.78
                break

    # Entity extraction (always run regardless of intent match)
    inst_slug, _ = normalize_institution(q)
    category = normalize_category(q)
    merchant = _extract_merchant(q)
    time_range = _extract_timerange(q)
    amount_min, amount_max = _extract_amounts(q)

    # Avoid merchant == institution name collision
    if merchant and inst_slug and merchant in inst_slug.replace("_", " "):
        merchant = None

    entities = ExtractedEntities(
        category=category,
        merchant=merchant,
        institution=inst_slug,
        account=None,
        time_range=time_range,
        amount_min=amount_min,
        amount_max=amount_max,
    )

    data_source = default_data_source(intent)

    return IntentClassificationResult(
        intent=intent,
        confidence=confidence,
        entities=entities,
        data_source=data_source,
        needs_clarification=False,
        clarifying_question=None,
        source="rule",
    )


# ── Complexity gate ────────────────────────────────────────────────────────────
# Patterns that indicate the question requires LLM reasoning, not just SQL lookup.
# These are NOT intent-classification signals — they describe *how hard* the
# question is to answer, regardless of what intent the classifier chose.

_COMPLEXITY_SIGNALS: list[tuple[str, re.Pattern[str]]] = [
    ("why",              re.compile(r"\bwhy\b", re.IGNORECASE)),
    ("trend",            re.compile(r"\btrend(?:ing|s)?\b", re.IGNORECASE)),
    ("change",           re.compile(r"\b(?:change[sd]?|chang(?:ing|ed))\b", re.IGNORECASE)),
    ("increase",         re.compile(r"\bincrease[sd]?\b", re.IGNORECASE)),
    ("decrease",         re.compile(r"\bdecrease[sd]?\b", re.IGNORECASE)),
    ("unusual",          re.compile(r"\b(?:unusual|unexpected|strange|anomal(?:y|ous)|outlier)\b", re.IGNORECASE)),
    ("high_low",         re.compile(r"\b(?:high(?:er|est)?|low(?:er|est)?)\s+(?:than\s+(?:usual|normal|average|last)|spending|charges?|fees?)\b", re.IGNORECASE)),
    ("document_detail",  re.compile(r"\b(?:statement|document|pdf|disclosure|terms|conditions|interest\s+rate)\s+(?:says?|shows?|mentions?|explains?|describes?)\b", re.IGNORECASE)),
    ("vague_this_that",  re.compile(r"\b(?:this|that)\s+(?:transaction|charge|payment|one|item|amount|purchase)\b", re.IGNORECASE)),
    ("how_am_i_doing",   re.compile(r"\bhow\s+(?:am\s+i\s+doing|is\s+my|are\s+my)\b", re.IGNORECASE)),
    ("best_worst",       re.compile(r"\b(?:best|worst)\b", re.IGNORECASE)),
    ("what_about",       re.compile(r"\bwhat\s+about\b", re.IGNORECASE)),
    ("vague_happened",   re.compile(r"\bwhat\s+(?:happened|changed|went\s+(?:up|down|wrong))\b", re.IGNORECASE)),
    ("projection",       re.compile(r"\b(?:predict|forecast|project(?:ion)?|will\s+i|should\s+i)\b", re.IGNORECASE)),
    ("vague_tell_me",    re.compile(r"\btell\s+me\s+(?:about|more|more\s+about)\b", re.IGNORECASE)),
]

# Intents that are always analytically complex enough to benefit from LLM planning.
_ALWAYS_COMPLEX_INTENTS: frozenset[ChatIntent] = frozenset({
    ChatIntent.COMPARISON,
})

# Intents that are always document-oriented (FTS/RAG primary, never simple SQL).
_DOCUMENT_INTENTS: frozenset[ChatIntent] = frozenset({
    ChatIntent.DOCUMENT_LOOKUP,
})

# Intents that can be safe SQL when filters are present.
_SQL_CAPABLE_INTENTS: frozenset[ChatIntent] = frozenset({
    ChatIntent.TRANSACTION_SEARCH,
    ChatIntent.SPENDING_SUMMARY,
    ChatIntent.BALANCE_SUMMARY,
    ChatIntent.INCOME_SUMMARY,
    ChatIntent.RECURRING_TRANSACTIONS,
    ChatIntent.FEES_SUMMARY,
    ChatIntent.ACCOUNT_SUMMARY,
})


def _detect_complexity(q: str) -> list[str]:
    """Return a list of complexity signal names that match the question."""
    return [name for name, pattern in _COMPLEXITY_SIGNALS if pattern.search(q)]


def build_route_decision(
    classification: IntentClassificationResult,
    *,
    question: str = "",
) -> RouteDecision:
    """Translate a classification result into a concrete routing decision.

    The decision is based on three inputs (in priority order):
      1. Intent type — document intents always go to DOCUMENT_SEARCH.
      2. Complexity signals — trigger NEEDS_LLM_PLANNER regardless of confidence.
      3. Rule confidence — below threshold triggers NEEDS_LLM_PLANNER.

    The returned RouteDecision drives whether the LLM is called in
    ``intent_classifier.classify()`` and which SQL/RAG path runs in
    ``chat_router.route()``.
    """
    intent = classification.intent
    ents = classification.entities
    q = question.lower() if question else ""
    complexity = _detect_complexity(q)
    rule_conf = classification.confidence

    # ── Unknown / needs clarification ────────────────────────────────────────
    if intent == ChatIntent.UNKNOWN:
        return RouteDecision(
            route_type=RouteType.CLARIFICATION,
            route_risk=RouteRisk.NEEDS_CLARIFICATION,
            intent=intent,
            entities=ents,
            reason="Intent could not be determined; clarification required.",
            complexity_signals=complexity,
            rule_confidence=rule_conf,
        )

    # ── Document-oriented intents ─────────────────────────────────────────────
    if intent in _DOCUMENT_INTENTS:
        return RouteDecision(
            route_type=RouteType.DOCUMENT_SEARCH,
            route_risk=RouteRisk.SAFE,
            intent=intent,
            entities=ents,
            reason="Document-lookup intent routes to FTS/RAG by default.",
            complexity_signals=complexity,
            rule_confidence=rule_conf,
        )

    # ── Always-complex intents (e.g. comparison) ──────────────────────────────
    if intent in _ALWAYS_COMPLEX_INTENTS:
        return RouteDecision(
            route_type=RouteType.SQL_ANALYSIS,
            route_risk=RouteRisk.NEEDS_LLM_PLANNER,
            intent=intent,
            entities=ents,
            reason=f"Intent '{intent.value}' always requires LLM analysis.",
            complexity_signals=complexity,
            rule_confidence=rule_conf,
        )

    # ── Investment / fees — inherently hybrid ─────────────────────────────────
    if intent in (ChatIntent.INVESTMENT_SUMMARY, ChatIntent.FEES_SUMMARY):
        risk = RouteRisk.NEEDS_LLM_PLANNER if complexity else RouteRisk.SAFE
        return RouteDecision(
            route_type=RouteType.HYBRID,
            route_risk=risk,
            intent=intent,
            entities=ents,
            reason="Investment/fees questions benefit from both SQL and document evidence.",
            complexity_signals=complexity,
            rule_confidence=rule_conf,
        )

    # ── Complexity signals detected ───────────────────────────────────────────
    if complexity:
        return RouteDecision(
            route_type=RouteType.SQL_ANALYSIS,
            route_risk=RouteRisk.NEEDS_LLM_PLANNER,
            intent=intent,
            entities=ents,
            reason=f"Complexity signals detected: {', '.join(complexity)}.",
            complexity_signals=complexity,
            rule_confidence=rule_conf,
        )

    # ── Low rule confidence ───────────────────────────────────────────────────
    if rule_conf < RULE_CONFIDENCE_THRESHOLD:
        return RouteDecision(
            route_type=RouteType.SQL_ANALYSIS,
            route_risk=RouteRisk.NEEDS_LLM_PLANNER,
            intent=intent,
            entities=ents,
            reason=f"Rule confidence {rule_conf:.2f} below threshold {RULE_CONFIDENCE_THRESHOLD}; LLM planner needed.",
            complexity_signals=complexity,
            rule_confidence=rule_conf,
        )

    # ── Safe simple SQL ───────────────────────────────────────────────────────
    return RouteDecision(
        route_type=RouteType.SIMPLE_SQL,
        route_risk=RouteRisk.SAFE,
        intent=intent,
        entities=ents,
        reason="High-confidence rule match with no complexity signals.",
        complexity_signals=[],
        rule_confidence=rule_conf,
    )
