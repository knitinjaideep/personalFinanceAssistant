"""
Intent classifier service.

Primary path: rule-based classifier (~0ms). The LLM is only called for
questions the rules cannot confidently classify (confidence < threshold).

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
from app.services.intent_mapping import default_data_source, rule_classify, RULE_CONFIDENCE_THRESHOLD

logger = get_logger(__name__)


_SYSTEM_PROMPT = """You are a strict intent classifier for a personal-finance assistant.
You NEVER answer the user's question. You ONLY output a single JSON object.

Classify the question into exactly one intent from this list:
- transaction_search       : find/list specific transactions, charges, purchases
- spending_summary         : how much was spent (totals, by category/merchant)
- income_summary           : income, deposits, paychecks, money coming in
- balance_summary          : account balances, cash on hand
- investment_summary       : portfolio, holdings, allocation, total invested
- fees_summary             : fees charged (advisory, account, trading, late)
- document_lookup          : what a statement/document says (text, disclosures, interest terms)
- account_summary          : a high-level overview of accounts
- comparison               : compare spending between two periods or institutions
- recurring_transactions   : subscriptions, recurring charges, auto-payments, memberships
- unknown                  : cannot tell

Pick the data_source:
- sql     : exact numeric questions (totals, sums, lists, balances)
- rag     : "what does my statement/document say" style questions
- hybrid  : needs both totals AND document evidence (e.g. fees explanation, investment allocation)
- unknown : only if intent is unknown

Extract entities. For time_range.type use "relative" (e.g. last_month, this_month,
last_3_months), "absolute" (e.g. january_2025, q1_2025), or "none". Leave start_date
and end_date null unless the user gave explicit dates.

For amount filters: if the user says "over $100" set amount_min=100.0, "under $50" set
amount_max=50.0, "between $20 and $200" set both. Leave null if no amount filter given.

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
    },
    "amount_min": <float or null>,
    "amount_max": <float or null>
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

    Fast path: rule classifier runs first (zero latency). If it returns
    confidence >= RULE_CONFIDENCE_THRESHOLD the result is used immediately —
    no LLM call is made.

    Slow path: only ambiguous questions (confidence below threshold) fall
    through to a single LLM attempt. If that fails too, we return the rule
    result or unknown fallback.
    """
    req_id = get_request_id()

    # ── 1. Rule classifier (primary — ~0ms) ──────────────────────────────────
    rule_result = rule_classify(question)
    if rule_result.confidence >= RULE_CONFIDENCE_THRESHOLD:
        logger.info(
            "intent_classifier.rule_hit",
            extra={
                "stage": "intent_classified",
                "request_id": req_id,
                "intent": rule_result.intent.value,
                "data_source": rule_result.data_source.value,
                "confidence": round(rule_result.confidence, 3),
                "source": "rule",
            },
        )
        return rule_result

    # ── 2. LLM fallback for ambiguous questions ───────────────────────────────
    model = settings.ollama.classification_model
    prompt = _build_prompt(question)
    last_raw = ""
    try:
        raw = await llm.generate(
            prompt,
            model=model,
            system=_SYSTEM_PROMPT,
            temperature=0.0,
            format_json=True,
            num_ctx=settings.ollama.classification_num_ctx,
        )
        last_raw = raw
        result = _validate(raw)
        logger.info(
            "intent_classifier.llm_hit",
            extra={
                "stage": "intent_classified",
                "request_id": req_id,
                "model": model,
                "intent": result.intent.value,
                "data_source": result.data_source.value,
                "confidence": round(result.confidence, 3),
                "rule_confidence": round(rule_result.confidence, 3),
            },
        )
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "intent_classifier.llm_failed",
            extra={
                "stage": "intent_classify_failed",
                "request_id": req_id,
                "model": model,
                "error": str(exc),
                "raw_output": last_raw[:300],
            },
        )

    # ── 3. Return rule result even if low confidence, or unknown ─────────────
    if rule_result.intent != ChatIntent.UNKNOWN:
        return rule_result

    logger.warning(
        "intent_classifier.unknown_fallback",
        extra={"stage": "intent_classified", "request_id": req_id},
    )
    return IntentClassificationResult.unknown_fallback(source="invalid")
