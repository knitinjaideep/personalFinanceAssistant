"""
Phase 7 tests: LLM grounding — JSON output parsing and fallback behaviour.

Tests cover _extract_summary_from_llm_json without calling Ollama.
"""

from __future__ import annotations

import pytest


FALLBACK = "Total spend: $482.31"


def _extract(raw: str) -> str:
    from app.services.answer_builder import _extract_summary_from_llm_json
    return _extract_summary_from_llm_json(raw, FALLBACK)


# ── Happy path ────────────────────────────────────────────────────────────────

def test_clean_json_extracts_summary():
    raw = '{"summary": "You spent $482.31 at Costco.", "highlights": [], "caveats": []}'
    assert _extract(raw) == "You spent $482.31 at Costco."

def test_json_with_markdown_fence_extracts_summary():
    raw = '```json\n{"summary": "Your fees were $150.00.", "caveats": []}\n```'
    assert _extract(raw) == "Your fees were $150.00."

def test_json_with_leading_whitespace():
    raw = '   \n{"summary": "Balance is $10,000.00.", "highlights": []}\n'
    assert _extract(raw) == "Balance is $10,000.00."


# ── PLAIN: fallback signal ────────────────────────────────────────────────────

def test_plain_prefix_returns_inline_text():
    raw = "PLAIN: You spent $482.31 at Costco in May."
    assert _extract(raw) == "You spent $482.31 at Costco in May."


# ── Failure fallbacks ─────────────────────────────────────────────────────────

def test_invalid_json_returns_fallback():
    raw = "This is just plain text with no JSON at all."
    assert _extract(raw) == FALLBACK

def test_empty_summary_field_returns_fallback():
    raw = '{"summary": "", "caveats": []}'
    assert _extract(raw) == FALLBACK

def test_null_summary_field_returns_fallback():
    raw = '{"summary": null}'
    assert _extract(raw) == FALLBACK

def test_missing_summary_key_returns_fallback():
    raw = '{"highlights": ["foo"]}'
    assert _extract(raw) == FALLBACK

def test_truncated_json_returns_fallback():
    raw = '{"summary": "incomplete'
    assert _extract(raw) == FALLBACK

def test_empty_string_returns_fallback():
    assert _extract("") == FALLBACK


# ── build_grounded_prompt sanity check ───────────────────────────────────────

def test_grounded_prompt_includes_facts():
    from app.chat.fact_builder import FactBundle
    from app.services.answer_builder import _build_grounded_prompt

    bundle = FactBundle(
        total_spend=482.31,
        transaction_count=4,
        rows_used=4,
        filters_used={"merchant": "Costco"},
        caveats=["Merchant filter applied."],
    )
    context = "Total spend: $482.31\nTransaction count: 4"
    prompt = _build_grounded_prompt("Costco spend?", context, bundle, timeframe_label="May 2026")

    assert "482.31" in prompt
    assert "May 2026" in prompt
    assert "Costco" in prompt
    assert "Merchant filter applied" in prompt
    assert "do not recalculate" in prompt.lower()
