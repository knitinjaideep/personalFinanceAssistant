"""
narrative_builder.py — Builds the final natural-language answer for affordability questions.

Rules:
  1. Start with a direct answer.
  2. Explain the main constraint in plain English.
  3. Use only the 2–4 most important numbers.
  4. End with one practical next step.
  5. Default to natural paragraphs — no bullets unless explicitly requested.
  6. No headings unless necessary.
  7. Do not start with "Based on your data".
  8. Do not say "Verdict:".
  9. Do not sound like a report.
  10. The LLM narrator receives AdvisoryContext + MathResult; it must not recalculate.
  11. Caveats come from Python, not the LLM.
  12. The LLM is a narrator, not an analyst.
  13. If the verdict is negative, be direct but not discouraging.
  14. Mention tradeoffs, not just facts.
  15. If the household is financially strong but the specific purchase is risky, say that clearly.
  16. Never recommend draining emergency reserves.

The LLM is called with a tight system prompt + JSON payload.
On failure or validation error the deterministic template is used as fallback.
"""
from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any

from app.core.logger import get_logger

from .advisory_context import AdvisoryContext
from .decision_engine import DecisionResult, VerdictCode
from .math_engine import MathResult
from .scenario_parser import AffordabilityScenario

logger = get_logger(__name__)


# ── System prompt ──────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are the answer narrator for Coral, a local-first personal finance app.
You receive pre-computed math, a deterministic verdict, advisory framing, and the user's question.
Your only job is to narrate — all numbers and verdicts were computed by Python; you must not alter them.

VOICE: Write like a calm, knowledgeable friend giving advice over coffee — direct, honest, never clinical.

STRUCTURE:
  - First sentence: direct answer. Start with "Yes", "No", "Not right now", "Probably not", or a short
    clause that answers the question. Do NOT start with "It depends" unless the verdict is NEEDS_MORE_INFO.
  - Second sentence: explain the primary constraint in plain English using 1–2 key numbers from math_amounts.
  - Optional second paragraph (1–2 sentences): supporting context — what is NOT the problem, or what
    would change the answer. Mention tradeoffs, not just facts.
  - Final sentence: the recommended_next_step from AdvisoryContext verbatim or lightly paraphrased.
  - Total: 3–5 sentences, under 130 words.

FORBIDDEN PHRASES — never use these, not even paraphrased:
  "Verdict:"
  "Based on your data"
  "Based on the analysis"
  "Here are the key factors"
  "In conclusion"
  "It depends" (as the first sentence, unless verdict is needs_more_info)
  "I estimate", "I calculate", "I computed", "my estimate"

FORMAT:
  - No bullet points (unless response_shape is "numeric_breakdown").
  - No headings, no bold labels, no "Key points:" sections.
  - Numbers: use only amounts from math_amounts. Use at most 4 numbers in the entire summary.
  - If the verdict is NOT_AFFORDABLE or STRETCH, be direct but constructive — name the constraint clearly,
    acknowledge what IS working (if anything), and give one concrete path forward.
  - If the household is financially strong but this specific purchase is risky, say that explicitly.
  - Never recommend draining emergency reserves. Never suggest retirement accounts as a funding source.

HARD RULES (violations cause your output to be discarded):
  1. Do NOT change the verdict_code or verdict_label.
  2. Do NOT invent dollar amounts not present in math_amounts.
  3. Do NOT add assumptions not listed in math_assumptions.
  4. Do NOT make any conclusion listed in forbidden_conclusions.
  5. Do NOT recommend loans, credit card debt, or financing (unless user asked).
  6. Do NOT mention retirement accounts as a funding option unless specifically asked.
  7. All suggested followups must come ONLY from decision_followups.
  8. Do NOT use bullet points unless response_shape is "numeric_breakdown".
  9. Never claim affordability when the verdict is NOT_AFFORDABLE.

OUTPUT — return ONLY this JSON (no markdown fences, no prose outside it):
{
  "summary": "<3-5 sentences, direct and natural, no bullets, no headings>",
  "verdict_label": "<must exactly match DecisionResult.verdict_label>",
  "suggested_followups": ["<followup 1>", "<followup 2>"]
}
"""


def _build_llm_payload(
    question: str,
    math: MathResult,
    decision: DecisionResult,
    advisory: AdvisoryContext,
) -> str:
    """Serialize the pipeline output into a compact JSON prompt for the LLM."""
    # Only send the amounts the LLM is allowed to reference
    amounts: dict[str, str] = {}
    for field_name, label in [
        ("purchase_amount", "purchase_price"),
        ("liquid_cash", "liquid_cash"),
        ("emergency_reserve_target", "emergency_reserve"),
        ("comfortable_spend_capacity", "comfortable_spend_capacity"),
        ("cash_after_purchase", "cash_after_purchase"),
        ("reserve_gap_after", "reserve_gap_after"),
        ("cash_needed_at_close", "cash_needed_at_close"),
        ("cash_remaining_after_close", "cash_remaining_after_close"),
        ("comfortable_cash_gap", "comfortable_cash_gap"),
        ("total_monthly_housing", "total_monthly_housing"),
        ("dti_pct", "dti_pct"),
        ("monthly_income", "monthly_income"),
        ("monthly_spending", "monthly_spending"),
        ("monthly_surplus", "monthly_surplus"),
        ("max_affordable_home_price", "max_affordable_home_price"),
        ("months_to_save_for_purchase", "months_to_save"),
    ]:
        val = getattr(math, field_name, None)
        if val is not None and val > 0:
            if field_name in ("dti_pct", "months_to_save_for_purchase"):
                amounts[label] = f"{val}"
            else:
                amounts[label] = f"${val:,.0f}"

    payload: dict[str, Any] = {
        "question": question,
        "verdict": {
            "code": decision.verdict_code.value,
            "label": decision.verdict_label,
            "severity": decision.severity.value,
        },
        "advisory": {
            "direct_answer": advisory.direct_answer,
            "core_tension": advisory.core_tension,
            "primary_constraint": advisory.primary_constraint,
            "secondary_constraints": advisory.secondary_constraints,
            "what_is_not_the_problem": advisory.what_is_not_the_problem,
            "what_would_make_it_work": advisory.what_would_make_it_work,
            "recommended_next_step": advisory.recommended_next_step,
            "emotional_frame": advisory.emotional_frame,
            "response_shape": advisory.response_shape,
        },
        "math_amounts": amounts,
        "math_assumptions": math.assumptions[:4],   # trim to avoid context overflow
        "allowed_conclusions": decision.allowed_conclusions,
        "forbidden_conclusions": decision.forbidden_conclusions,
        "decision_followups": decision.recommended_followups,
    }
    if advisory.protected_goals:
        payload["protected_goals"] = advisory.protected_goals
    if advisory.time_horizon:
        payload["time_horizon"] = advisory.time_horizon
    if advisory.user_is_asking_for:
        payload["user_is_asking_for"] = advisory.user_is_asking_for

    return json.dumps(payload, ensure_ascii=False)


async def _call_llm(
    question: str,
    math: MathResult,
    decision: DecisionResult,
    advisory: AdvisoryContext,
) -> dict | None:
    """Call the local LLM to produce a readable JSON answer. Returns None on failure."""
    try:
        from app.config import settings
        from app.services import llm as llm_service

        user_prompt = _build_llm_payload(question, math, decision, advisory)
        raw = await llm_service.generate(
            user_prompt,
            model=settings.ollama.model,
            system=_SYSTEM_PROMPT,
            temperature=0.1,
            format_json=True,
            num_ctx=getattr(settings.ollama, "num_ctx", 4096),
        )

        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-z]*\n?", "", text)
            text = re.sub(r"```$", "", text.strip())
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]

        return json.loads(text)
    except Exception as exc:
        logger.warning("narrative_builder.llm_failed", extra={"error": str(exc)})
        return None


# ── Deterministic template fallback ───────────────────────────────────────────

def _template_summary(math: MathResult, decision: DecisionResult, advisory: AdvisoryContext) -> str:
    """Build a clean prose summary without the LLM."""
    lines = [advisory.direct_answer]
    if advisory.core_tension and advisory.core_tension != advisory.direct_answer:
        lines.append(advisory.core_tension)
    if decision.secondary_reasons:
        lines.append(decision.secondary_reasons[0])
    if advisory.recommended_next_step:
        lines.append(advisory.recommended_next_step)
    return " ".join(lines)


def build_template(
    math: MathResult,
    decision: DecisionResult,
    advisory: AdvisoryContext,
) -> tuple[str, str]:
    """Return (summary, verdict_label) without calling the LLM."""
    return _template_summary(math, decision, advisory), decision.verdict_label


# ── LLM narrative prompt exposure (for debug payload) ─────────────────────────

def build_llm_prompt(
    question: str,
    math: MathResult,
    decision: DecisionResult,
    advisory: AdvisoryContext,
) -> str:
    """Return the JSON string that would be sent to the LLM. For debug use."""
    return _build_llm_payload(question, math, decision, advisory)


# ── Main entry point ──────────────────────────────────────────────────────────

async def build_narrative(
    question: str,
    math: MathResult,
    decision: DecisionResult,
    advisory: AdvisoryContext,
) -> tuple[str, str, list[str], bool, str | None]:
    """
    Build the final natural narrative.

    Returns:
        (summary, verdict_label, suggested_followups, llm_called, llm_prompt_if_debug)
    """
    llm_prompt = _build_llm_payload(question, math, decision, advisory)

    llm_out = await _call_llm(question, math, decision, advisory)

    allowed_followups = set(decision.recommended_followups)

    if llm_out is not None:
        summary = llm_out.get("summary") or advisory.direct_answer
        verdict_label_from_llm = llm_out.get("verdict_label", "")
        followups = [
            fp for fp in (llm_out.get("suggested_followups") or [])
            if fp in allowed_followups
        ]
        if not followups:
            followups = decision.recommended_followups[:3]
        return summary, verdict_label_from_llm, followups, True, llm_prompt

    # Fallback to template
    summary, verdict_label = build_template(math, decision, advisory)
    return summary, verdict_label, decision.recommended_followups[:3], False, llm_prompt
