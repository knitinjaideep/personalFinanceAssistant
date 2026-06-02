# Chatbot Intent Pipeline

Coral's chat answers run through a deterministic, fault-tolerant pipeline whose
job is to **never silently return "no data."** Every question is classified,
routed, and — if the obvious query comes back empty — progressively relaxed and
finally answered with whatever context we *do* have.

```
user question
  → intent classifier        (LLM, strict JSON, validated)
  → entity + time extraction  (normalization helpers)
  → route to SQL / RAG / hybrid
  → confidence check
  → fallback chain            (relax SQL → date fallback → RAG → helpful answer)
  → final structured answer + debug metadata
```

## Where the code lives

| Concern | Module |
| --- | --- |
| Typed classifier schema | `backend/app/domain/classification.py` |
| Intent classifier (LLM call + validation + retry) | `backend/app/services/intent_classifier.py` |
| Rule fallback + ChatIntent→QueryIntent mapping | `backend/app/services/intent_mapping.py` |
| Entity normalization (institution / category / time) | `backend/app/services/normalization.py` |
| Routing + fallback chain | `backend/app/services/chat_router.py` |
| "What data exists?" helpers | `backend/app/services/availability.py` |
| SQL handlers (reused, unchanged) | `backend/app/services/sql_query.py` |
| Narrative generation (reused) | `backend/app/services/answer_builder.py` |
| API endpoint | `backend/app/api/chat.py` |
| Model config | `backend/app/config/__init__.py` (`OllamaConfig`) |

## 1. The classifier

`intent_classifier.classify(question)` calls the local Ollama model with a strict
JSON-only system prompt and validates the response through the Pydantic
`IntentClassificationResult`. The validated shape:

```json
{
  "intent": "spending_summary",
  "confidence": 0.92,
  "entities": {
    "category": "groceries",
    "merchant": null,
    "institution": null,
    "account": null,
    "compare_to": null,
    "time_range": {
      "type": "relative",
      "value": "last_month",
      "start_date": null,
      "end_date": null
    }
  },
  "data_source": "sql",
  "needs_clarification": false,
  "clarifying_question": null
}
```

Robustness:

- **Retry once** if JSON parsing/validation fails.
- Tolerates code fences (` ```json `) and surrounding prose (extracts the first
  `{...}` block).
- If both LLM attempts fail → **deterministic rule-based classifier**
  (`intent_mapping.rule_classify`).
- If that is also `unknown` → `intent=unknown, confidence=0`.
- The raw model output is **logged** whenever parsing fails.

## 2. Intent list

`transaction_search`, `spending_summary`, `income_summary`, `balance_summary`,
`investment_summary`, `fees_summary`, `document_lookup`, `account_summary`,
`comparison`, `unknown`.

Each maps to an internal `QueryIntent` (which owns the SQL handlers) in
`intent_mapping.CHAT_TO_QUERY_INTENT`, so the SQL layer was not duplicated.

## 3. Routing logic

`data_source` decides the path:

| data_source | path | when |
| --- | --- | --- |
| `sql` | SQL handlers | exact numeric questions (totals, lists, balances) |
| `rag` | FTS / vector search | "what does my statement say" |
| `hybrid` | SQL first, RAG for evidence | fees explanations, investment allocation |
| `unknown` | broad hybrid fallback | classifier unsure |

Routing examples:

| Question | intent | data_source |
| --- | --- | --- |
| How much did I spend on groceries last month? | spending_summary | sql |
| Show me Chase transactions from January | transaction_search | sql |
| What fees did Morgan Stanley charge me? | fees_summary | hybrid |
| What does my Amex statement say about interest? | document_lookup | rag |
| Compare my Chase spending in March vs April | comparison | sql |
| What is my current investment allocation? | investment_summary | hybrid |

## 4. Fallback chain (no more "no data")

Inside `chat_router.route()`:

- **A. Exact SQL** — full context (category + merchant + institution + dates).
- **B. Relaxed SQL** — drop category/merchant filters (the usual culprit),
  keep institution + dates. Institution & category names are normalized
  (case-insensitive, typo-tolerant: `morgan stanly` → Morgan Stanley).
- **C. Date fallback** — drop the time window, use most-recent available data.
- **D. RAG fallback** — if SQL is still empty on an SQL route, search statement
  chunks.
- **E. Helpful answer** — `chat_router._helpful_answer` states what was searched,
  lists categories / institutions / date ranges that **do** exist, and asks one
  clarifying question. This is the only path that ends in
  `no_data_after_fallback`, and it is never a bare "No data found."

When B or C succeed the answer is marked `partial` and carries a caveat such as
*"I broadened the search by removing the Groceries category filter to find
matching data."*

## 5. Final answer status

Every request logs a `final_answer_status`:

- `answered` — exact SQL/RAG hit
- `partial` — answered via a relaxed/date fallback or RAG-only
- `clarification_needed` — classifier explicitly asked for clarification
- `no_data_after_fallback` — helpful fallback answer (still useful, never blank)

## 6. Choosing / pulling the Ollama model

The model name lives in **one place** — `OllamaConfig.model` in
`backend/app/config/__init__.py`. Nothing else hardcodes a model name.

- Default: `gemma4:latest`
- Override with an environment variable:

  ```bash
  export OLLAMA_MODEL=gemma4:e4b
  ```

  (`CORAL_OLLAMA_MODEL` is also accepted for consistency with the other
  `CORAL_OLLAMA_*` settings.)

Pull Gemma 4 before starting the backend:

```bash
ollama pull gemma4:e4b        # or: ollama pull gemma4:latest
```

At startup the app checks Ollama (`main._check_ollama_model`). If the model is
missing or Ollama is unreachable it logs a clear, actionable error containing the
exact command, e.g. `Run: ollama pull gemma4:e4b`. The app still boots — the chat
pipeline degrades to its rule-based classifier so the API keeps working.

## 7. Observability

Every chat request emits structured logs (Rich console + JSON file at
`logs/coral.log`) carrying `request_id`. Key fields:

- `chat_request_received` — `user_question`, `selected_model`
- `intent_classifier.ok` / `.parse_failed` / `.rule_fallback` / `.unknown_fallback`
  — `intent`, `data_source`, `confidence`, and `raw_output` on failure
- `chat_router.classified` — normalized `category` / `institution` / `timeframe`
- `chat_router.sql_relaxed_hit` / `.sql_date_fallback_hit`
- `chat_request_completed` — `selected_route`, `sql_rows`, `rag_chunks`,
  `fallback_steps`, `final_answer_status`, `duration_ms`

### Example debug log (no-data → helpful fallback)

```json
{"stage":"chat_request_received","request_id":"a1b2","selected_model":"gemma4:e4b","user_question":"how much did I spend on groceries last month?"}
{"stage":"intent_classified","request_id":"a1b2","intent":"spending_summary","data_source":"sql","confidence":0.94}
{"stage":"chat_router_classified","request_id":"a1b2","query_intent":"spending_by_category","category":"groceries","institution":null,"timeframe":"last month"}
{"stage":"sql_fallback","request_id":"a1b2","dropped":"category/merchant"}
{"stage":"chat_request_completed","request_id":"a1b2","selected_route":"fallback","sql_rows":0,"rag_chunks":0,"fallback_steps":["sql_exact","sql_relaxed_filters","sql_date_fallback","rag_fallback","helpful_fallback"],"final_answer_status":"no_data_after_fallback"}
```

## 8. Tests

```bash
cd backend
python -m pytest tests/test_normalization.py tests/test_intent_classifier.py tests/test_chat_router.py -q
```

Covered: normalization (institutions/categories/time), classifier JSON parsing &
retry & fallback, ChatIntent→QueryIntent mapping, the SQL relaxation chain, and
the guarantee that an empty result yields a helpful answer rather than a bare
"no data."
