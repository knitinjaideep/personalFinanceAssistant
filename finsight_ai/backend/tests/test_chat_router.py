"""
Unit tests for the chat router: intent → route mapping, the SQL fallback chain,
and the guarantee that we never instantly return a bare "no data" answer.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.domain.classification import (
    ChatIntent,
    DataSource,
    ExtractedEntities,
    IntentClassificationResult,
    TimeRange,
)
from app.domain.enums import QueryIntent
from app.services import chat_router
from app.services.chat_router import (
    ANSWERED,
    CLARIFICATION_NEEDED,
    NO_DATA_AFTER_FALLBACK,
    PARTIAL,
)
from app.services.intent_mapping import rule_classify


# ── Rule-based classifier covers the required intent cases ────────────────────

@pytest.mark.parametrize(
    "question,intent,data_source",
    [
        ("How much did I spend on groceries last month?", ChatIntent.SPENDING_SUMMARY, DataSource.SQL),
        ("What fees did Morgan Stanley charge me?", ChatIntent.FEES_SUMMARY, DataSource.HYBRID),
        ("Show me Chase transactions from January", ChatIntent.TRANSACTION_SEARCH, DataSource.SQL),
        ("What does my Amex statement say about interest?", ChatIntent.DOCUMENT_LOOKUP, DataSource.RAG),
        ("Compare my Chase spending in March vs April", ChatIntent.COMPARISON, DataSource.SQL),
        ("What is my current investment allocation?", ChatIntent.INVESTMENT_SUMMARY, DataSource.HYBRID),
    ],
)
def test_rule_classify_intents(question, intent, data_source):
    result = rule_classify(question)
    assert result.intent == intent
    assert result.data_source == data_source


def test_rule_classify_typo_morgan_stanly_feez():
    result = rule_classify("morgan stanly feez")
    assert result.intent == ChatIntent.FEES_SUMMARY
    assert result.entities.institution == "morgan_stanley"


def test_rule_classify_vague_is_unknown():
    result = rule_classify("show me my money")
    assert result.intent == ChatIntent.UNKNOWN


def test_rule_classify_normalizes_entities():
    result = rule_classify("how much did I spend on grocery at chase")
    assert result.entities.category == "groceries"
    assert result.entities.institution == "chase"


# ── Context building ──────────────────────────────────────────────────────────

def test_build_context_normalizes_and_resolves_time():
    from datetime import date

    cls = IntentClassificationResult(
        intent=ChatIntent.SPENDING_SUMMARY,
        confidence=0.9,
        entities=ExtractedEntities(
            category="grocery",
            institution="amex",
            time_range=TimeRange(type="relative", value="last_month"),
        ),
        data_source=DataSource.SQL,
    )
    ctx = chat_router._build_context(cls, today=date(2026, 6, 2))
    assert ctx.category == "groceries"
    assert ctx.institution == "amex"
    assert ctx.date_from == date(2026, 5, 1)
    assert ctx.date_to == date(2026, 5, 31)


# ── Routing + fallback chain ──────────────────────────────────────────────────

def _cls(intent=ChatIntent.SPENDING_SUMMARY, data_source=DataSource.SQL, **ent):
    return IntentClassificationResult(
        intent=intent, confidence=0.9,
        entities=ExtractedEntities(**ent),
        data_source=data_source, source="llm",
    )


def _sql_rows(rows):
    return {"rows": rows, "columns": [], "summary": "ok", "sql_used": "SELECT 1"}


@pytest.mark.asyncio
async def test_exact_sql_hit_is_answered():
    cls = _cls(category="groceries", time_range=TimeRange(type="relative", value="last_month"))
    with (
        patch.object(chat_router, "classify", new=AsyncMock(return_value=cls)),
        patch.object(chat_router.sql_query, "execute_for_intent",
                     new=AsyncMock(return_value=_sql_rows([{"category": "groceries", "total_spent": 100}]))),
        patch.object(chat_router, "build_answer", new=AsyncMock(side_effect=_fake_build_answer)),
    ):
        outcome = await chat_router.route("How much on groceries last month?")
    assert outcome.final_answer_status == ANSWERED
    assert outcome.query_intent == QueryIntent.SPENDING_BY_CATEGORY
    assert "sql_exact" in outcome.fallback_steps
    assert outcome.sql_rows == 1


@pytest.mark.asyncio
async def test_relaxed_sql_fallback_marks_partial():
    cls = _cls(category="groceries", time_range=TimeRange(type="relative", value="last_month"))

    # First call (exact w/ category+date) empty, then relaxed (no cat/merch) hits.
    calls = {"n": 0}

    async def fake_sql(intent, q, ctx):
        calls["n"] += 1
        if ctx.category is None and ctx.merchant is None:
            return _sql_rows([{"category": "restaurants", "total_spent": 50}])
        return _sql_rows([])

    with (
        patch.object(chat_router, "classify", new=AsyncMock(return_value=cls)),
        patch.object(chat_router.sql_query, "execute_for_intent", new=fake_sql),
        patch.object(chat_router, "build_answer", new=AsyncMock(side_effect=_fake_build_answer)),
    ):
        outcome = await chat_router.route("groceries last month")
    assert outcome.final_answer_status == PARTIAL
    assert "sql_relaxed_filters" in outcome.fallback_steps
    # A relaxation note should have been appended.
    assert any("broadened" in c.lower() for c in outcome.answer.caveats)


@pytest.mark.asyncio
async def test_no_data_falls_back_to_helpful_not_blank():
    """The critical guarantee: empty SQL + empty RAG → helpful answer, never bare 'no data'."""
    cls = _cls(category="groceries", time_range=TimeRange(type="relative", value="last_month"))
    with (
        patch.object(chat_router, "classify", new=AsyncMock(return_value=cls)),
        patch.object(chat_router.sql_query, "execute_for_intent",
                     new=AsyncMock(return_value=_sql_rows([]))),
        patch.object(chat_router.text_search, "search", new=AsyncMock(return_value=[])),
        patch.object(chat_router.vector_search, "search", new=AsyncMock(return_value=[])),
        patch.object(chat_router.availability, "available_categories",
                     new=AsyncMock(return_value=["restaurants", "gas"])),
        patch.object(chat_router.availability, "available_institutions",
                     new=AsyncMock(return_value=["Chase", "Amex"])),
        patch.object(chat_router.availability, "transaction_date_bounds",
                     new=AsyncMock(return_value=("2026-04-01", "2026-05-31"))),
    ):
        outcome = await chat_router.route("groceries last month")

    assert outcome.final_answer_status == NO_DATA_AFTER_FALLBACK
    # Not a blank/placeholder answer — it explains what was searched + shows alternatives.
    summary = outcome.answer.summary.lower()
    assert "couldn't find" in summary
    assert "dining" in summary or "restaurants" in summary.lower()  # available categories surfaced
    assert outcome.answer.summary != "No data found."
    assert "helpful_fallback" in outcome.fallback_steps


@pytest.mark.asyncio
async def test_classifier_clarification_short_circuits():
    cls = IntentClassificationResult(
        intent=ChatIntent.UNKNOWN, confidence=0.1,
        entities=ExtractedEntities(),
        data_source=DataSource.UNKNOWN,
        needs_clarification=True,
        clarifying_question="Which account do you mean?",
        source="llm",
    )
    with patch.object(chat_router, "classify", new=AsyncMock(return_value=cls)):
        outcome = await chat_router.route("uhh")
    assert outcome.final_answer_status == CLARIFICATION_NEEDED
    assert "Which account" in outcome.answer.summary


@pytest.mark.asyncio
async def test_rag_route_with_chunks_is_partial():
    cls = _cls(intent=ChatIntent.DOCUMENT_LOOKUP, data_source=DataSource.RAG, institution="amex")
    with (
        patch.object(chat_router, "classify", new=AsyncMock(return_value=cls)),
        patch.object(chat_router.text_search, "search",
                     new=AsyncMock(return_value=[{"content": "interest terms"}])),
        patch.object(chat_router, "build_answer", new=AsyncMock(side_effect=_fake_build_answer)),
    ):
        outcome = await chat_router.route("What does my Amex statement say about interest?")
    assert outcome.final_answer_status == PARTIAL
    assert outcome.rag_chunks == 1


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _fake_build_answer(question, intent, path, confidence, ctx, *, req_id=""):
    from app.domain.entities import StructuredAnswer
    return StructuredAnswer(
        answer_type="prose", title="t", summary="generated answer",
        intent=intent.value, query_path=path.value, confidence=confidence,
    )
