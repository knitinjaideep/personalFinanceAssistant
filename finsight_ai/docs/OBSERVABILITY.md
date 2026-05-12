# Coral — Observability Guide

Every chat request generates a `request_id` that flows through terminal logs, the JSON log file, the API response, and optionally Better Stack / Logtail. Use it to trace any question end-to-end.

---

## Quick start

```bash
# Start the backend
cd finsight_ai/backend
LOG_LEVEL=INFO uvicorn app.main:app --reload --port 8000

# Tail the JSON log file in a second terminal
tail -f logs/coral.log | jq

# Search all log entries for one request
grep "a3f9c12e" logs/coral.log | jq
```

---

## Log surfaces

| Surface | Format | Always on |
|---|---|---|
| Terminal (stdout) | Rich colored output via `RichHandler` | Yes |
| File (`logs/coral.log`) | Rotating JSON, 50 MB × 5 | Yes |
| Better Stack / Logtail | Structured JSON, remote | Optional |

---

## Terminal logs

The backend console uses `RichHandler` — color-coded, with file/line context.

```
[10:23:01] INFO  coral.middleware   request_started method=POST path=/api/v1/chat/query
[10:23:01] INFO  coral.chat         intent_classification_started
[10:23:01] INFO  app.services.query_router  query.routed intent=fee_summary route=sql confidence=0.920
[10:23:01] INFO  app.services.sql_query     sql_execution_completed result_count=4 duration_ms=3.2
[10:23:02] INFO  app.services.answer_builder response_generation_completed answer_type=numeric
[10:23:02] INFO  coral.chat         chat_request_completed rows_used=4 duration_ms=1230
[10:23:02] INFO  coral.middleware   request_completed status_code=200 duration_ms=1232
```

---

## JSON file logs

Each line in `logs/coral.log` is a JSON object:

```json
{
  "timestamp": "2026-05-12T10:23:01.452Z",
  "level": "INFO",
  "logger": "coral.chat",
  "message": "chat_request_completed",
  "request_id": "a3f9c12e-...",
  "stage": "chat_request_completed",
  "intent": "fee_summary",
  "route": "sql",
  "confidence": 0.92,
  "rows_used": 4,
  "duration_ms": 1230
}
```

### Useful jq queries

```bash
# Follow live
tail -f logs/coral.log | jq

# All stages for one request
grep "a3f9c12e" logs/coral.log | jq '{stage, intent, route, duration_ms}'

# Slow requests (> 5 seconds)
cat logs/coral.log | jq 'select(.stage == "chat_request_completed" and .duration_ms > 5000)'

# All SQL executions
cat logs/coral.log | jq 'select(.stage == "sql_execution_completed") | {request_id, intent, result_count, duration_ms}'

# Failed requests
cat logs/coral.log | jq 'select(.stage == "chat_request_failed")'
```

---

## Log levels

| `LOG_LEVEL` | What you see |
|---|---|
| `INFO` (default) | All stage transitions, intent, route, timings |
| `DEBUG` | Everything above + SQL template + row preview (first 3 rows) |

```bash
# Enable DEBUG
LOG_LEVEL=DEBUG uvicorn app.main:app --reload
# or
DEBUG=true uvicorn app.main:app --reload
```

**Safety**: raw financial row data is only logged in DEBUG mode. It is never logged in production by default.

---

## Request-ID tracing

Every HTTP response includes:

```
X-Request-ID: a3f9c12e-7b14-4c9d-8f2e-1234abcd5678
```

The frontend `DebugPanel` also surfaces it. Copy it and search:

```bash
grep "a3f9c12e-7b14-4c9d-8f2e-1234abcd5678" logs/coral.log | jq
```

---

## Frontend Debug Panel

Add `VITE_DEBUG=true` to `frontend/.env.local`:

```env
VITE_DEBUG=true
```

Then restart `npm run dev`. Each assistant answer will show a collapsible **Debug** bar with:

- `request_id` (first 8 chars shown, copy to grep logs)
- `intent`, `route`, `confidence`
- `rows_used`, `sources`
- Per-stage timings: intent / SQL / RAG / LLM / total
- SQL template used
- Chart payload summary

On a failed answer you will see the `request_id` so you can search the log file.

---

## Better Stack / Logtail

### Setup

1. Create a **Source** in Better Stack → Logs → Sources → New Source → "Node.js / Python"
2. Copy the **Source Token**
3. Add to `finsight_ai/backend/.env`:

```env
BETTERSTACK_ENABLED=true
BETTERSTACK_SOURCE_TOKEN=your_token_here
```

4. Install the Python SDK (if not already installed):

```bash
pip install logtail-python
```

5. Restart the backend. You should see in the startup log:

```
betterstack_enabled=True logtail_enabled=True
```

### Logtail alias (equivalent)

```env
LOGTAIL_ENABLED=true
LOGTAIL_SOURCE_TOKEN=your_token_here
```

### Searching in Better Stack

- All structured fields (request_id, stage, intent, route, duration_ms) are indexed automatically.
- Filter: `request_id = "a3f9c12e-..."` to see all stages for one chat request.
- Filter: `stage = "chat_request_failed"` to see all errors.
- Filter: `stage = "sql_execution_completed" AND duration_ms > 1000` for slow SQL.

### Graceful fallback

If `logtail-python` is not installed, the backend logs a warning and continues without remote shipping. No crash, no data loss.

```
WARNING  coral.logger  logtail-python not installed — remote log shipping disabled.
         Run: pip install logtail-python
```

---

## Startup diagnostics

On every backend startup the following is logged:

```json
{
  "stage": "app_started",
  "environment": "development",
  "debug": true,
  "log_level": "INFO",
  "rich_logging_enabled": true,
  "json_file_logging_enabled": true,
  "betterstack_enabled": false,
  "logtail_enabled": false,
  "database_path": "...",
  "ollama_model": "qwen3:8b",
  "embedding_model": "nomic-embed-text",
  "langgraph_installed": true,
  "langgraph_wired_to_chat": false,
  "registered_routes": 42
}
```

---

## LangGraph status

LangGraph is declared in `pyproject.toml` but **not wired to the chat route**. On startup:

```
WARNING  coral  LangGraph components exist but are not connected to chat route
```

All chat requests use the SQL-first `query_router → sql_query → answer_builder` pipeline.

---

## Verifying SQL vs RAG routing

Chat log entry contains:

```json
{"stage": "route_selected", "route": "sql", "intent": "fee_summary"}
```

Or for text/hybrid:

```json
{"stage": "route_selected", "route": "fts", "intent": "text_explanation"}
```

RAG retrieval result:

```json
{"stage": "rag_retrieval_completed", "chunks_retrieved": 4}
```

If `chunks_retrieved` is 0 and `route` is `fts`, text search returned nothing — check FTS index.

---

## Verification checklist

Run each question and confirm using `grep "<request_id>" logs/coral.log | jq`:

| Question | Expected intent | Expected route |
|---|---|---|
| "How much did I spend on groceries last month?" | `spending_by_category` | `sql` |
| "What fees did I pay Morgan Stanley last month?" | `fee_summary` | `sql` |
| "What subscriptions am I paying?" | `subscription_lookup` | `sql` |
| "What is my total invested amount?" | `holdings_total` | `sql` |

For each, verify:
- `request_id` appears in `ChatResponse.answer.request_id` (visible in DebugPanel)
- Same `request_id` in `logs/coral.log`
- Better Stack receives the same `request_id` if enabled
- `intent` matches expected
- `route` matches expected
- `chat_request_completed` stage shows `rows_used > 0`
