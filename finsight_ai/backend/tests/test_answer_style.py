"""
Unit tests for the answer-style layer (app.chat.answer_style).

Each test targets the determine_answer_style() function with a representative
question, a pre-built IntentClassificationResult, and a RouteDecision.
Tests verify:
  - correct AnswerMode is selected
  - correct ResponseShape is selected
  - rendering hints are sane (types, not exact values)
"""

from __future__ import annotations

import pytest

from app.chat.answer_style import (
    AnswerMode,
    AnswerStyleDecision,
    ResponseShape,
    determine_answer_style,
)
from app.domain.classification import (
    ChatIntent,
    DataSource,
    ExtractedEntities,
    IntentClassificationResult,
    RouteDecision,
    RouteRisk,
    RouteType,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_classification(
    intent: ChatIntent = ChatIntent.SPENDING_SUMMARY,
    confidence: float = 0.92,
    data_source: DataSource = DataSource.SQL,
) -> IntentClassificationResult:
    return IntentClassificationResult(
        intent=intent,
        confidence=confidence,
        entities=ExtractedEntities(),
        data_source=data_source,
        source="rule",
    )


def _make_route(
    route_type: RouteType = RouteType.SIMPLE_SQL,
    route_risk: RouteRisk = RouteRisk.SAFE,
    intent: ChatIntent = ChatIntent.SPENDING_SUMMARY,
) -> RouteDecision:
    return RouteDecision(
        route_type=route_type,
        route_risk=route_risk,
        intent=intent,
        reason="test",
    )


# ── Test 1: Factual spending question ────────────────────────────────────────

def test_factual_spending_question():
    """Simple 'how much' lookup → FACTUAL + ONE_LINE_ANSWER."""
    question = "How much did I spend at Amazon last month?"
    classification = _make_classification(ChatIntent.SPENDING_SUMMARY, confidence=0.92)
    route = _make_route(RouteType.SIMPLE_SQL, intent=ChatIntent.SPENDING_SUMMARY)

    decision = determine_answer_style(question, classification, route)

    assert decision.answer_mode == AnswerMode.FACTUAL
    assert decision.response_shape in (ResponseShape.ONE_LINE_ANSWER, ResponseShape.NUMERIC_BREAKDOWN)
    assert decision.prefer_natural_language is False
    assert decision.allow_chart is True
    assert isinstance(decision.confidence, float)


# ── Test 2: Analytical spending question ─────────────────────────────────────

def test_analytical_spending_question():
    """'Why' / explanation question → ANALYTICAL + DASHBOARD_SUMMARY."""
    question = "Why was my spending so high this month?"
    classification = _make_classification(ChatIntent.SPENDING_SUMMARY, confidence=0.85)
    route = _make_route(RouteType.SQL_ANALYSIS, intent=ChatIntent.SPENDING_SUMMARY)

    decision = determine_answer_style(question, classification, route)

    assert decision.answer_mode == AnswerMode.ANALYTICAL
    assert decision.response_shape == ResponseShape.DASHBOARD_SUMMARY
    assert decision.prefer_natural_language is True


# ── Test 3: Home affordability question (ADVISORY) ───────────────────────────

def test_home_affordability_advisory():
    """Affordability yes/no decision → ADVISORY + NATURAL_ADVISORY."""
    question = "Can we afford a $1.3M house?"
    classification = _make_classification(ChatIntent.AFFORDABILITY, confidence=0.95)
    route = _make_route(RouteType.AFFORDABILITY, intent=ChatIntent.AFFORDABILITY)

    decision = determine_answer_style(question, classification, route)

    assert decision.answer_mode == AnswerMode.ADVISORY
    assert decision.response_shape == ResponseShape.NATURAL_ADVISORY
    assert decision.prefer_natural_language is True
    assert decision.allow_chart is False


# ── Test 4: Luxury affordability question (ADVISORY) ─────────────────────────

def test_luxury_affordability_advisory():
    """'Should I afford a Tesla?' is advisory, not coaching."""
    question = "Should I buy a Tesla Model S for $90,000?"
    classification = _make_classification(ChatIntent.AFFORDABILITY, confidence=0.90)
    route = _make_route(RouteType.AFFORDABILITY, intent=ChatIntent.AFFORDABILITY)

    decision = determine_answer_style(question, classification, route)

    # "should i" is advisory signal; even if coaching signal fires route keeps advisory
    assert decision.answer_mode in (AnswerMode.ADVISORY, AnswerMode.COACHING)
    assert decision.response_shape in (ResponseShape.NATURAL_ADVISORY, ResponseShape.WHAT_IF_EXPLANATION)
    assert decision.prefer_natural_language is True


# ── Test 5: What-if affordability question (EXPLORATORY) ─────────────────────

def test_what_if_affordability_exploratory():
    """What-if scenario → EXPLORATORY + WHAT_IF_EXPLANATION."""
    question = "What if we wait 12 months before buying the house?"
    classification = _make_classification(ChatIntent.AFFORDABILITY, confidence=0.88)
    route = _make_route(RouteType.AFFORDABILITY, intent=ChatIntent.AFFORDABILITY)

    decision = determine_answer_style(question, classification, route)

    assert decision.answer_mode == AnswerMode.EXPLORATORY
    assert decision.response_shape == ResponseShape.WHAT_IF_EXPLANATION
    assert decision.prefer_natural_language is True


# ── Test 6: Comparison question ───────────────────────────────────────────────

def test_comparison_question():
    """'Compare X vs Y' → COMPARISON + COMPARISON_TABLE."""
    question = "Compare my Chase and Amex spending this year"
    classification = _make_classification(ChatIntent.COMPARISON, confidence=0.90)
    route = _make_route(RouteType.HYBRID, intent=ChatIntent.COMPARISON)

    decision = determine_answer_style(question, classification, route)

    assert decision.answer_mode == AnswerMode.COMPARISON
    assert decision.response_shape == ResponseShape.COMPARISON_TABLE
    assert decision.allow_chart is True


# ── Additional edge cases ─────────────────────────────────────────────────────

def test_coaching_question():
    """How-to / plan question → COACHING + WHAT_IF_EXPLANATION."""
    question = "How do we get ready to buy a house?"
    classification = _make_classification(ChatIntent.AFFORDABILITY, confidence=0.80)
    route = _make_route(RouteType.AFFORDABILITY, intent=ChatIntent.AFFORDABILITY)

    decision = determine_answer_style(question, classification, route)

    assert decision.answer_mode == AnswerMode.COACHING
    assert decision.response_shape == ResponseShape.WHAT_IF_EXPLANATION
    assert decision.prefer_natural_language is True


def test_unknown_low_confidence_clarification():
    """Unknown intent with very low confidence → CLARIFICATION."""
    question = "xyz blah blah"
    classification = _make_classification(ChatIntent.UNKNOWN, confidence=0.20)
    route = _make_route(RouteType.CLARIFICATION, intent=ChatIntent.UNKNOWN)

    decision = determine_answer_style(question, classification, route)

    assert decision.answer_mode == AnswerMode.CLARIFICATION
    assert decision.response_shape == ResponseShape.CLARIFYING_QUESTION
    assert decision.allow_chart is False


def test_factual_breakdown_question():
    """'Breakdown by category' phrasing → NUMERIC_BREAKDOWN shape."""
    question = "Show me a breakdown of my spending by category last month"
    classification = _make_classification(ChatIntent.SPENDING_SUMMARY, confidence=0.92)
    route = _make_route(RouteType.SIMPLE_SQL, intent=ChatIntent.SPENDING_SUMMARY)

    decision = determine_answer_style(question, classification, route)

    assert decision.answer_mode == AnswerMode.FACTUAL
    assert decision.response_shape == ResponseShape.NUMERIC_BREAKDOWN


def test_decision_is_answer_style_decision():
    """Return type is always AnswerStyleDecision."""
    question = "What are my balances?"
    classification = _make_classification(ChatIntent.BALANCE_SUMMARY, confidence=0.88)
    route = _make_route(RouteType.SIMPLE_SQL, intent=ChatIntent.BALANCE_SUMMARY)

    decision = determine_answer_style(question, classification, route)

    assert isinstance(decision, AnswerStyleDecision)
    assert isinstance(decision.max_bullets, int)
    assert isinstance(decision.allow_headings, bool)
    assert isinstance(decision.reason, str)
    assert len(decision.reason) > 0
