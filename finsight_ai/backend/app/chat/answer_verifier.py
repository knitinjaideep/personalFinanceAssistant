"""
Answer Verifier — Phase 8.

Deterministic safety net that runs before every answer leaves the pipeline.
It checks that the answer text is consistent with the FactBundle, never
presents a positive result when no data exists, and does not claim trends
without comparison facts.

Design principles:
  - Prefer deterministic checks over another LLM call.
  - Never block a correct answer; only flag genuine inconsistencies.
  - When a check fails, repair with a deterministic template rather than
    silently suppressing the answer.

Usage:
    from app.chat.answer_verifier import verify_answer

    result = verify_answer(question, fact_bundle, answer)
    if result.repaired:
        answer.summary = result.repaired_summary
    answer.caveats.extend(result.warnings_as_caveats())
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

from app.chat.fact_builder import FactBundle
from app.core.logger import get_logger
from app.domain.entities import StructuredAnswer

logger = get_logger(__name__)

# ── Verifier result ────────────────────────────────────────────────────────────

class VerifierResult(BaseModel):
    passed: bool = True
    warnings: list[str] = []
    repaired: bool = False
    repaired_summary: str | None = None

    def warnings_as_caveats(self) -> list[str]:
        return self.warnings if not self.passed else []


# ── Public entry point ─────────────────────────────────────────────────────────

def verify_answer(
    question: str,
    fact_bundle: FactBundle,
    answer: StructuredAnswer,
) -> VerifierResult:
    """
    Run all deterministic checks against the draft answer.

    Returns a VerifierResult. If repaired=True, the caller should replace
    answer.summary with result.repaired_summary before returning to the user.
    """
    warnings: list[str] = []

    summary = answer.summary or ""

    # ── Check 1: no-data answers must not present a positive claim ─────────────
    if fact_bundle.rows_used == 0 and answer.answer_type != "no_data":
        money_pattern = _money_regex()
        if money_pattern.search(summary):
            warnings.append(
                "Answer contains a dollar amount but no data rows were found."
            )

    # ── Check 2: numbers in the answer must exist in FactBundle ───────────────
    hallucinated = _find_hallucinated_amounts(summary, fact_bundle)
    for amt in hallucinated:
        warnings.append(f"Answer mentions ${amt:,.2f} which is not in the computed facts.")

    # ── Check 3: trend/comparison language requires comparison facts ──────────
    if _claims_trend(summary) and fact_bundle.comparison is None:
        warnings.append(
            "Answer uses trend/comparison language but no comparison data is available."
        )

    # ── Check 4: institution mismatch ─────────────────────────────────────────
    inst_warning = _check_institution(summary, fact_bundle)
    if inst_warning:
        warnings.append(inst_warning)

    # ── Check 5: date range mismatch ──────────────────────────────────────────
    date_warning = _check_date_range(summary, fact_bundle)
    if date_warning:
        warnings.append(date_warning)

    # ── Check 6: no-data result but answer says something was found ────────────
    if (
        fact_bundle.rows_used == 0
        and answer.answer_type != "no_data"
        and _claims_found(summary)
    ):
        warnings.append(
            "Answer claims data was found but the query returned zero rows."
        )

    passed = len(warnings) == 0

    # ── Repair: if critical failures, replace with a safe caveated answer ─────
    repaired = False
    repaired_summary: str | None = None

    if warnings:
        logger.warning(
            "answer_verifier.check_failed",
            extra={
                "passed": passed,
                "warning_count": len(warnings),
                "warnings": warnings,
                "rows_used": fact_bundle.rows_used,
                "answer_type": answer.answer_type,
                "summary_preview": summary[:120],
            },
        )

    if not passed and _is_critical(warnings):
        repaired_summary = _build_safe_answer(fact_bundle, question)
        repaired = True
        logger.warning(
            "answer_verifier.repaired",
            extra={"repaired_summary": repaired_summary[:120]},
        )

    return VerifierResult(
        passed=passed,
        warnings=warnings,
        repaired=repaired,
        repaired_summary=repaired_summary,
    )


# ── Individual checks ──────────────────────────────────────────────────────────

_MONEY_RE: re.Pattern[str] | None = None


def _money_regex() -> re.Pattern[str]:
    global _MONEY_RE
    if _MONEY_RE is None:
        _MONEY_RE = re.compile(r"\$[\d,]+(?:\.\d{1,2})?")
    return _MONEY_RE


def _extract_dollar_amounts(text: str) -> set[float]:
    """Pull every dollar amount mentioned in the text."""
    amounts: set[float] = set()
    for match in _money_regex().finditer(text):
        raw = match.group().replace("$", "").replace(",", "")
        try:
            amounts.add(round(float(raw), 2))
        except ValueError:
            pass
    return amounts


def _fact_bundle_amounts(bundle: FactBundle) -> set[float]:
    """Collect all dollar values present in the FactBundle."""
    known: set[float] = set()

    def _add(v: float | None) -> None:
        if v is not None:
            known.add(round(abs(v), 2))

    _add(bundle.total_spend)
    _add(bundle.total_income)
    _add(bundle.net_cash_flow)
    _add(bundle.total_fees)
    _add(bundle.balance)
    _add(bundle.holdings_value)
    _add(bundle.average_transaction)

    for c in bundle.top_categories:
        _add(c.amount)
    for m in bundle.top_merchants:
        _add(m.amount)
    if bundle.comparison:
        _add(bundle.comparison.period_a_value)
        _add(bundle.comparison.period_b_value)
        _add(bundle.comparison.delta)

    return known


def _find_hallucinated_amounts(text: str, bundle: FactBundle) -> list[float]:
    """Return amounts in `text` not present in (or derivable from) FactBundle."""
    if bundle.rows_used == 0:
        return []  # no-data answers handled by check 1

    mentioned = _extract_dollar_amounts(text)
    if not mentioned:
        return []

    known = _fact_bundle_amounts(bundle)

    hallucinated: list[float] = []
    for amt in mentioned:
        if not _amount_is_known(amt, known):
            hallucinated.append(amt)

    return hallucinated


def _amount_is_known(amt: float, known: set[float], tolerance: float = 0.02) -> bool:
    """Check if `amt` is in known set within a small tolerance (rounding)."""
    return any(abs(amt - k) <= tolerance for k in known)


_TREND_PHRASES: tuple[str, ...] = (
    "increased", "decreased", "went up", "went down",
    "rose", "fell", "higher than", "lower than",
    "more than last", "less than last", "compared to",
    "up from", "down from", "grew by", "dropped by",
    "change from", "change of",
)


def _claims_trend(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in _TREND_PHRASES)


_FOUND_PHRASES: tuple[str, ...] = (
    "you spent", "total spend", "total of",
    "your balance", "your holdings", "you paid",
)

_NEGATION_PHRASES: tuple[str, ...] = (
    "no ", "not ", "couldn't find", "could not find",
    "i found no", "no transactions", "no data", "no matching",
)


def _claims_found(text: str) -> bool:
    lower = text.lower()
    # Skip if the sentence is a negation
    if any(neg in lower for neg in _NEGATION_PHRASES):
        return False
    return any(phrase in lower for phrase in _FOUND_PHRASES)


def _check_institution(text: str, bundle: FactBundle) -> str | None:
    """Warn if the answer names an institution not in the facts."""
    if not bundle.institution:
        return None

    # Normalize bundle institution to common name
    inst_lower = bundle.institution.lower().replace("_", " ")
    known_name_parts = set(inst_lower.split())

    # Check that the text doesn't name a completely different institution
    _INSTITUTIONS = [
        "morgan stanley", "chase", "amex", "american express",
        "discover", "etrade", "e*trade", "marcus", "bank of america",
    ]
    for other in _INSTITUTIONS:
        other_parts = set(other.split())
        # Skip if this other name overlaps with known institution
        if other_parts & known_name_parts:
            continue
        if other in text.lower():
            return (
                f"Answer mentions '{other}' but facts are from "
                f"'{bundle.institution.replace('_', ' ').title()}'."
            )
    return None


def _check_date_range(text: str, bundle: FactBundle) -> str | None:
    """Warn if the answer references a date range that contradicts the facts."""
    if not (bundle.date_from and bundle.date_to):
        return None

    # Extract four-digit years from the answer
    years_in_text = {int(y) for y in re.findall(r"\b(20\d{2})\b", text)}
    if not years_in_text:
        return None

    valid_years = {bundle.date_from.year, bundle.date_to.year}
    invalid = years_in_text - valid_years
    # Allow one year of slack (e.g. "last year" comparisons)
    invalid = {y for y in invalid if abs(y - bundle.date_from.year) > 1}
    if invalid:
        return (
            f"Answer references year(s) {sorted(invalid)} "
            f"but data covers {bundle.date_from.year}–{bundle.date_to.year}."
        )
    return None


# ── Repair helper ──────────────────────────────────────────────────────────────

_CRITICAL_PREFIXES: tuple[str, ...] = (
    "Answer contains a dollar amount but no data rows",
    "Answer claims data was found but the query returned zero rows",
)


def _is_critical(warnings: list[str]) -> bool:
    return any(
        any(w.startswith(p) for p in _CRITICAL_PREFIXES)
        for w in warnings
    )


def _build_safe_answer(bundle: FactBundle, question: str) -> str:
    """Build a deterministic safe answer when the LLM answer failed verification."""
    if bundle.rows_used == 0:
        return (
            "I searched your statements but couldn't find matching data for that question. "
            "Try uploading more statements or rephrasing with a specific time period or account."
        )
    # Provide the key fact without LLM embellishment
    parts: list[str] = []
    if bundle.total_spend is not None:
        parts.append(f"Total spend: ${bundle.total_spend:,.2f}")
    if bundle.total_fees is not None:
        parts.append(f"Total fees: ${bundle.total_fees:,.2f}")
    if bundle.balance is not None:
        parts.append(f"Balance: ${bundle.balance:,.2f}")
    if bundle.holdings_value is not None:
        parts.append(f"Holdings: ${bundle.holdings_value:,.2f}")
    if bundle.transaction_count:
        parts.append(f"Transactions: {bundle.transaction_count}")
    if parts:
        return "Here is what I found: " + "; ".join(parts) + "."
    return "I found data but could not generate a verified answer. Please try rephrasing."
