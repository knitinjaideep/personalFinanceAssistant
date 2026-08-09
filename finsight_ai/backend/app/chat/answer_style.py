"""
Answer-style layer: classifies HOW to answer, independent of WHAT to answer.

After intent classification and query planning, the pipeline knows the data
path (SQL/RAG/affordability). This module adds a second dimension: given the
user's question and the routing decision, what *style* of answer should be
produced and what *shape* should the response take?

AnswerMode  — the epistemic mode the user expects
ResponseShape — the structural/presentation shape of the answer
AnswerStyleDecision — the full decision, including rendering hints
determine_answer_style() — the single entry-point called by chat_router
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.chat.query_planner import QueryPlan
    from app.domain.classification import IntentClassificationResult, RouteDecision


# ── AnswerMode ─────────────────────────────────────────────────────────────────

class AnswerMode(str, Enum):
    """The epistemic stance the user's question implies."""
    FACTUAL      = "factual"       # "How much did I spend at Amazon?" → give a number
    ANALYTICAL   = "analytical"    # "Why was my spending high?" → explain a pattern
    ADVISORY     = "advisory"      # "Can we afford a $1.3M house?" → give a recommendation
    COACHING     = "coaching"      # "How do we get ready to buy a house?" → give a plan
    COMPARISON   = "comparison"    # "Compare Chase vs Amex" → side-by-side contrast
    EXPLORATORY  = "exploratory"   # "What if we wait 12 months?" → scenario analysis
    CLARIFICATION = "clarification"  # unclear question → ask back


# ── ResponseShape ──────────────────────────────────────────────────────────────

class ResponseShape(str, Enum):
    """The structural form the answer should take in the UI."""
    ONE_LINE_ANSWER     = "one_line_answer"      # single sentence or single value
    NATURAL_ADVISORY    = "natural_advisory"     # conversational prose paragraphs
    NUMERIC_BREAKDOWN   = "numeric_breakdown"    # numbered list of amounts/metrics
    COMPARISON_TABLE    = "comparison_table"     # side-by-side table
    WHAT_IF_EXPLANATION = "what_if_explanation"  # scenario narrative with conditions
    DASHBOARD_SUMMARY   = "dashboard_summary"    # multi-metric prose + highlights
    CLARIFYING_QUESTION = "clarifying_question"  # question back to the user


# ── Decision model ─────────────────────────────────────────────────────────────

class AnswerStyleDecision(BaseModel):
    """Full answer-style decision passed downstream to answer_builder."""
    answer_mode: AnswerMode
    response_shape: ResponseShape
    reason: str = ""
    max_bullets: int = 5
    prefer_natural_language: bool = True
    allow_headings: bool = False
    allow_chart: bool = True
    confidence: float = 1.0


# ── Mode signal tables ─────────────────────────────────────────────────────────

# Strong keywords that push toward a specific mode
_ANALYTICAL_SIGNALS = (
    "why", "how come", "reason", "unusual", "explain", "tell me about",
    "what caused", "trend", "pattern", "insight", "analysis", "look at",
)
_ADVISORY_SIGNALS = (
    "can i afford", "can we afford", "should i", "should we", "is it smart",
    "is it wise", "is it a good idea", "make sense to", "recommend",
    "worth it", "afford", "feasible", "viable",
)
_COACHING_SIGNALS = (
    "how do i", "how do we", "how should i", "how should we",
    "get ready", "prepare", "steps to", "plan to", "plan for",
    "what do i need to do", "what should i do", "roadmap", "goal",
    "save for", "saving for", "build up", "get to",
)
_COMPARISON_SIGNALS = (
    "compare", "versus", " vs ", "difference between", "which is better",
    "higher", "lower", "more than", "less than", "how does", "side by side",
)
_EXPLORATORY_SIGNALS = (
    "what if", "if i wait", "if we wait", "what would happen",
    "scenario", "suppose", "hypothetical", "projection", "forecast",
    "in 12 months", "in 6 months", "in a year", "in 2 years",
    "if i saved", "if we saved",
)

# ChatIntent → preferred AnswerMode (used as base before signal overrides)
_INTENT_MODE_MAP: dict[str, AnswerMode] = {
    "transaction_search":     AnswerMode.FACTUAL,
    "spending_summary":       AnswerMode.FACTUAL,
    "income_summary":         AnswerMode.FACTUAL,
    "balance_summary":        AnswerMode.FACTUAL,
    "investment_summary":     AnswerMode.FACTUAL,
    "fees_summary":           AnswerMode.FACTUAL,
    "document_lookup":        AnswerMode.FACTUAL,
    "account_summary":        AnswerMode.FACTUAL,
    "comparison":             AnswerMode.COMPARISON,
    "recurring_transactions": AnswerMode.FACTUAL,
    "affordability":          AnswerMode.ADVISORY,
    "unknown":                AnswerMode.CLARIFICATION,
}

# AnswerMode → default ResponseShape
_MODE_DEFAULT_SHAPE: dict[AnswerMode, ResponseShape] = {
    AnswerMode.FACTUAL:        ResponseShape.ONE_LINE_ANSWER,
    AnswerMode.ANALYTICAL:     ResponseShape.DASHBOARD_SUMMARY,
    AnswerMode.ADVISORY:       ResponseShape.NATURAL_ADVISORY,
    AnswerMode.COACHING:       ResponseShape.WHAT_IF_EXPLANATION,
    AnswerMode.COMPARISON:     ResponseShape.COMPARISON_TABLE,
    AnswerMode.EXPLORATORY:    ResponseShape.WHAT_IF_EXPLANATION,
    AnswerMode.CLARIFICATION:  ResponseShape.CLARIFYING_QUESTION,
}

# RouteType → mode nudge (lower priority than question signals)
_ROUTE_MODE_NUDGE: dict[str, AnswerMode | None] = {
    "simple_sql":     None,           # pure factual, keep intent default
    "sql_analysis":   AnswerMode.ANALYTICAL,
    "document_search": None,
    "hybrid":         None,
    "affordability":  AnswerMode.ADVISORY,
    "clarification":  AnswerMode.CLARIFICATION,
    "unsupported":    AnswerMode.CLARIFICATION,
}


# ── Main function ──────────────────────────────────────────────────────────────

def determine_answer_style(
    question: str,
    intent_result: "IntentClassificationResult",
    route_decision: "RouteDecision",
    query_plan: "QueryPlan | None" = None,
) -> AnswerStyleDecision:
    """
    Determine the answer mode and response shape for a question.

    Priority order (highest wins):
      1. Question-text signals (what/if, why, compare, coach keywords)
      2. RouteType nudge (affordability → advisory)
      3. ChatIntent default mapping
      4. Fallback to FACTUAL/ONE_LINE_ANSWER

    Returns an AnswerStyleDecision with rendering hints.
    """
    q = question.lower().strip()
    intent_value = intent_result.intent.value if intent_result else "unknown"
    route_type = route_decision.route_type.value if route_decision else "simple_sql"
    confidence = intent_result.confidence if intent_result else 0.0

    # ── Step 1: start from intent default ─────────────────────────────────────
    mode = _INTENT_MODE_MAP.get(intent_value, AnswerMode.FACTUAL)
    reason = f"intent:{intent_value}"

    # ── Step 2: apply route nudge (lower priority than signals) ───────────────
    route_nudge = _ROUTE_MODE_NUDGE.get(route_type)
    if route_nudge is not None and mode == AnswerMode.FACTUAL:
        mode = route_nudge
        reason = f"route_nudge:{route_type}"

    # ── Step 3: override with question-text signals (highest priority) ─────────
    if any(sig in q for sig in _EXPLORATORY_SIGNALS):
        mode = AnswerMode.EXPLORATORY
        reason = "question_signal:exploratory"
    elif any(sig in q for sig in _COACHING_SIGNALS):
        mode = AnswerMode.COACHING
        reason = "question_signal:coaching"
    elif any(sig in q for sig in _ADVISORY_SIGNALS):
        mode = AnswerMode.ADVISORY
        reason = "question_signal:advisory"
    elif any(sig in q for sig in _COMPARISON_SIGNALS):
        mode = AnswerMode.COMPARISON
        reason = "question_signal:comparison"
    elif any(sig in q for sig in _ANALYTICAL_SIGNALS):
        mode = AnswerMode.ANALYTICAL
        reason = "question_signal:analytical"

    # ── Step 4: affordability questions always advisory or exploratory ─────────
    # (route_type is authoritative when affordability is confirmed by the planner)
    if route_type == "affordability":
        if mode not in (AnswerMode.EXPLORATORY, AnswerMode.COACHING):
            mode = AnswerMode.ADVISORY
            reason = f"route_type:affordability,prior_mode:{mode.value}"

    # ── Step 5: low confidence → clarification ────────────────────────────────
    if confidence < 0.35 and intent_value == "unknown":
        mode = AnswerMode.CLARIFICATION
        reason = f"low_confidence:{confidence:.2f}"

    # ── Step 6: derive shape from mode ────────────────────────────────────────
    shape = _derive_shape(mode, q, intent_value, route_type, query_plan)

    # ── Step 7: compute rendering hints from mode/shape ───────────────────────
    return _build_decision(mode, shape, reason, confidence)


# ── Shape derivation ──────────────────────────────────────────────────────────

def _derive_shape(
    mode: AnswerMode,
    q: str,
    intent_value: str,
    route_type: str,
    query_plan: "QueryPlan | None",
) -> ResponseShape:
    """Refine the response shape beyond the simple mode-default mapping."""
    base = _MODE_DEFAULT_SHAPE[mode]

    # FACTUAL with multiple categories → numeric breakdown is more useful
    if mode == AnswerMode.FACTUAL:
        breakdown_signals = ("breakdown", "by category", "by merchant", "by account", "each", "all my")
        if any(sig in q for sig in breakdown_signals):
            return ResponseShape.NUMERIC_BREAKDOWN

    # ANALYTICAL with comparison context → prefer comparison table
    if mode == AnswerMode.ANALYTICAL and intent_value == "comparison":
        return ResponseShape.COMPARISON_TABLE

    # COACHING with specific savings/affordability goal → what-if
    if mode == AnswerMode.COACHING and route_type == "affordability":
        return ResponseShape.WHAT_IF_EXPLANATION

    # ADVISORY affordability → natural advisory prose
    if mode == AnswerMode.ADVISORY and route_type == "affordability":
        return ResponseShape.NATURAL_ADVISORY

    return base


# ── Decision builder ──────────────────────────────────────────────────────────

def _build_decision(
    mode: AnswerMode,
    shape: ResponseShape,
    reason: str,
    confidence: float,
) -> AnswerStyleDecision:
    """Build final AnswerStyleDecision with mode-appropriate rendering hints."""

    # Rendering hint matrix
    if mode == AnswerMode.FACTUAL:
        return AnswerStyleDecision(
            answer_mode=mode,
            response_shape=shape,
            reason=reason,
            max_bullets=3,
            prefer_natural_language=False,
            allow_headings=False,
            allow_chart=True,
            confidence=confidence,
        )

    if mode == AnswerMode.ANALYTICAL:
        return AnswerStyleDecision(
            answer_mode=mode,
            response_shape=shape,
            reason=reason,
            max_bullets=6,
            prefer_natural_language=True,
            allow_headings=True,
            allow_chart=True,
            confidence=confidence,
        )

    if mode == AnswerMode.ADVISORY:
        return AnswerStyleDecision(
            answer_mode=mode,
            response_shape=shape,
            reason=reason,
            max_bullets=4,
            prefer_natural_language=True,
            allow_headings=False,
            allow_chart=False,
            confidence=confidence,
        )

    if mode == AnswerMode.COACHING:
        return AnswerStyleDecision(
            answer_mode=mode,
            response_shape=shape,
            reason=reason,
            max_bullets=6,
            prefer_natural_language=True,
            allow_headings=True,
            allow_chart=True,
            confidence=confidence,
        )

    if mode == AnswerMode.COMPARISON:
        return AnswerStyleDecision(
            answer_mode=mode,
            response_shape=shape,
            reason=reason,
            max_bullets=5,
            prefer_natural_language=False,
            allow_headings=True,
            allow_chart=True,
            confidence=confidence,
        )

    if mode == AnswerMode.EXPLORATORY:
        return AnswerStyleDecision(
            answer_mode=mode,
            response_shape=shape,
            reason=reason,
            max_bullets=5,
            prefer_natural_language=True,
            allow_headings=False,
            allow_chart=True,
            confidence=confidence,
        )

    # CLARIFICATION
    return AnswerStyleDecision(
        answer_mode=mode,
        response_shape=shape,
        reason=reason,
        max_bullets=0,
        prefer_natural_language=True,
        allow_headings=False,
        allow_chart=False,
        confidence=confidence,
    )
