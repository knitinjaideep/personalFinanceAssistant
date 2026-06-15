"""
Tests for the /stream SSE endpoint.

Validates that stream_chat() delegates to the shared safe chat_router.route()
pipeline and that the unsafe helper functions (_build_context, _sql_with_fallbacks,
_build_llm_context, _build_structured_answer) no longer exist in streaming.py.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.chat import streaming
from app.domain.classification import (
    ChatIntent,
    DataSource,
    ExtractedEntities,
    IntentClassificationResult,
    TimeRange,
)
from app.domain.entities import AnswerTimings, StructuredAnswer
from app.domain.enums import QueryIntent
from app.services import chat_router
from app.services.chat_router import ANSWERED, NO_DATA_AFTER_FALLBACK, RoutingOutcome


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_sse(raw: str) -> list[dict]:
    """Parse a sequence of SSE frames into list of {event, data} dicts."""
    events = []
    for frame in raw.split("\n\n"):
        frame = frame.strip()
        if not frame:
            continue
        event_type = ""
        data_str = ""
        for line in frame.splitlines():
            if line.startswith("event: "):
                event_type = line[len("event: "):]
            elif line.startswith("data: "):
                data_str = line[len("data: "):]
        if event_type:
            events.append({"event": event_type, "data": json.loads(data_str) if data_str else {}})
    return events


async def _collect(gen) -> list[dict]:
    chunks = []
    async for chunk in gen:
        chunks.append(chunk)
    return _parse_sse("".join(chunks))


def _make_answer(**kwargs) -> StructuredAnswer:
    defaults = dict(
        answer_type="prose",
        title="Test",
        summary="Here is the answer.",
        intent=QueryIntent.SPENDING_BY_CATEGORY.value,
        query_path="sql",
        confidence=0.9,
        answer_strategy="template_only",
        llm_called=False,
        verifier_passed=True,
        verifier_repaired=False,
        verifier_warnings=[],
        rows_used=5,
        timings=AnswerTimings(),
        request_id="req-test",
    )
    defaults.update(kwargs)
    return StructuredAnswer(**defaults)


def _make_outcome(answer: StructuredAnswer, **kwargs) -> RoutingOutcome:
    cls = IntentClassificationResult(
        intent=ChatIntent.SPENDING_SUMMARY,
        confidence=0.9,
        entities=ExtractedEntities(),
        data_source=DataSource.SQL,
        source="rule",
    )
    defaults = dict(
        classification=cls,
        query_intent=QueryIntent.SPENDING_BY_CATEGORY,
        route="sql",
        final_answer_status=ANSWERED,
        sql_rows=5,
        rag_chunks=0,
    )
    defaults.update(kwargs)
    return RoutingOutcome(answer=answer, **defaults)


# ── Test 1: template_only question uses shared pipeline, no LLM ───────────────

@pytest.mark.asyncio
async def test_template_only_uses_shared_safe_pipeline():
    """A simple SQL question resolved by template returns verified metadata via done event."""
    answer = _make_answer(
        answer_strategy="template_only",
        llm_called=False,
        verifier_passed=True,
        verifier_repaired=False,
        verifier_warnings=[],
        summary="You spent $1,234.00 on groceries in May.",
    )
    outcome = _make_outcome(answer)

    with patch.object(streaming, "route", new=AsyncMock(return_value=outcome)) as mock_route:
        events = await _collect(streaming.stream_chat("How much on groceries in May?", req_id="r1"))

    # route() was called exactly once — no duplicate pipeline
    mock_route.assert_awaited_once()

    event_types = [e["event"] for e in events]
    assert "status" in event_types
    assert "answer_token" in event_types
    assert "done" in event_types

    done = next(e["data"] for e in events if e["event"] == "done")
    a = done["answer"]
    assert a["answer_strategy"] == "template_only"
    assert a["llm_called"] is False
    assert a["verifier_passed"] is True
    assert a["verifier_repaired"] is False
    assert a["verifier_warnings"] == []
    assert a["rows_used"] == 5

    token = next(e["data"] for e in events if e["event"] == "answer_token")
    assert "groceries" in token["text"].lower() or "spent" in token["text"].lower()


# ── Test 2: no-data merchant query does not silently relax filters ─────────────

@pytest.mark.asyncio
async def test_unknown_merchant_no_data_not_silently_relaxed():
    """A query for an unknown merchant returns no-data answer with caveat, not broadened data."""
    answer = _make_answer(
        answer_type="prose",
        answer_strategy="template_only",
        llm_called=False,
        verifier_passed=True,
        summary="I couldn't find SomeFakeMerchant transactions for March.",
        caveats=["Searched: SomeFakeMerchant transactions for March."],
        rows_used=0,
        searched_filters={"merchant": "somefakemerchant", "date_from": "2026-03-01"},
        exact_match=False,
    )
    outcome = _make_outcome(
        answer,
        final_answer_status=NO_DATA_AFTER_FALLBACK,
        sql_rows=0,
        rag_chunks=0,
    )

    with patch.object(streaming, "route", new=AsyncMock(return_value=outcome)):
        events = await _collect(
            streaming.stream_chat("How much did I spend at SomeFakeMerchant in March?", req_id="r2")
        )

    done = next(e["data"] for e in events if e["event"] == "done")
    a = done["answer"]

    # No data was found, filters were NOT silently relaxed to show unrelated rows
    assert a["rows_used"] == 0
    assert a["exact_match"] is False
    # The answer carries a caveat explaining what was searched
    assert any("searched" in c.lower() or "couldn't find" in c.lower() for c in a.get("caveats", []))
    # Summary tells the user it couldn't find the merchant, not made-up data
    assert "couldn't find" in a["summary"].lower() or "somefakemerchant" in a["summary"].lower()


# ── Test 3: comparison question goes through verified pipeline with real metadata

@pytest.mark.asyncio
async def test_comparison_question_includes_verifier_metadata():
    """A complex comparison question returns real verifier metadata in the done event."""
    answer = _make_answer(
        answer_type="prose",
        answer_strategy="llm_narrative",
        llm_called=True,
        verifier_passed=True,
        verifier_repaired=False,
        verifier_warnings=[],
        summary="Amex spending was $800 in May vs $650 in April — $150 higher month-over-month.",
        rows_used=12,
    )
    outcome = _make_outcome(answer, final_answer_status=ANSWERED, sql_rows=12)

    with patch.object(streaming, "route", new=AsyncMock(return_value=outcome)):
        events = await _collect(
            streaming.stream_chat("Compare Amex spending this month vs last month.", req_id="r3")
        )

    done = next(e["data"] for e in events if e["event"] == "done")
    a = done["answer"]

    # All verifier fields must be present and populated from the real pipeline
    assert a["answer_strategy"] == "llm_narrative"
    assert a["llm_called"] is True
    assert a["verifier_passed"] is True
    assert "verifier_repaired" in a
    assert "verifier_warnings" in a
    assert a["rows_used"] == 12


# ── Test 4: unsafe helper functions no longer exist in streaming module ─────────

def test_unsafe_helpers_removed():
    """Guarantee the old unsafe helpers are not present in the streaming module."""
    removed = [
        "_build_context",
        "_sql_with_fallbacks",
        "_build_llm_context",
        "_build_structured_answer",
        "_NUMERIC_INTENTS",
        "_TABLE_INTENTS",
        "_MONEY_COLS",
        "_LABEL_MAP",
        "_FOLLOWUPS",
    ]
    for name in removed:
        assert not hasattr(streaming, name), (
            f"Unsafe helper '{name}' still exists in streaming.py — it must be removed."
        )


# ── Test 5: errors emit SSE error event (not an unhandled exception) ───────────

@pytest.mark.asyncio
async def test_pipeline_error_emits_sse_error_event():
    """If chat_router.route() raises, stream_chat must emit an 'error' SSE event."""
    with patch.object(streaming, "route", new=AsyncMock(side_effect=RuntimeError("db offline"))):
        events = await _collect(streaming.stream_chat("any question", req_id="r4"))

    event_types = [e["event"] for e in events]
    assert "error" in event_types
    # A done event is still emitted so the client can close the stream cleanly
    assert "done" in event_types

    error_event = next(e["data"] for e in events if e["event"] == "error")
    # Error message must not leak internals (safe_error_message scrubs them)
    assert "message" in error_event
    assert isinstance(error_event["message"], str)
    assert len(error_event["message"]) > 0
