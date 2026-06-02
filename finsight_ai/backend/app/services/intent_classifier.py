"""
Intent classifier service.

Takes a raw user question, calls the local Ollama model (``settings.ollama.model``)
with a strict JSON-only system prompt, and validates the response through
``IntentClassificationResult``.

Robustness:
  - Retries once if JSON parsing / validation fails.
  - Logs the raw model output on failure.
  - Falls back to a deterministic rule-based classifier, then to
    ``intent=unknown, confidence=0`` if everything fails.

This service never answers the user — it only classifies.
"""

from __future__ import annotations

import json

from app.config import settings
from app.core.logger import get_logger, get_request_id
from app.domain.classification import (
    ChatIntent,
    DataSource,
    IntentClassificationResult,
)
from app.services import llm
from app.services.intent_mapping import default_data_source, rule_classify

logger = get_logger(__name__)


_SYSTEM_PROMPT = """You are a strict intent classifier for a personal-finance assistant.
You NEVER answer the user's question. You ONLY output a single JSON object.

Classify the question into exactly one intent from this list:
- transaction_search   : find/list specific transactions, charges, purchases
- spending_summary     : how much was spent (totals, by category/merchant)
- income_summary       : income, deposits, paychecks, money coming in
- balance_summary      : account balances, cash on hand
- investment_summary   : portfolio, holdings, allocation, total invested
- fees_summary         : fees charged (advisory, account, trading, late)
- document_lookup      : what a statement/document says (text, disclosures, interest terms)
- account_summary      : a high-level overview of accounts
- comparison           : compare two periods/institutions/categories
- unknown              : cannot tell

Pick the data_source:
- sql     : exact numeric questions (totals, sums, lists, balances)
- rag     : "what does my statement/document say" style questions
- hybrid  : needs both totals AND document evidence (e.g. fees explanation, investment allocation)
- unknown : only if intent is unknown

Extract entities. For time_range.type use "relative" (e.g. last_month, this_month,
last_3_months), "absolute" (e.g. january_2025, q1_2025), or "none". Leave start_date
and end_date null unless the user gave explicit dates.

Set needs_clarification=true ONLY when the question is genuinely impossible to route.
Prefer making a confident best guess over asking for clarification.

Return ONLY this JSON shape, nothing else:
{
  "intent": "<one of the intents>",
  "confidence": <float 0.0-1.0>,
  "entities": {
    "category": <string or null>,
    "merchant": <string or null>,
    "institution": <string or null>,
    "account": <string or null>,
    "compare_to": <string or null>,
    "time_range": {
      "type": "relative" | "absolute" | "none",
      "value": <string or null>,
      "start_date": <ISO date or null>,
      "end_date": <ISO date or null>
    }
  },
  "data_source": "sql" | "rag" | "hybrid" | "unknown",
  "needs_clarification": <bool>,
  "clarifying_question": <string or null>
}

Examples:
Q: "How much did I spend on groceries last month?"
{"intent":"spending_summary","confidence":0.94,"entities":{"category":"groceries","merchant":null,"institution":null,"account":null,"compare_to":null,"time_range":{"type":"relative","value":"last_month","start_date":null,"end_date":null}},"data_source":"sql","needs_clarification":false,"clarifying_question":null}

Q: "Show me Chase transactions from January"
{"intent":"transaction_search","confidence":0.93,"entities":{"category":null,"merchant":null,"institution":"chase","account":null,"compare_to":null,"time_range":{"type":"absolute","value":"january","start_date":null,"end_date":null}},"data_source":"sql","needs_clarification":false,"clarifying_question":null}

Q: "What fees did Morgan Stanley charge me?"
{"intent":"fees_summary","confidence":0.9,"entities":{"category":null,"merchant":null,"institution":"morgan stanley","account":null,"compare_to":null,"time_range":{"type":"none","value":null,"start_date":null,"end_date":null}},"data_source":"hybrid","needs_clarification":false,"clarifying_question":null}

Q: "What does my Amex statement say about interest?"
{"intent":"document_lookup","confidence":0.9,"entities":{"category":null,"merchant":null,"institution":"amex","account":null,"compare_to":null,"time_range":{"type":"none","value":null,"start_date":null,"end_date":null}},"data_source":"rag","needs_clarification":false,"clarifying_question":null}

Q: "Compare my Chase spending in March vs April"
{"intent":"comparison","confidence":0.92,"entities":{"category":null,"merchant":null,"institution":"chase","account":null,"compare_to":"april","time_range":{"type":"absolute","value":"march","start_date":null,"end_date":null}},"data_source":"sql","needs_clarification":false,"clarifying_question":null}

Q: "What is my current investment allocation?"
{"intent":"investment_summary","confidence":0.9,"entities":{"category":null,"merchant":null,"institution":null,"account":null,"compare_to":null,"time_range":{"type":"none","value":null,"start_date":null,"end_date":null}},"data_source":"hybrid","needs_clarification":false,"clarifying_question":null}
"""


def _build_prompt(question: str) -> str:
    return f'Classify this question. Output JSON only.\n\nQuestion: "{question}"'


def _validate(raw: str) -> IntentClassificationResult:
    """Parse + validate raw model text into a classification result.

    Raises on failure (caller decides retry / fallback).
    """
    text = raw.strip()
    # Some models wrap JSON in ```json fences — strip them defensively.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    # Grab the first {...} block if extra prose leaked in.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    data = json.loads(text)
    result = IntentClassificationResult.model_validate(data)

    # Backfill an unknown data_source from the intent default.
    if result.data_source == DataSource.UNKNOWN and result.intent != ChatIntent.UNKNOWN:
        result.data_source = default_data_source(result.intent)
    result.source = "llm"
    return result


async def classify(question: str) -> IntentClassificationResult:
    """Classify a user question into a validated IntentClassificationResult.

    Tries the LLM (with one retry), then a rule-based fallback, then unknown.
    """
    req_id = get_request_id()
    model = settings.ollama.model
    prompt = _build_prompt(question)

    last_raw = ""
    for attempt in (1, 2):
        try:
            raw = await llm.generate(
                prompt,
                model=model,
                system=_SYSTEM_PROMPT,
                temperature=0.0,
                format_json=True,
            )
            last_raw = raw
            result = _validate(raw)
            logger.info(
                "intent_classifier.ok",
                extra={
                    "stage": "intent_classified",
                    "request_id": req_id,
                    "attempt": attempt,
                    "model": model,
                    "intent": result.intent.value,
                    "data_source": result.data_source.value,
                    "confidence": round(result.confidence, 3),
                    "needs_clarification": result.needs_clarification,
                },
            )
            return result
        except Exception as exc:  # noqa: BLE001 — broad: parse, validation, or LLM errors
            logger.warning(
                "intent_classifier.parse_failed",
                extra={
                    "stage": "intent_classify_failed",
                    "request_id": req_id,
                    "attempt": attempt,
                    "model": model,
                    "error": str(exc),
                    "raw_output": last_raw[:500],
                },
            )

    # ── LLM path exhausted → deterministic rule fallback ─────────────────────
    rule_result = rule_classify(question)
    if rule_result.intent != ChatIntent.UNKNOWN:
        logger.info(
            "intent_classifier.rule_fallback",
            extra={
                "stage": "intent_classified",
                "request_id": req_id,
                "intent": rule_result.intent.value,
                "data_source": rule_result.data_source.value,
                "confidence": round(rule_result.confidence, 3),
                "source": "rule_fallback",
            },
        )
        return rule_result

    logger.warning(
        "intent_classifier.unknown_fallback",
        extra={"stage": "intent_classified", "request_id": req_id, "source": "invalid"},
    )
    return IntentClassificationResult.unknown_fallback(source="invalid")
