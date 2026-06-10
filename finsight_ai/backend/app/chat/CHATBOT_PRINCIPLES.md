# Coral Chatbot — Design Principles

## What already exists (do not re-implement)

| Component | Location | Status |
|---|---|---|
| Chat API endpoint | `api/chat.py` — POST `/api/v1/chat/query` | Live |
| SSE streaming endpoint | `api/chat.py` — POST `/api/v1/chat/stream` | Live |
| Intent classifier | `services/intent_classifier.py` | Live — Gemma4 + rule fallback |
| Chat router | `services/chat_router.py` | Live — 3-tier SQL fallback chain |
| SQL query handlers | `services/sql_query.py` | Live — 11 deterministic handlers |
| Answer builder | `services/answer_builder.py` | Live — LLM narrative over data |
| Normalization | `services/normalization.py` | Live — institution/category/account/date |
| LLM client | `services/llm.py` | Live — httpx → Ollama, streaming added |
| Pydantic schemas | `domain/classification.py`, `domain/entities.py` | Live |
| Tests | `tests/test_intent_classifier.py`, `test_chat_router.py`, `test_normalization.py` | Live |

## Data Source Hierarchy

1. **SQLite is the source of truth** for transactions, balances, fees, holdings, accounts, and institutions.
2. **FTS5 / vector search** is for document text, statement explanations, and evidence retrieval.
3. **Gemma 4 (Ollama)** explains and formats — it never calculates or invents financial data.
4. **Pydantic** validates every LLM output before it reaches routing or the user.

## Non-Negotiable Rules

- **Never send financial data to external APIs.** All LLM calls go to local Ollama only.
- **SQL is authoritative for numeric answers.** Do not let the LLM invent totals, balances, or transaction amounts.
- **Every answer knows its route.** The `StructuredAnswer.query_path` and `intent` fields must always be set.
- **Never return a bare "no data" response.** The fallback chain in `chat_router.py` must always surface helpful context: available categories, institutions, date bounds, and a clarifying question.
- **No destructive actions from chat in v1.** Chat is read-only. Never modify, delete, or create records via chat.
- **No arbitrary LLM-generated SQL in v1.** All SQL is written in `sql_query.py` as parameterized Python functions. The LLM cannot write or execute SQL.
- **Ambiguous questions trigger clarification**, not guessed answers. If required entities (account, date range) are missing and cannot be safely defaulted, set `needs_clarification=True` and emit a short clarifying question.
- **If data is missing, say what is missing.** The answer must name what was searched and what was not found, then suggest what the user can try.
- **Mask account numbers in logs and answers.** Never show full account numbers.
- **No internal errors in chat answers.** Stack traces and SQL errors must be caught and replaced with chat-safe messages.

## Intent → Route Mapping

| ChatIntent | Internal QueryIntent | Route |
|---|---|---|
| spending_summary | SPENDING_BY_CATEGORY | SQL |
| income_summary | CASH_FLOW_SUMMARY | SQL |
| balance_summary | BALANCE_LOOKUP | SQL |
| transaction_search | TRANSACTION_LOOKUP | SQL |
| investment_summary | HOLDINGS_TOTAL | HYBRID |
| fees_summary | FEE_SUMMARY | HYBRID |
| document_lookup | TEXT_EXPLANATION | FTS/VECTOR |
| account_summary | BALANCE_LOOKUP | SQL |
| comparison | SPENDING_BY_CATEGORY | SQL |
| unknown | HYBRID_FINANCIAL_QUESTION | HYBRID |

## SSE Streaming Event Protocol

Events emitted by `POST /api/v1/chat/stream`:

```
event: status
data: {"message": "Understanding your question..."}

event: intent
data: {"domain": "banking", "intent": "spending_summary", "confidence": 0.94}

event: tool_start
data: {"tool": "sql_query", "intent": "spending_by_category"}

event: tool_result
data: {"row_count": 12, "summary": "Total spending: $2,341"}

event: answer_token
data: {"text": "You spent $2,341..."}

event: done
data: {"request_id": "abc-123"}
```

On error:
```
event: error
data: {"message": "Could not reach Ollama. Is it running?"}

event: done
data: {}
```

## Adding New Intents

1. Add the value to `ChatIntent` in `domain/classification.py`
2. Add a mapping in `intent_mapping.py` (`to_query_intent`, `default_data_source`, `rule_classify`)
3. Add a SQL handler in `sql_query.py` `_INTENT_HANDLERS`
4. Add a rule pattern in `query_router.py` `_INTENT_PATTERNS` (legacy, kept for backward compat)
5. Add golden questions for the new intent in `chat/evals/golden_questions.yaml`
6. Run `python scripts/debug_chat.py --question "<example question>"`

## Adding New Institution Aliases

Edit `services/normalization.py` → `_INSTITUTIONS` dict.
Format: `"slug": ("Display Name", ["alias1", "alias2", ...])`
Whole-word-only aliases (to avoid false positives) go in `_WHOLE_WORD_ALIASES`.

## Debugging a Bad Answer

```bash
python scripts/debug_chat.py --question "How much did I spend on Amex Gold last month?"
```

Output shows: classified_intent → extracted_entities → selected_route → tool_name → tool_result → final_answer → errors

Check logs at `logs/coral.log` for the full structured trace.

## Intent Taxonomy (current)

| ChatIntent | Internal QueryIntent | Route |
|---|---|---|
| spending_summary | SPENDING_BY_CATEGORY | SQL |
| income_summary | CASH_FLOW_SUMMARY | SQL |
| balance_summary | BALANCE_LOOKUP | SQL |
| transaction_search | TRANSACTION_LOOKUP | SQL |
| recurring_transactions | RECURRING_TRANSACTIONS | SQL |
| investment_summary | HOLDINGS_TOTAL | HYBRID |
| fees_summary | FEE_SUMMARY | HYBRID |
| document_lookup | TEXT_EXPLANATION | FTS/VECTOR |
| account_summary | BALANCE_LOOKUP | SQL |
| comparison | SPENDING_COMPARISON | SQL |
| unknown | HYBRID_FINANCIAL_QUESTION | HYBRID |

## Conversation Memory

Follow-up questions are resolved via `chat/services/conversation_context.py`.

The `ConversationContextService` singleton stores the last 10 turns per `conversation_id` (TTL 30 min).
On each new turn, missing entities (institution, account, category, date range) are inherited from the prior turn.
Explicit values in the new question always override inherited values.

The `conversation_id` is passed in `ChatRequest.conversation_id`. The API generates a UUID if omitted.

## Phase Completion Status

| Phase | Status | Notes |
|---|---|---|
| 0 — Inspection | Complete | This document |
| 1 — Pydantic contracts | Complete | `domain/classification.py`, `domain/entities.py`; `amount_min`/`amount_max` added |
| 2 — Intent classifier | Complete | `services/intent_classifier.py`; `recurring_transactions` intent added |
| 3 — Entity extraction/normalization | Complete | `services/normalization.py`; aliases for bofa/marcus/roth/529 added; `amount_min`/`amount_max` wired end-to-end |
| 4 — Banking SQL tools | Complete | `services/sql_query.py` (13 handlers); `_recurring_transactions` + `_spending_comparison` added |
| 5 — Answer generator | Complete | `services/answer_builder.py` |
| 6 — LangGraph orchestration | Not applicable | `services/chat_router.py` serves this role deterministically; LangGraph adds no value here |
| 7 — SSE streaming | Complete | `api/chat.py` `/chat/stream`; guardrails wired; `conversation_id` threaded |
| 8 — Document RAG | Complete | `services/text_search.py`, `services/vector_search.py` integrated in answer_builder |
| 9 — Hybrid SQL+RAG | Complete | `QueryPath.HYBRID` in chat_router + answer_builder |
| 10 — Clarification | Complete | `needs_clarification` in classification → `_clarification_answer` in chat_router |
| 11 — Conversation memory | Complete | `chat/services/conversation_context.py`; in-memory, 30-min TTL, follow-up inheritance |
| 12 — Table/chart payloads | Complete | `chart_builder.py`, `sections` in StructuredAnswer |
| 13 — Golden question evals | Complete | `chat/evals/golden_questions.yaml` (60 questions); runner works; eval expectations corrected |
| 14 — Observability/logging | Complete | structlog, request_id + conversation_id tracing throughout |
| 15 — Human correction loop | Not started | Future sprint |
| 16 — Investment tools | Partial | HOLDINGS_TOTAL, HOLDINGS_LOOKUP, BALANCE_LOOKUP exist; ira_summary/contribution_summary pending |
| 17 — Proactive insights | Not started | Future sprint |
| 18 — MCP-compatible tool contracts | Not started | Future sprint |
| 19 — Security guardrails | Complete | `chat/guardrails.py`; `apply_guardrails_to_answer` wired into streaming pipeline |
| 20 — Chat UX polish | Not started | After backend is solid |
