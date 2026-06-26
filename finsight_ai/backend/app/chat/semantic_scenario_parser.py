"""
SemanticScenarioParser — Gemma/LLM-powered scenario extractor for complex affordability questions.

Architecture contract:
- Only called when should_use_semantic_scenario_parser() returns True.
- Extracts MEANING only: scenario type, goals, purchase info, protected goals, constraints.
- NEVER calculates financial numbers.
- NEVER decides affordability verdicts.
- NEVER invents account balances, cash flow, or reserve amounts.
- Python (ScenarioMathResult + DecisionResult) remains responsible for all math and verdicts.
- On any failure (JSON parse error, Pydantic validation, LLM timeout), returns a safe deterministic
  fallback with scenario_type="unknown" and confidence=0.0.

Trigger rules (in should_use_semantic_scenario_parser):
- Only called for ChatIntent.AFFORDABILITY / RouteType.AFFORDABILITY.
- Not called for simple, single-goal, explicit-price questions like "Can we afford a $25,000 Birkin?"
  unless the question also contains multi-goal, safety, impact, or vague scenario language.
- Triggered by semantic complexity signals: hurt, affect, impact, still, next year, before/after,
  safe, comfortable, stretch, risk, house savings, down payment, emergency fund, preserve, protect,
  multiple goals, "should we", "are we okay", "financially okay", "what if".
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.core.logger import get_logger

logger = get_logger(__name__)


# ── Semantic complexity signals ───────────────────────────────────────────────

_SEMANTIC_TRIGGERS: frozenset[str] = frozenset({
    "hurt",
    "affect",
    "impact",
    "still",
    "next year",
    "before",
    "after",
    "safe",
    "comfortable",
    "stretch",
    "risk",
    "house savings",
    "house fund",
    "home savings",
    "down payment",
    "emergency fund",
    "preserve",
    "protect",
    "and still",
    "should we",
    "are we okay",
    "financially okay",
    "what if",
    "both",
    "also",
    "at the same time",
    "and also",
    "while still",
    "without hurting",
    "without affecting",
    "fellowship ends",
    "fellowship",
    "end of the year",
    "by end of",
    "before the",
})

# Words that indicate multi-goal complexity even in "simple" questions
_MULTI_GOAL_SIGNALS: frozenset[str] = frozenset({
    "and",
    "also",
    "both",
    "while",
    "still",
    "same time",
    "without",
    "but still",
    "and still",
    "as well as",
})

# Simple explicit affordability patterns — these are NOT complex
# (single goal, explicit price, no impact/protection language)
# Only skip Gemma if the question has an explicit dollar amount AND none of the triggers above.
_SIMPLE_EXPLICIT_RE = re.compile(
    r"can (i|we|we afford|i afford|you afford)\s+(a\s+)?\$[\d,]+(?:\.\d+)?(?:\s*(?:k|thousand|million))?\b",
    re.IGNORECASE,
)
_HAS_DOLLAR_RE = re.compile(r"\$[\d,]+", re.IGNORECASE)


def should_use_semantic_scenario_parser(
    question: str,
    route_type: str,
    intent: str,
) -> bool:
    """Determine whether the SemanticScenarioParser should be invoked.

    Returns True only for affordability questions with semantic complexity:
    multi-goal, impact analysis, safety checks, time-horizon constraints,
    or vague/scenario language.

    Does NOT call Gemma for simple explicit single-goal affordability questions
    like "Can we afford a $25,000 Birkin?" unless they also contain complexity signals.
    """
    from app.domain.classification import ChatIntent, RouteType

    # Only applies to affordability routing
    if route_type not in ("affordability",) and intent not in ("affordability",):
        return False

    q = question.lower()

    # Check for any semantic trigger word/phrase
    has_trigger = any(trigger in q for trigger in _SEMANTIC_TRIGGERS)

    if not has_trigger:
        return False

    # Even if triggers exist, if the question is a simple "Can we afford $X [item]?"
    # with no multi-goal signals, skip Gemma (deterministic planner handles it fine).
    # Exception: if the trigger is NOT just "before"/"after" appearing in a neutral context.
    # The key distinguishers are impact words (hurt, affect, still, safe, stretch, etc.)
    _STRONG_TRIGGERS = frozenset({
        "hurt", "affect", "impact", "still", "safe", "stretch", "risk",
        "house savings", "house fund", "home savings", "emergency fund",
        "preserve", "protect", "should we", "are we okay", "financially okay",
        "what if", "while still", "without hurting", "without affecting",
        "fellowship", "and still",
    })
    has_strong_trigger = any(trigger in q for trigger in _STRONG_TRIGGERS)

    return has_strong_trigger


# ── Pydantic schema ───────────────────────────────────────────────────────────

class GoalSpec(BaseModel):
    """A financial goal extracted from the user's question."""
    goal_type: Literal[
        "home_purchase",
        "luxury_purchase",
        "car_purchase",
        "vacation",
        "emergency_fund",
        "savings_goal",
        "debt_payoff",
        "unknown",
    ] = "unknown"
    label: str = ""
    amount: Optional[Decimal] = None
    amount_source: Optional[str] = None   # "explicit_user_amount" | "default_assumption_needed" | "unknown"
    time_horizon: Optional[str] = None


class SemanticScenarioResult(BaseModel):
    """
    Structured semantic understanding of a complex affordability question.
    Produced by LLM (Gemma). Never contains financial calculations.
    Python (ScenarioMathResult + DecisionResult) performs all math/verdicts.
    """
    scenario_type: Literal[
        "simple_purchase_affordability",
        "home_affordability",
        "multi_goal_affordability",
        "purchase_impact_on_goal",
        "cash_reserve_safety",
        "unknown",
    ] = "unknown"

    primary_goal: Optional[GoalSpec] = None
    secondary_goals: list[GoalSpec] = Field(default_factory=list)

    purchase_item: Optional[str] = None
    purchase_category: Optional[str] = None
    purchase_amount: Optional[Decimal] = None
    purchase_amount_source: Literal[
        "explicit_user_amount",
        "default_assumption_needed",
        "unknown",
    ] = "unknown"

    time_horizon: Optional[str] = None
    protected_goals: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)

    user_is_asking_for: Literal[
        "can_afford",
        "impact_analysis",
        "safety_check",
        "comparison",
        "clarification",
        "unknown",
    ] = "unknown"

    clarification_needed: bool = False
    clarifying_question: Optional[str] = None

    assumptions_requested_by_user: list[str] = Field(default_factory=list)
    forbidden_assumptions: list[str] = Field(default_factory=list)

    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = ""

    # Internal: not populated by LLM, set by parser
    parser_called: bool = False
    parser_model: str = ""
    parser_error: Optional[str] = None


# ── Safe fallback ─────────────────────────────────────────────────────────────

def _fallback_result(reason: str = "", error: str = "") -> SemanticScenarioResult:
    return SemanticScenarioResult(
        scenario_type="unknown",
        confidence=0.0,
        reason=reason or "SemanticScenarioParser returned safe fallback",
        parser_called=True,
        parser_error=error or None,
    )


# ── System prompt ─────────────────────────────────────────────────────────────

_SEMANTIC_SYSTEM_PROMPT = """\
You are a semantic scenario parser for a personal finance app called Coral.
Your ONLY job is to extract the meaning of the user's question into a structured JSON object.

CRITICAL RULES (violations will cause your output to be discarded):
1. Do NOT calculate any financial values (balances, cash flow, income, savings rate, etc.)
2. Do NOT decide whether the user can afford anything — that is Python's job.
3. Do NOT invent balances, income, spending amounts, account data, or reserve targets.
4. Do NOT add financial advice, caveats, or recommendations.
5. If the user gives an explicit dollar amount (e.g. "$75,000 car"), extract it exactly.
6. If the user mentions an item but gives no amount (e.g. "Birkin bag"), set purchase_amount to null
   and purchase_amount_source to "default_assumption_needed".
7. If the user asks about a future goal (e.g. "buy a house next year"), extract it as a
   protected_goals entry and/or secondary_goal.
8. For time constraints like "before fellowship ends", extract that as time_horizon.
9. Return ONLY the JSON object — no markdown fences, no prose outside it.

OUTPUT JSON SCHEMA (return exactly this shape):
{
  "scenario_type": "<simple_purchase_affordability|home_affordability|multi_goal_affordability|purchase_impact_on_goal|cash_reserve_safety|unknown>",
  "primary_goal": {
    "goal_type": "<home_purchase|luxury_purchase|car_purchase|vacation|emergency_fund|savings_goal|debt_payoff|unknown>",
    "label": "<short label e.g. 'Birkin bag' or 'vacation to Japan'>",
    "amount": <number or null>,
    "amount_source": "<explicit_user_amount|default_assumption_needed|unknown>",
    "time_horizon": "<string or null>"
  },
  "secondary_goals": [
    {
      "goal_type": "<...>",
      "label": "<string>",
      "amount": <number or null>,
      "amount_source": "<...>",
      "time_horizon": "<string or null>"
    }
  ],
  "purchase_item": "<string or null — the specific item being purchased>",
  "purchase_category": "<luxury_purchase|car_purchase|vacation|home_purchase|savings_goal|unknown>",
  "purchase_amount": <number or null>,
  "purchase_amount_source": "<explicit_user_amount|default_assumption_needed|unknown>",
  "time_horizon": "<string or null — overall time context e.g. 'next year', 'before fellowship ends'>",
  "protected_goals": ["<goal that must not be harmed e.g. 'house savings', 'emergency fund'>"],
  "constraints": ["<constraint from user e.g. 'keep emergency fund intact', 'before fellowship ends'>"],
  "user_is_asking_for": "<can_afford|impact_analysis|safety_check|comparison|clarification|unknown>",
  "clarification_needed": <bool>,
  "clarifying_question": "<string or null>",
  "assumptions_requested_by_user": ["<assumption user wants you to make>"],
  "forbidden_assumptions": ["<something user explicitly does NOT want assumed>"],
  "confidence": <float 0.0-1.0>,
  "reason": "<one sentence explaining your extraction>"
}

SCENARIO TYPE GUIDE:
- simple_purchase_affordability: single purchase, no multi-goal complexity
- home_affordability: user wants to buy a home
- multi_goal_affordability: user is balancing multiple financial goals
- purchase_impact_on_goal: user asks if purchase X will hurt goal Y (e.g. "Would a Birkin hurt house savings?")
- cash_reserve_safety: user asks about safety of emergency fund / reserves
- unknown: cannot determine

USER_IS_ASKING_FOR GUIDE:
- can_afford: "Can I/we afford X?"
- impact_analysis: "Would X hurt/affect Y?"
- safety_check: "Is X safe?" "Would it stretch us?"
- comparison: "Should we do X or Y?"
- clarification: question is too vague to extract scenario

EXAMPLES:
Q: "Would buying a Birkin hurt our house savings?"
→ scenario_type: "purchase_impact_on_goal"
→ purchase_item: "Birkin bag", purchase_category: "luxury_purchase", purchase_amount: null, purchase_amount_source: "default_assumption_needed"
→ protected_goals: ["house savings"]
→ secondary_goals: [{"goal_type": "home_purchase", "label": "house savings"}]
→ user_is_asking_for: "impact_analysis"

Q: "Can we still buy a house next year if we buy a $75,000 car?"
→ scenario_type: "multi_goal_affordability"
→ purchase_item: "car", purchase_category: "car_purchase", purchase_amount: 75000, purchase_amount_source: "explicit_user_amount"
→ protected_goals: ["home purchase next year"]
→ secondary_goals: [{"goal_type": "home_purchase", "label": "home purchase", "time_horizon": "next year"}]
→ time_horizon: "next year"
→ user_is_asking_for: "impact_analysis"

Q: "Can we afford a $10,000 vacation before fellowship ends?"
→ scenario_type: "simple_purchase_affordability"
→ purchase_item: "vacation", purchase_category: "vacation", purchase_amount: 10000, purchase_amount_source: "explicit_user_amount"
→ time_horizon: "before fellowship ends"
→ constraints: ["before fellowship ends"]
→ user_is_asking_for: "can_afford"

Q: "Can we afford this and still keep our emergency fund?"
→ scenario_type: "cash_reserve_safety"
→ purchase_item: null (unknown — needs clarification)
→ protected_goals: ["emergency fund"]
→ clarification_needed: true
→ clarifying_question: "What are you considering buying? I need the item or amount to check if it's safe while keeping your emergency fund."
→ user_is_asking_for: "safety_check"

Q: "Is a $25,000 bag safe or would it stretch us?"
→ scenario_type: "simple_purchase_affordability"
→ purchase_item: "bag", purchase_category: "luxury_purchase", purchase_amount: 25000, purchase_amount_source: "explicit_user_amount"
→ user_is_asking_for: "safety_check"
→ constraints: ["should not stretch finances"]
"""


# ── Parser core ───────────────────────────────────────────────────────────────

def _parse_goal_spec(raw: Any) -> GoalSpec | None:
    if not isinstance(raw, dict):
        return None
    try:
        amount = raw.get("amount")
        if amount is not None:
            amount = Decimal(str(amount))
        return GoalSpec(
            goal_type=raw.get("goal_type", "unknown"),
            label=str(raw.get("label", "")),
            amount=amount,
            amount_source=raw.get("amount_source"),
            time_horizon=raw.get("time_horizon"),
        )
    except Exception:
        return None


def _parse_goal_list(raw: Any) -> list[GoalSpec]:
    if not isinstance(raw, list):
        return []
    goals: list[GoalSpec] = []
    for item in raw:
        g = _parse_goal_spec(item)
        if g is not None:
            goals.append(g)
    return goals


def _parse_llm_response(data: dict[str, Any]) -> SemanticScenarioResult:
    """Parse and validate LLM JSON into SemanticScenarioResult. May raise."""
    purchase_amount = data.get("purchase_amount")
    if purchase_amount is not None:
        purchase_amount = Decimal(str(purchase_amount))

    return SemanticScenarioResult(
        scenario_type=data.get("scenario_type", "unknown"),
        primary_goal=_parse_goal_spec(data.get("primary_goal")),
        secondary_goals=_parse_goal_list(data.get("secondary_goals", [])),
        purchase_item=data.get("purchase_item"),
        purchase_category=data.get("purchase_category"),
        purchase_amount=purchase_amount,
        purchase_amount_source=data.get("purchase_amount_source", "unknown"),
        time_horizon=data.get("time_horizon"),
        protected_goals=[str(g) for g in (data.get("protected_goals") or [])],
        constraints=[str(c) for c in (data.get("constraints") or [])],
        user_is_asking_for=data.get("user_is_asking_for", "unknown"),
        clarification_needed=bool(data.get("clarification_needed", False)),
        clarifying_question=data.get("clarifying_question"),
        assumptions_requested_by_user=[str(a) for a in (data.get("assumptions_requested_by_user") or [])],
        forbidden_assumptions=[str(f) for f in (data.get("forbidden_assumptions") or [])],
        confidence=float(data.get("confidence", 0.0)),
        reason=str(data.get("reason", "")),
        parser_called=True,
    )


async def parse_semantic_scenario(
    question: str,
    route_type: str,
    intent: str,
    conversation_context: str = "",
) -> SemanticScenarioResult:
    """
    Parse the semantic scenario of a complex affordability question using the LLM.

    This is only called when should_use_semantic_scenario_parser() returned True.
    Returns a SemanticScenarioResult (never raises).
    On any failure returns a safe fallback with confidence=0.0.

    Args:
        question: The raw user question.
        route_type: Current route type string (e.g. "affordability").
        intent: Current intent string (e.g. "affordability").
        conversation_context: Optional brief context from conversation history.
    """
    from app.config import settings
    from app.services import llm as llm_service

    model = settings.ollama.classification_model

    user_prompt = f'Question: "{question}"'
    if conversation_context:
        user_prompt = f'Context: {conversation_context}\n{user_prompt}'

    logger.info(
        "semantic_scenario_parser.start",
        extra={
            "question_preview": question[:100],
            "model": model,
        },
    )

    raw_text: str = ""
    for attempt in range(2):
        try:
            raw_text = await llm_service.generate(
                user_prompt,
                model=model,
                system=_SEMANTIC_SYSTEM_PROMPT,
                temperature=0.0,
                format_json=True,
                num_ctx=getattr(settings.ollama, "classification_num_ctx", 4096),
            )

            # Strip markdown fences if present
            text = raw_text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```[a-z]*\n?", "", text)
                text = re.sub(r"```$", "", text.strip())
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end > start:
                text = text[start : end + 1]

            data: dict[str, Any] = json.loads(text)
            result = _parse_llm_response(data)
            result.parser_model = model

            logger.info(
                "semantic_scenario_parser.success",
                extra={
                    "scenario_type": result.scenario_type,
                    "purchase_item": result.purchase_item,
                    "purchase_amount": str(result.purchase_amount) if result.purchase_amount else None,
                    "purchase_amount_source": result.purchase_amount_source,
                    "protected_goals": result.protected_goals,
                    "user_is_asking_for": result.user_is_asking_for,
                    "confidence": result.confidence,
                    "attempt": attempt + 1,
                },
            )
            return result

        except json.JSONDecodeError as exc:
            logger.warning(
                "semantic_scenario_parser.json_parse_failed",
                extra={"attempt": attempt + 1, "error": str(exc), "raw": raw_text[:300]},
            )
        except Exception as exc:
            logger.warning(
                "semantic_scenario_parser.failed",
                extra={"attempt": attempt + 1, "error": str(exc)},
            )
            if attempt == 0:
                continue
            return _fallback_result(error=str(exc))

    return _fallback_result(
        reason="LLM returned unparseable JSON after 2 attempts",
        error="json_parse_failed",
    )
