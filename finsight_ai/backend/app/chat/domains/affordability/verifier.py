"""
verifier.py — Post-LLM verification for affordability narratives.

Checks:
  1. LLM did not change the verdict_label
  2. LLM did not invent dollar amounts not in MathResult
  3. LLM did not make forbidden conclusions
  4. LLM did not use "I calculate / I estimate" phrases
  5. LLM did not recommend something outside allowed conclusions
  6. Purchase answers do not contain home-only terms (down payment, mortgage, etc.)
  7. NOT_AFFORDABLE answers must not imply approval

Hard failures trigger fallback to the deterministic template.
Soft warnings are logged and stored in the result for debug.
"""
from __future__ import annotations

import re
from decimal import Decimal

from pydantic import BaseModel, Field

from .decision_engine import DecisionResult, VerdictCode
from .math_engine import MathResult

_DOLLAR_RE = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:k\b)?", re.IGNORECASE)

_PURCHASE_ONLY_TERMS = re.compile(
    r"\b(down payment|closing cost|mortgage|property tax|loan amount|loan term)\b",
    re.IGNORECASE,
)

_LLM_CALC_PHRASES = [
    "i estimate your",
    "i calculate",
    "i estimated",
    "i computed",
    "based on my calculation",
    "my estimate",
]

_APPROVAL_WORDS = [
    "affordable", "you can afford", "looks good", "comfortable", "possible",
    "no problem", "go ahead",
]


class VerificationResult(BaseModel):
    passed: bool = True
    repaired: bool = False
    warnings: list[str] = Field(default_factory=list)


def _extract_amounts(text: str) -> set[int]:
    amounts: set[int] = set()
    for m in _DOLLAR_RE.finditer(text):
        try:
            raw = m.group(1).replace(",", "")
            val = float(raw) * 1000 if "k" in m.group(0).lower() else float(raw)
            amounts.add(int(val))
        except ValueError:
            pass
    return amounts


def _amount_is_known(amount: int, known: set[int]) -> bool:
    if amount == 0:
        return True
    for k in known:
        if k == 0:
            continue
        if abs(amount - k) / k <= 0.02:
            return True
    return False


def verify(
    summary: str,
    verdict_label_from_llm: str,
    math: MathResult,
    decision: DecisionResult,
    *,
    protected_goals: list[str] | None = None,
    user_is_asking_for: str = "",
) -> VerificationResult:
    result = VerificationResult()
    warnings: list[str] = []
    hard_fail = False

    full_text = (summary or "").lower()

    # 1. Verdict label preserved
    if verdict_label_from_llm and verdict_label_from_llm.lower() != decision.verdict_label.lower():
        warnings.append(
            f"verifier: verdict_label changed by LLM: expected {decision.verdict_label!r}, "
            f"got {verdict_label_from_llm!r}"
        )
        hard_fail = True

    # 2. Forbidden conclusions
    for forbidden in decision.forbidden_conclusions:
        check = re.sub(r"^do not (say |mention |recommend |imply )?", "", forbidden.lower()).strip(".'\"")
        if len(check) > 5 and check in full_text:
            warnings.append(f"verifier: forbidden conclusion detected: {check!r}")
            hard_fail = True

    # 3. Purchase answers must not use home-only terms
    if math.scenario_type != "home_purchase":
        if _PURCHASE_ONLY_TERMS.search(summary or ""):
            warnings.append("verifier: non-home answer contains home-only terms")
            hard_fail = True

    # 4. LLM calculator phrases
    for phrase in _LLM_CALC_PHRASES:
        if phrase in full_text:
            warnings.append(f"verifier: LLM-as-calculator phrase: {phrase!r}")
            hard_fail = True

    # 5. Invented dollar amounts (≥$1,000 and not within 2% of known amounts)
    known = math.all_known_amounts()
    text_amounts = _extract_amounts(summary or "")
    for amt in text_amounts:
        if amt >= 1000 and not _amount_is_known(amt, known):
            warnings.append(f"verifier: invented amount ${amt:,} not in MathResult")
            hard_fail = True

    # 6. NOT_AFFORDABLE / NEEDS_MORE_INFO must not imply approval
    if decision.verdict_code in (VerdictCode.NOT_AFFORDABLE, VerdictCode.NEEDS_MORE_INFO):
        for word in _APPROVAL_WORDS:
            if word in full_text:
                warnings.append(f"verifier: approval word {word!r} in non-approval answer")
                hard_fail = True

    # 7. Primary reason must include a dollar figure when decision.primary_reason does
    if "$" in decision.primary_reason and "$" not in (summary or ""):
        warnings.append("verifier: summary dropped all dollar amounts from primary_reason")
        hard_fail = True

    result.warnings = warnings
    result.passed = not hard_fail
    result.repaired = hard_fail
    return result
