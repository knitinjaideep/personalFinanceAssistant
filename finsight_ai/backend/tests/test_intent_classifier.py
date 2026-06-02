"""Unit tests for the intent classifier: parsing, validation, retry, fallback."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.domain.classification import (
    ChatIntent,
    DataSource,
    IntentClassificationResult,
)
from app.services import intent_classifier


def _llm_json(payload: dict) -> str:
    return json.dumps(payload)


GROCERIES = {
    "intent": "spending_summary",
    "confidence": 0.94,
    "entities": {
        "category": "groceries", "merchant": None, "institution": None,
        "account": None, "compare_to": None,
        "time_range": {"type": "relative", "value": "last_month",
                       "start_date": None, "end_date": None},
    },
    "data_source": "sql",
    "needs_clarification": False,
    "clarifying_question": None,
}


@pytest.mark.asyncio
async def test_valid_groceries_classification():
    with patch.object(intent_classifier.llm, "generate",
                      new=AsyncMock(return_value=_llm_json(GROCERIES))):
        result = await intent_classifier.classify("How much did I spend on groceries last month?")
    assert result.intent == ChatIntent.SPENDING_SUMMARY
    assert result.data_source == DataSource.SQL
    assert result.entities.category == "groceries"
    assert result.entities.time_range.value == "last_month"
    assert result.source == "llm"


@pytest.mark.asyncio
async def test_json_wrapped_in_code_fence_is_parsed():
    fenced = "```json\n" + _llm_json(GROCERIES) + "\n```"
    with patch.object(intent_classifier.llm, "generate",
                      new=AsyncMock(return_value=fenced)):
        result = await intent_classifier.classify("groceries last month")
    assert result.intent == ChatIntent.SPENDING_SUMMARY


@pytest.mark.asyncio
async def test_prose_around_json_is_recovered():
    noisy = "Sure! Here is the classification:\n" + _llm_json(GROCERIES) + "\nHope that helps."
    with patch.object(intent_classifier.llm, "generate",
                      new=AsyncMock(return_value=noisy)):
        result = await intent_classifier.classify("groceries")
    assert result.intent == ChatIntent.SPENDING_SUMMARY


@pytest.mark.asyncio
async def test_invalid_json_retries_then_rule_fallback():
    # Both LLM attempts return garbage → falls back to the rule classifier.
    gen = AsyncMock(side_effect=["not json", "still not json"])
    with patch.object(intent_classifier.llm, "generate", new=gen):
        result = await intent_classifier.classify("What fees did Morgan Stanley charge me?")
    assert gen.await_count == 2  # retried once
    # Rule fallback should still recover the fees intent.
    assert result.intent == ChatIntent.FEES_SUMMARY
    assert result.source == "rule_fallback"


@pytest.mark.asyncio
async def test_total_garbage_and_unmatchable_yields_unknown():
    gen = AsyncMock(side_effect=["xxx", "yyy"])
    with patch.object(intent_classifier.llm, "generate", new=gen):
        result = await intent_classifier.classify("asdfghjkl qwerty")
    assert result.intent == ChatIntent.UNKNOWN
    assert result.confidence == 0.0
    assert result.source == "invalid"


@pytest.mark.asyncio
async def test_unknown_data_source_backfilled_from_intent():
    payload = dict(GROCERIES, data_source="unknown")
    with patch.object(intent_classifier.llm, "generate",
                      new=AsyncMock(return_value=_llm_json(payload))):
        result = await intent_classifier.classify("groceries last month")
    # spending_summary defaults to SQL.
    assert result.data_source == DataSource.SQL


def test_schema_clamps_confidence_and_coerces_enums():
    r = IntentClassificationResult.model_validate({
        "intent": "not_a_real_intent",
        "confidence": 5.0,
        "data_source": "weird",
    })
    assert r.intent == ChatIntent.UNKNOWN
    assert r.confidence == 1.0  # clamped
    assert r.data_source == DataSource.UNKNOWN
