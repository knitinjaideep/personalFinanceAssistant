"""
analyzer.py — Domain entry point for affordability analysis.

Orchestrates the 7-layer pipeline:
  1. scenario_parser   → AffordabilityScenario
  2. data_collector    → FinancialSnapshot
  3. math_engine       → MathResult
  4. decision_engine   → DecisionResult
  5. advisory_context  → AdvisoryContext
  6. narrative_builder → (summary, verdict_label, followups, llm_called, llm_prompt)
  7. verifier          → VerificationResult; falls back to template on hard failure

Returns a StructuredAnswer with rich debug payload in searched_filters.

Backward-compatible with the old chat/affordability.py analyze() call signature
so chat_router.py needs only a one-line import change.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.core.logger import get_logger
from app.domain.entities import KeyNumber, SupportingDetail, StructuredAnswer

from . import advisory_context as advisory_module
from . import data_collector, decision_engine, math_engine, narrative_builder
from . import scenario_parser as sp
from . import verifier as verifier_module

logger = get_logger(__name__)


def _fmt(v: Decimal | None) -> str:
    if v is None:
        return "N/A"
    return f"${v:,.0f}"


def _no_data_answer(item: str, req_id: str = "") -> StructuredAnswer:
    return StructuredAnswer(
        answer_type="prose",
        title="No balance data available",
        summary=(
            f"I couldn't find any account balance snapshots to analyze affordability for {item}. "
            "Please upload at least one bank or investment statement to get started."
        ),
        caveats=["No balance_snapshots rows found in Coral."],
        suggested_followups=["What documents have been uploaded?", "What institutions are covered?"],
        query_path="affordability",
        intent="affordability",
        confidence=0.5,
        answer_strategy="template_only",
        llm_called=False,
        verifier_passed=True,
        request_id=req_id,
    )


def _build_highlights(
    math: math_engine.MathResult,
    decision: decision_engine.DecisionResult,
) -> list[dict[str, str]]:
    highlights: list[dict[str, str]] = [
        {"label": "Verdict", "value": decision.verdict_label},
        {"label": "Liquid cash (checking + savings)", "value": _fmt(math.liquid_cash)},
        {"label": "Emergency reserve target (6 months)", "value": _fmt(math.emergency_reserve_target)},
        {"label": "Available after reserve", "value": _fmt(math.comfortable_spend_capacity)},
    ]
    if math.scenario_type == "home_purchase":
        if math.purchase_amount:
            highlights.append({"label": "Home price", "value": _fmt(math.purchase_amount)})
        if math.down_payment:
            highlights.append({"label": "Down payment (20%)", "value": _fmt(math.down_payment)})
        if math.closing_costs:
            highlights.append({"label": "Closing costs (3%)", "value": _fmt(math.closing_costs)})
        if math.cash_needed_at_close:
            highlights.append({"label": "Cash needed at close", "value": _fmt(math.cash_needed_at_close)})
        if math.cash_remaining_after_close is not None:
            highlights.append({"label": "Cash remaining after close", "value": _fmt(math.cash_remaining_after_close)})
        if math.total_monthly_housing:
            highlights.append({"label": "Est. monthly housing cost", "value": _fmt(math.total_monthly_housing)})
        if math.dti_pct:
            highlights.append({"label": "Est. DTI vs. income", "value": f"{math.dti_pct}%"})
    else:
        if math.purchase_amount:
            highlights.append({"label": f"Cost of {math.purchase_item}", "value": _fmt(math.purchase_amount)})
        if math.cash_after_purchase is not None:
            highlights.append({"label": "Cash remaining after purchase", "value": _fmt(math.cash_after_purchase)})
        if math.reserve_gap_after and math.reserve_gap_after > 0:
            highlights.append({"label": "Reserve gap after purchase", "value": _fmt(math.reserve_gap_after)})
    return highlights


def _build_sections(math: math_engine.MathResult) -> list[dict]:
    sections: list[dict] = []
    if math.liquid_account_labels:
        sections.append({
            "heading": "Liquid accounts included",
            "rows": [{"account": a} for a in math.liquid_account_labels],
        })
    if math.excluded_account_labels:
        sections.append({
            "heading": "Excluded accounts (retirement / child)",
            "rows": [{"account": a} for a in math.excluded_account_labels],
        })
    return sections


def _build_key_numbers(
    math: math_engine.MathResult,
    decision: decision_engine.DecisionResult,
) -> list[KeyNumber]:
    """Structured numbers for the collapsible 'View the math' section."""
    nums: list[KeyNumber] = [
        KeyNumber(label="Verdict", value=decision.verdict_label),
        KeyNumber(label="Liquid cash (checking + savings)", value=_fmt(math.liquid_cash)),
        KeyNumber(
            label="Emergency reserve target",
            value=_fmt(math.emergency_reserve_target),
            note="6 months of estimated spending",
        ),
        KeyNumber(label="Available after reserve", value=_fmt(math.comfortable_spend_capacity)),
    ]
    if math.scenario_type == "home_purchase":
        if math.purchase_amount:
            nums.append(KeyNumber(label="Home price", value=_fmt(math.purchase_amount)))
        if math.down_payment:
            nums.append(KeyNumber(label="Down payment (20%)", value=_fmt(math.down_payment)))
        if math.closing_costs:
            nums.append(KeyNumber(label="Closing costs (3%)", value=_fmt(math.closing_costs)))
        if math.cash_needed_at_close:
            nums.append(KeyNumber(label="Total cash needed at close", value=_fmt(math.cash_needed_at_close)))
        if math.cash_remaining_after_close is not None:
            nums.append(KeyNumber(label="Cash remaining after close", value=_fmt(math.cash_remaining_after_close)))
        if math.total_monthly_housing:
            nums.append(
                KeyNumber(
                    label="Est. monthly housing cost",
                    value=_fmt(math.total_monthly_housing),
                    note="P&I + tax + insurance + maintenance",
                )
            )
        if math.dti_pct:
            nums.append(KeyNumber(label="Est. debt-to-income ratio", value=f"{math.dti_pct}%"))
    else:
        if math.purchase_amount:
            nums.append(
                KeyNumber(label=f"Cost of {math.purchase_item}", value=_fmt(math.purchase_amount))
            )
        if math.cash_after_purchase is not None:
            nums.append(KeyNumber(label="Cash remaining after purchase", value=_fmt(math.cash_after_purchase)))
        if math.reserve_gap_after and math.reserve_gap_after > 0:
            nums.append(KeyNumber(label="Reserve gap after purchase", value=_fmt(math.reserve_gap_after)))
    return nums


def _build_supporting_details(
    math: math_engine.MathResult,
    advisory: advisory_module.AdvisoryContext,
) -> list[SupportingDetail]:
    """Explanatory paragraphs for the collapsible math section."""
    details: list[SupportingDetail] = []
    if advisory.primary_constraint:
        details.append(SupportingDetail(heading="Why this matters", body=advisory.primary_constraint))
    if advisory.what_would_make_it_work:
        body = (
            " ".join(advisory.what_would_make_it_work)
            if isinstance(advisory.what_would_make_it_work, list)
            else advisory.what_would_make_it_work
        )
        details.append(SupportingDetail(heading="What would change the answer", body=body))
    for assumption in math.assumptions[:3]:
        details.append(SupportingDetail(body=assumption))
    return details


def _build_caveats(math: math_engine.MathResult, snap: data_collector.FinancialSnapshot) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for c in math.assumptions + math.caveats + snap.data_quality_notes:
        key = c.strip().lower()[:80]
        if key not in seen:
            seen.add(key)
            result.append(c.strip())
    return result


def _build_debug_payload(
    scenario: sp.AffordabilityScenario,
    snap: data_collector.FinancialSnapshot,
    math: math_engine.MathResult,
    decision: decision_engine.DecisionResult,
    advisory: advisory_module.AdvisoryContext,
    verification: verifier_module.VerificationResult,
    llm_prompt: str | None = None,
    debug_mode: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "scenario": {
            "type": scenario.scenario_type,
            "item": scenario.purchase_item,
            "category": scenario.purchase_category,
            "amount": float(scenario.purchase_amount) if scenario.purchase_amount else None,
            "amount_source": scenario.purchase_amount_source,
            "time_horizon": scenario.time_horizon,
            "missing_inputs": scenario.missing_inputs,
            "protected_goals": scenario.protected_goals,
        },
        "financial_snapshot": {
            "liquid_cash": float(snap.liquid_cash),
            "investment_value": float(snap.investment_value),
            "retirement_value": float(snap.retirement_value),
            "monthly_spending": float(snap.monthly_spending) if snap.monthly_spending else None,
            "monthly_income": float(snap.monthly_income) if snap.monthly_income else None,
            "has_balance_data": snap.has_balance_data,
            "has_spending_data": snap.has_spending_data,
            "has_income_data": snap.has_income_data,
            "quality_notes": snap.data_quality_notes,
        },
        "math_result": {
            "scenario_type": math.scenario_type,
            "purchase_amount": float(math.purchase_amount) if math.purchase_amount else None,
            "liquid_cash": float(math.liquid_cash),
            "emergency_reserve": float(math.emergency_reserve_target),
            "comfortable_capacity": float(math.comfortable_spend_capacity),
            "cash_after_purchase": float(math.cash_after_purchase) if math.cash_after_purchase is not None else None,
            "reserve_gap_after": float(math.reserve_gap_after) if math.reserve_gap_after else None,
            "cash_needed_at_close": float(math.cash_needed_at_close) if math.cash_needed_at_close else None,
            "dti_pct": float(math.dti_pct) if math.dti_pct else None,
        },
        "decision_result": {
            "verdict_code": decision.verdict_code.value,
            "verdict_label": decision.verdict_label,
            "severity": decision.severity.value,
            "confidence": decision.confidence,
            "primary_reason": decision.primary_reason,
        },
        "advisory_context": {
            "direct_answer": advisory.direct_answer,
            "core_tension": advisory.core_tension,
            "primary_constraint": advisory.primary_constraint,
            "secondary_constraints": advisory.secondary_constraints,
            "what_is_not_the_problem": advisory.what_is_not_the_problem,
            "what_would_make_it_work": advisory.what_would_make_it_work,
            "recommended_next_step": advisory.recommended_next_step,
            "risk_level": advisory.risk_level,
        },
        "verification": {
            "passed": verification.passed,
            "repaired": verification.repaired,
            "warnings": verification.warnings,
        },
    }
    if debug_mode and llm_prompt:
        payload["narrative_prompt"] = llm_prompt
    return payload


async def analyze(
    task_type: str,
    purchase_price: float | None,
    purchase_item: str,
    purchase_category: str,
    req_id: str = "",
    question: str = "",
    # Semantic scenario context (from SemanticScenarioParser, optional)
    semantic_scenario_type: str = "",
    semantic_parser_called: bool = False,
    semantic_parser_confidence: float = 0.0,
    protected_goals: list[str] | None = None,
    secondary_goals: list[dict] | None = None,
    time_horizon: str | None = None,
    constraints: list[str] | None = None,
    user_is_asking_for: str = "",
) -> StructuredAnswer:
    """
    Run the 7-layer affordability advisory pipeline.

    Drop-in replacement for the old chat.affordability.analyze().
    """
    from app.config import settings
    debug_mode = getattr(settings, "debug_chat", False)

    _protected_goals = protected_goals or []
    _secondary_goals = secondary_goals or []
    _constraints = constraints or []

    logger.info(
        "affordability_domain.start",
        extra={
            "task_type": task_type,
            "purchase_price": purchase_price,
            "purchase_item": purchase_item,
            "purchase_category": purchase_category,
            "request_id": req_id,
            "semantic_parser_called": semantic_parser_called,
            "semantic_scenario_type": semantic_scenario_type or "none",
            "protected_goals": _protected_goals,
        },
    )

    # ── Layer 1: Parse scenario ────────────────────────────────────────────────
    scenario = sp.parse(
        question,
        purchase_price_override=purchase_price,
        purchase_item_override=purchase_item,
        purchase_category_override=purchase_category,
        task_type_override=task_type,
        protected_goals=_protected_goals,
        secondary_goals=_secondary_goals,
        user_is_asking_for=user_is_asking_for,
        time_horizon_override=time_horizon,
        constraints=_constraints,
    )

    # ── Layer 2: Collect financial data ───────────────────────────────────────
    snap = await data_collector.collect()

    if not snap.has_balance_data:
        return _no_data_answer(purchase_item or "this purchase", req_id)

    # ── Layer 3: Math ──────────────────────────────────────────────────────────
    # Handle cash_reserve_analysis as a no-purchase sub-type
    if task_type == "cash_reserve_analysis":
        math = math_engine.MathResult(
            scenario_type="cash_reserve_analysis",
            purchase_item="cash reserve",
            liquid_cash=snap.liquid_cash,
            emergency_reserve_target=snap.emergency_reserve_target,
            comfortable_spend_capacity=snap.comfortable_spend_capacity,
            monthly_income=snap.monthly_income,
            monthly_spending=snap.monthly_spending,
            monthly_surplus=snap.monthly_surplus,
            liquid_account_labels=[a.account_name for a in snap.liquid_accounts],
            excluded_account_labels=snap.excluded_account_labels,
            investment_value=snap.investment_value,
            retirement_value=snap.retirement_value,
            assumptions=[
                f"Monthly spend estimated from transaction history: ${snap.monthly_spending:,.0f}/month.",
                f"Emergency reserve: 6 months × ${snap.monthly_spending:,.0f} = ${snap.emergency_reserve_target:,.0f}.",
            ],
            caveats=["This is not financial advice."],
        )
        months_runway = float(snap.liquid_cash / max(snap.monthly_spending, Decimal("1")))
        if months_runway >= 6:
            verdict_label = "Healthy — exceeds 6-month guideline"
        elif months_runway >= 3:
            verdict_label = "Adequate — between 3–6 months"
        else:
            verdict_label = "Tight — below 3-month minimum"

        highlights = [
            {"label": "Reserve status", "value": verdict_label},
            {"label": "Liquid cash", "value": _fmt(snap.liquid_cash)},
            {"label": "Monthly spending (est.)", "value": _fmt(snap.monthly_spending)},
            {"label": "Months of runway", "value": f"{months_runway:.1f} months"},
            {"label": "6-month reserve target", "value": _fmt(snap.emergency_reserve_target)},
            {"label": "Available beyond reserve", "value": _fmt(snap.comfortable_spend_capacity)},
        ]
        return StructuredAnswer(
            answer_type="numeric",
            title="Cash reserve analysis",
            summary=(
                f"Your liquid cash ({_fmt(snap.liquid_cash)}) covers approximately "
                f"{months_runway:.1f} months at {_fmt(snap.monthly_spending)}/month. "
                f"The 6-month target is {_fmt(snap.emergency_reserve_target)}."
            ),
            highlights=highlights,
            caveats=_build_caveats(math, snap),
            suggested_followups=["How much could I afford for a vacation?", "What are my account balances?"],
            query_path="affordability",
            intent="affordability",
            confidence=0.9,
            answer_strategy="template_only",
            llm_called=False,
            verifier_passed=True,
            request_id=req_id,
        )

    math = math_engine.compute(scenario, snap)

    # ── Layer 4: Decision ──────────────────────────────────────────────────────
    decision = decision_engine.decide(math)

    # Inject semantic enrichment into math caveats / decision reason_codes
    if semantic_parser_called:
        for goal in _protected_goals:
            math.caveats.append(
                f"Your question mentions protecting '{goal}'. This analysis checks whether "
                f"the purchase preserves your financial position relative to that goal."
            )
        if time_horizon:
            math.caveats.append(f"Time horizon context: '{time_horizon}'.")
        for constraint in _constraints:
            if constraint not in math.caveats:
                math.caveats.append(f"User constraint: '{constraint}'.")

    # ── Layer 5: Advisory context ──────────────────────────────────────────────
    advisory = advisory_module.build(math, decision, scenario)

    # ── Layer 6: Narrative ─────────────────────────────────────────────────────
    summary, verdict_label_from_llm, followups, llm_called, llm_prompt = (
        await narrative_builder.build_narrative(question or purchase_item, math, decision, advisory)
    )

    # ── Layer 7: Verify ────────────────────────────────────────────────────────
    verification = verifier_module.verify(
        summary,
        verdict_label_from_llm,
        math,
        decision,
        protected_goals=_protected_goals if semantic_parser_called else None,
        user_is_asking_for=user_is_asking_for if semantic_parser_called else "",
    )

    if verification.repaired:
        logger.warning(
            "affordability_domain.verifier_repaired",
            extra={"warnings": verification.warnings, "request_id": req_id},
        )
        # Fall back to template
        summary, verdict_label_from_llm = narrative_builder.build_template(math, decision, advisory)
        llm_called = False

    # ── Assemble StructuredAnswer ──────────────────────────────────────────────
    title = (
        "Home purchase affordability"
        if task_type == "home_affordability"
        else f"Can you afford the {purchase_item}?"
    )

    caveats = _build_caveats(math, snap)
    highlights = _build_highlights(math, decision)
    sections = _build_sections(math)
    key_numbers = _build_key_numbers(math, decision)
    supporting_details = _build_supporting_details(math, advisory)
    debug_payload = _build_debug_payload(
        scenario, snap, math, decision, advisory, verification, llm_prompt, debug_mode
    )

    _DEFAULT_FOLLOWUPS = [
        "What home price would be safer?",
        "What if we wait 12 months?",
        "How much cash should we save first?",
        "What monthly payment fits our budget?",
    ]
    final_followups = followups if followups else _DEFAULT_FOLLOWUPS

    answer = StructuredAnswer(
        answer_type="advisory",
        title=title,
        # summary preserved as the legacy alias so raw_text in ChatResponse stays populated
        summary=summary,
        main_answer_text=summary,
        key_numbers=key_numbers,
        supporting_details=supporting_details,
        highlights=highlights,
        sections=sections,
        caveats=caveats,
        suggested_followups=final_followups,
        query_path="affordability",
        intent="affordability",
        confidence=decision.confidence,
        answer_strategy="hybrid_template_plus_llm" if llm_called else "template_only",
        llm_called=llm_called,
        verifier_passed=verification.passed,
        verifier_repaired=verification.repaired,
        verifier_warnings=verification.warnings,
        request_id=req_id,
        searched_filters=debug_payload,
    )

    # Stamp semantic parser metadata for debug
    if semantic_parser_called:
        answer.searched_filters["semantic_parser_called"] = True
        answer.searched_filters["semantic_scenario_type"] = semantic_scenario_type or "unknown"
        answer.searched_filters["semantic_parser_confidence"] = round(semantic_parser_confidence, 3)
        answer.searched_filters["protected_goals"] = _protected_goals
        answer.searched_filters["user_is_asking_for"] = user_is_asking_for or "unknown"

    return answer
