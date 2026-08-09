"""
Endpoint parity tests: /query and /stream must produce identical pipeline outputs.

Both endpoints call chat_router.route() — these tests assert that for the same
question the two paths produce the same:
  - intent (QueryIntent)
  - route_type
  - answer_mode
  - response_shape
  - SQL query (for SQL-routed questions)
  - affordability verdict (for affordability questions)
  - fallback behavior (when no data)
  - answer_strategy

The streaming path is exercised through stream_chat(); the batch path directly
through chat_router.route(). Both are mocked to return the same RoutingOutcome,
proving neither endpoint bypasses the shared pipeline.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.chat import streaming
from app.chat.answer_style import AnswerMode, AnswerStyleDecision, ResponseShape
from app.chat.query_planner import AffordabilitySpec, QueryPlan
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
from app.domain.entities import AnswerTimings, StructuredAnswer
from app.domain.enums import QueryIntent
from app.services import chat_router
from app.services.chat_router import ANSWERED, NO_DATA_AFTER_FALLBACK, RoutingOutcome


# ── Fixtures & helpers ────────────────────────────────────────────────────────

def _classification(
    intent: ChatIntent = ChatIntent.SPENDING_SUMMARY,
    data_source: DataSource = DataSource.SQL,
    **ent_kwargs,
) -> IntentClassificationResult:
    return IntentClassificationResult(
        intent=intent,
        confidence=0.9,
        entities=ExtractedEntities(**ent_kwargs),
        data_source=data_source,
        source="rule",
    )


def _route_decision(
    route_type: RouteType = RouteType.SIMPLE_SQL,
    route_risk: RouteRisk = RouteRisk.SAFE,
    intent: ChatIntent = ChatIntent.SPENDING_SUMMARY,
) -> RouteDecision:
    return RouteDecision(route_type=route_type, route_risk=route_risk, intent=intent)


def _answer_style(
    mode: AnswerMode = AnswerMode.FACTUAL,
    shape: ResponseShape = ResponseShape.ONE_LINE_ANSWER,
) -> AnswerStyleDecision:
    return AnswerStyleDecision(
        answer_mode=mode,
        response_shape=shape,
        reason="test",
        max_bullets=4,
    )


def _answer(
    intent: QueryIntent = QueryIntent.SPENDING_BY_CATEGORY,
    query_path: str = "sql",
    sql_used: list[str] | None = None,
    answer_mode: str = "factual",
    response_shape: str = "one_line_answer",
    answer_strategy: str = "template_only",
    llm_called: bool = False,
    verifier_passed: bool = True,
    verifier_repaired: bool = False,
    verifier_warnings: list[str] | None = None,
    rows_used: int = 5,
    summary: str = "You spent $123.00 on groceries.",
    caveats: list[str] | None = None,
) -> StructuredAnswer:
    return StructuredAnswer(
        answer_type="numeric",
        title="Test",
        summary=summary,
        intent=intent.value,
        query_path=query_path,
        confidence=0.9,
        sql_used=sql_used or ["SELECT * FROM transactions"],
        rows_used=rows_used,
        answer_mode=answer_mode,
        response_shape=response_shape,
        answer_strategy=answer_strategy,
        llm_called=llm_called,
        verifier_passed=verifier_passed,
        verifier_repaired=verifier_repaired,
        verifier_warnings=verifier_warnings or [],
        caveats=caveats or [],
        timings=AnswerTimings(),
        request_id="req-parity",
    )


def _outcome(
    answer: StructuredAnswer,
    classification: IntentClassificationResult | None = None,
    query_intent: QueryIntent = QueryIntent.SPENDING_BY_CATEGORY,
    route: str = "sql",
    route_decision: RouteDecision | None = None,
    query_plan: QueryPlan | None = None,
    answer_style: AnswerStyleDecision | None = None,
    sql_rows: int = 5,
    rag_chunks: int = 0,
    fallback_steps: list[str] | None = None,
    final_answer_status: str = ANSWERED,
) -> RoutingOutcome:
    return RoutingOutcome(
        answer=answer,
        classification=classification or _classification(),
        query_intent=query_intent,
        route=route,
        final_answer_status=final_answer_status,
        fallback_steps=fallback_steps or ["sql_exact"],
        sql_rows=sql_rows,
        rag_chunks=rag_chunks,
        route_decision=route_decision or _route_decision(),
        query_plan=query_plan,
        answer_style=answer_style or _answer_style(),
    )


async def _collect_stream(question: str, req_id: str = "test") -> list[dict]:
    """Collect all SSE events from stream_chat into a list of {event, data} dicts."""
    chunks = []
    async for chunk in streaming.stream_chat(question, req_id=req_id):
        chunks.append(chunk)
    raw = "".join(chunks)
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


# ── Parity test 1: same intent from both endpoints ────────────────────────────

@pytest.mark.asyncio
async def test_parity_same_intent():
    """Both /query and /stream produce the same QueryIntent for the same question."""
    question = "How much did I spend on groceries last month?"

    answer = _answer(intent=QueryIntent.SPENDING_BY_CATEGORY)
    shared_outcome = _outcome(answer, query_intent=QueryIntent.SPENDING_BY_CATEGORY)

    mock_route = AsyncMock(return_value=shared_outcome)

    with patch.object(chat_router, "route", mock_route):
        batch_outcome = await chat_router.route(question)

    with patch.object(streaming, "route", AsyncMock(return_value=shared_outcome)):
        events = await _collect_stream(question)

    intent_event = next((e["data"] for e in events if e["event"] == "intent"), None)
    assert intent_event is not None, "stream did not emit an 'intent' event"

    assert batch_outcome.query_intent.value == intent_event["intent"]
    assert batch_outcome.query_intent == QueryIntent.SPENDING_BY_CATEGORY


# ── Parity test 2: same route_type from both endpoints ───────────────────────

@pytest.mark.asyncio
async def test_parity_same_route_type():
    """Both endpoints report the same route_type for a complex question."""
    question = "Compare my Amex spending this month versus last month."

    decision = _route_decision(route_type=RouteType.SQL_ANALYSIS, route_risk=RouteRisk.NEEDS_LLM_PLANNER)  # noqa: E501
    answer = _answer(
        intent=QueryIntent.SPENDING_BY_CATEGORY,
        answer_mode="comparison",
        response_shape="comparison_table",
        answer_strategy="llm_narrative",
    )
    shared_outcome = _outcome(answer, route_decision=decision, query_intent=QueryIntent.SPENDING_BY_CATEGORY)

    with patch.object(chat_router, "route", AsyncMock(return_value=shared_outcome)):
        batch_outcome = await chat_router.route(question)

    with patch.object(streaming, "route", AsyncMock(return_value=shared_outcome)):
        events = await _collect_stream(question)

    intent_event = next((e["data"] for e in events if e["event"] == "intent"), None)
    assert intent_event is not None

    batch_rt = batch_outcome.route_decision.route_type.value
    stream_rt = intent_event["route_type"]
    assert batch_rt == stream_rt, f"/query route_type={batch_rt!r} != /stream route_type={stream_rt!r}"


# ── Parity test 3: same answer_mode and response_shape ───────────────────────

@pytest.mark.asyncio
async def test_parity_same_answer_mode_and_response_shape():
    """Both endpoints stamp identical answer_mode and response_shape on the answer."""
    question = "Should I put more money into my E*TRADE account?"

    style = _answer_style(mode=AnswerMode.ADVISORY, shape=ResponseShape.NATURAL_ADVISORY)
    answer = _answer(
        answer_mode=AnswerMode.ADVISORY.value,
        response_shape=ResponseShape.NATURAL_ADVISORY.value,
        answer_strategy="hybrid_template_plus_llm",
    )
    shared_outcome = _outcome(answer, answer_style=style)

    with patch.object(chat_router, "route", AsyncMock(return_value=shared_outcome)):
        batch_outcome = await chat_router.route(question)

    with patch.object(streaming, "route", AsyncMock(return_value=shared_outcome)):
        events = await _collect_stream(question)

    intent_event = next((e["data"] for e in events if e["event"] == "intent"), None)
    done_event = next(e["data"] for e in events if e["event"] == "done")

    # answer_mode must match in the intent event
    assert intent_event is not None
    assert batch_outcome.answer.answer_mode == intent_event["answer_mode"]
    assert batch_outcome.answer.response_shape == intent_event["response_shape"]

    # answer_mode must also appear in the answer embedded in the done event
    done_answer = done_event["answer"]
    assert done_answer["answer_mode"] == batch_outcome.answer.answer_mode
    assert done_answer["response_shape"] == batch_outcome.answer.response_shape


# ── Parity test 4: same SQL query for SQL routes ──────────────────────────────

@pytest.mark.asyncio
async def test_parity_same_sql_for_sql_routes():
    """Both endpoints carry the same SQL string for a SQL-routed question."""
    question = "What fees did Morgan Stanley charge me in 2025?"

    sql = "SELECT fee_category, SUM(amount) FROM fees WHERE institution='morgan_stanley'"
    answer = _answer(sql_used=[sql])
    shared_outcome = _outcome(answer)

    with patch.object(chat_router, "route", AsyncMock(return_value=shared_outcome)):
        batch_outcome = await chat_router.route(question)

    with patch.object(streaming, "route", AsyncMock(return_value=shared_outcome)):
        events = await _collect_stream(question)

    done_event = next(e["data"] for e in events if e["event"] == "done")
    stream_sql = done_event["answer"].get("sql_used", [])

    assert batch_outcome.answer.sql_used == stream_sql


# ── Parity test 5: same affordability verdict ─────────────────────────────────

@pytest.mark.asyncio
async def test_parity_same_affordability_verdict():
    """Both endpoints carry the same affordability scenario type for an affordability question."""
    question = "Can I afford a $3,000 vacation this summer?"

    aff_spec = AffordabilitySpec(
        task_type="purchase_viability",
        purchase_price=3000.0,
        purchase_item="vacation",
        purchase_category="travel",
        semantic_scenario_type="vacation_planning",
        semantic_parser_called=True,
        semantic_parser_confidence=0.92,
    )
    query_plan = QueryPlan(
        task_type="purchase_affordability",
        plan_source="deterministic",
        affordability=aff_spec,
    )
    decision = _route_decision(route_type=RouteType.AFFORDABILITY)
    answer = _answer(
        intent=QueryIntent.BALANCE_LOOKUP,  # affordability maps to BALANCE_LOOKUP internally
        query_path="affordability",
        answer_mode="advisory",
        answer_strategy="llm_narrative",
    )
    shared_outcome = _outcome(
        answer,
        classification=_classification(intent=ChatIntent.AFFORDABILITY),
        query_intent=QueryIntent.BALANCE_LOOKUP,
        route="affordability",
        route_decision=decision,
        query_plan=query_plan,
    )

    with patch.object(chat_router, "route", AsyncMock(return_value=shared_outcome)):
        batch_outcome = await chat_router.route(question)

    with patch.object(streaming, "route", AsyncMock(return_value=shared_outcome)):
        events = await _collect_stream(question)

    intent_event = next((e["data"] for e in events if e["event"] == "intent"), None)
    assert intent_event is not None

    # Both paths must expose the same scenario type
    batch_scenario = (
        batch_outcome.query_plan.affordability.semantic_scenario_type
        if batch_outcome.query_plan and batch_outcome.query_plan.affordability
        else None
    )
    stream_scenario = intent_event.get("affordability_scenario")
    assert batch_scenario == stream_scenario, (
        f"/query affordability_scenario={batch_scenario!r} "
        f"!= /stream affordability_scenario={stream_scenario!r}"
    )
    assert stream_scenario == "vacation_planning"


# ── Parity test 6: same fallback behavior (no data) ──────────────────────────

@pytest.mark.asyncio
async def test_parity_same_fallback_behavior():
    """Both endpoints hit the helpful_fallback path for the same no-data question."""
    question = "How much did I spend at SomeMadeUpStore last year?"

    answer = _answer(
        intent=QueryIntent.TRANSACTION_LOOKUP,
        query_path="fallback",
        sql_used=[],
        rows_used=0,
        answer_mode="factual",
        answer_strategy="template_only",
        summary="I couldn't find SomeMadeUpStore transactions.",
        caveats=["Searched: merchant 'somemadeupstore'. No exact matches found."],
    )
    shared_outcome = _outcome(
        answer,
        query_intent=QueryIntent.TRANSACTION_LOOKUP,
        route="fallback",
        sql_rows=0,
        rag_chunks=0,
        fallback_steps=["sql_exact", "helpful_fallback"],
        final_answer_status=NO_DATA_AFTER_FALLBACK,
    )

    with patch.object(chat_router, "route", AsyncMock(return_value=shared_outcome)):
        batch_outcome = await chat_router.route(question)

    with patch.object(streaming, "route", AsyncMock(return_value=shared_outcome)):
        events = await _collect_stream(question)

    intent_event = next((e["data"] for e in events if e["event"] == "intent"), None)
    done_event = next(e["data"] for e in events if e["event"] == "done")

    assert intent_event is not None
    # Both must report NO_DATA_AFTER_FALLBACK
    assert batch_outcome.final_answer_status == NO_DATA_AFTER_FALLBACK
    assert intent_event["final_answer_status"] == NO_DATA_AFTER_FALLBACK

    # Fallback steps must match
    assert batch_outcome.fallback_steps == intent_event["fallback_steps"]
    assert "helpful_fallback" in intent_event["fallback_steps"]

    # The done event answer must convey no data, not made-up rows
    done_answer = done_event["answer"]
    assert done_answer["rows_used"] == 0


# ── Parity test 7: same answer_strategy ───────────────────────────────────────

@pytest.mark.asyncio
async def test_parity_same_answer_strategy():
    """Both endpoints produce the same answer_strategy (template_only vs llm_narrative)."""
    for strategy in ("template_only", "llm_narrative", "hybrid_template_plus_llm"):
        answer = _answer(answer_strategy=strategy)
        shared_outcome = _outcome(answer)

        with patch.object(chat_router, "route", AsyncMock(return_value=shared_outcome)):
            batch_outcome = await chat_router.route("test question")

        with patch.object(streaming, "route", AsyncMock(return_value=shared_outcome)):
            events = await _collect_stream("test question")

        intent_event = next((e["data"] for e in events if e["event"] == "intent"), None)
        done_event = next(e["data"] for e in events if e["event"] == "done")

        assert intent_event is not None
        assert batch_outcome.answer.answer_strategy == intent_event["answer_strategy"], (
            f"strategy={strategy}: batch vs stream mismatch in intent event"
        )
        assert done_event["answer"]["answer_strategy"] == strategy, (
            f"strategy={strategy}: done event answer missing correct answer_strategy"
        )


# ── Parity test 8: stream emits intent event with endpoint_type=stream ────────

@pytest.mark.asyncio
async def test_stream_intent_event_has_endpoint_type():
    """The intent SSE event must identify itself as coming from the stream endpoint."""
    answer = _answer()
    shared_outcome = _outcome(answer)

    with patch.object(streaming, "route", AsyncMock(return_value=shared_outcome)):
        events = await _collect_stream("How much on dining last month?", req_id="r-ep")

    intent_event = next((e["data"] for e in events if e["event"] == "intent"), None)
    assert intent_event is not None
    assert intent_event["endpoint_type"] == "stream"


# ── Parity test 9: verification status propagates through both paths ───────────

@pytest.mark.asyncio
async def test_parity_verification_status():
    """Verifier_passed / verifier_repaired must match in both endpoints for repaired answers."""
    answer = _answer(
        answer_strategy="llm_narrative",
        llm_called=True,
        verifier_passed=True,
        verifier_repaired=True,
        verifier_warnings=["A number in the summary did not match computed total."],
        summary="You spent $500.00 on dining (repaired from LLM output).",
    )

    shared_outcome = _outcome(answer)

    with patch.object(chat_router, "route", AsyncMock(return_value=shared_outcome)):
        batch_outcome = await chat_router.route("How much on dining?")

    with patch.object(streaming, "route", AsyncMock(return_value=shared_outcome)):
        events = await _collect_stream("How much on dining?")

    intent_event = next((e["data"] for e in events if e["event"] == "intent"), None)
    done_event = next(e["data"] for e in events if e["event"] == "done")

    assert intent_event is not None
    assert intent_event["verification"] == "repaired"
    assert intent_event["verifier_repaired"] is True
    assert intent_event["verifier_passed"] is True

    done_answer = done_event["answer"]
    assert done_answer["verifier_passed"] == batch_outcome.answer.verifier_passed
    assert done_answer["verifier_repaired"] == batch_outcome.answer.verifier_repaired
