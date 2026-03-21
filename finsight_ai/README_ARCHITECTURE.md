# Coral — Architecture Reference

## Overview

Coral uses a **local-folder-first** data flow:

```
Local folders → Scanner → Parser Registry → SQLite DB → Dashboards + Chat
```

No cloud. No LangGraph. No Chroma. No MCP. SQL is the primary source of truth.

---

## Data flow

### 1. Scan (`GET /api/v1/scan/status`)

The **local scanner** (`services/local_scanner.py`) reads `STATEMENT_SOURCES` from `statement_sources.py` and:
- Globs each `root_path` for `*.pdf` files (recurses into `YYYY/` subdirs)
- Computes SHA-256 for each file
- Checks the `documents` table for existing hashes
- Returns a `ScanResult` with per-source counts: total / ingested / pending / failed / no_parser

No files are written. This is a read-only status check.

### 2. Ingest (`POST /api/v1/scan/ingest`)

For each pending file from the scan:
- Calls `ingest_document(file_path, ...)` in `services/ingestion.py`
- The ingestion pipeline runs sequentially:
  1. Register document in DB (`documents` table)
  2. Parse PDF → raw text + tables via `pdfplumber`
  3. Detect institution via `ParserRegistry.detect_institution()` (confidence scoring)
  4. Extract structured data via `parser.extract()`
  5. Persist canonical records: institution, account, statement, transactions, fees, holdings, balances
  6. Save bank-specific detail fields (chase_details, morgan_stanley_details, etc.)
  7. Chunk text and index in FTS5 (`text_chunks` + `text_chunks_fts`)
  8. Optionally generate embeddings (if vector_search_enabled)

### 3. Dashboard queries

All dashboard data comes from `services/dashboard/`:
- `investment_queries.py` — portfolio value, holdings, fees, balance history
- `banking_queries.py` — spend by month, by category, top merchants, card summary, cash flow
- `summary_queries.py` — top-level KPI counts, document coverage

The `api/dashboard.py` router assembles these into three endpoints:
- `GET /dashboard/investments`
- `GET /dashboard/banking`
- `GET /dashboard/summary`

### 4. Chat

```
User question → QueryRouter (intent classification) → SQL query + optional FTS
→ AnswerBuilder → LLM (formatting only) → StructuredAnswer → UI
```

- `query_router.py` classifies intent (10 explicit types) via regex rules, LLM fallback
- `sql_query.py` executes deterministic SQL for each intent
- `answer_builder.py` assembles a `StructuredAnswer` with human-readable highlights
- LLM (`qwen3:8b`) only formats the narrative — it does not query the DB

---

## Key modules

### Backend (`backend/app/`)

| Module | Purpose |
|--------|---------|
| `statement_sources.py` | Maps local folders → institution/product |
| `services/local_scanner.py` | Discovers PDFs, computes hashes, checks ingest status |
| `services/ingestion.py` | Full ingestion pipeline for one document |
| `parsers/base.py` | `InstitutionParser` ABC + `ParserRegistry` |
| `parsers/<name>/parser.py` | Institution-specific extraction logic |
| `db/models.py` | SQLModel ORM — canonical + detail tables |
| `db/repositories.py` | All DB access (no raw SQL in services) |
| `services/dashboard/investment_queries.py` | Investment dashboard queries |
| `services/dashboard/banking_queries.py` | Banking dashboard queries |
| `services/dashboard/summary_queries.py` | KPI summary queries |
| `api/dashboard.py` | Dashboard API endpoints |
| `api/scan.py` | Scan status + ingest trigger endpoints |
| `services/query_router.py` | Chat intent classification |
| `services/answer_builder.py` | Structures answers, calls LLM for formatting |

### Frontend (`frontend/src/`)

| Module | Purpose |
|--------|---------|
| `pages/HomePage.tsx` | Dashboard home — KPIs, source cards, bucket dashboards |
| `pages/ChatPage.tsx` | Chat interface |
| `api/scan.ts` | Scan status + ingest API calls |
| `api/dashboard.ts` | Dashboard API calls + TypeScript types |
| `components/chat/AnswerCard.tsx` | Structured answer renderer (numeric, table, prose, no_data) |

---

## Parser system

Each parser implements `InstitutionParser` (abstract base in `parsers/base.py`):

```python
class InstitutionParser(ABC):
    institution_type: str         # e.g. "chase"
    institution_name: str         # e.g. "Chase"

    def can_handle(text, metadata) -> float:
        # Returns confidence 0.0–1.0. > 0.7 = strong match.
        # Uses regex/keyword matching on first ~3000 chars. No LLM.

    async def extract(document: ParsedDocument) -> ParsedStatement:
        # Returns canonical ParsedStatement with transactions, fees, holdings, balances.
```

`ParserRegistry.detect_institution()` runs all parsers' `can_handle()` and returns the best match.

---

## Scanner deduplication

Files are deduplicated by SHA-256 hash stored in `documents.file_hash`:

```
New scan → compute hash → check documents table by hash
  → hash found + status=parsed  → INGESTED (skip)
  → hash found + status=failed  → FAILED (retry)
  → hash not found              → PENDING (ingest)
```

This means:
- Moving a file to a different folder and re-scanning does not re-ingest it
- Modifying a file creates a new hash and triggers re-ingestion
- Deleting a document from the DB and re-scanning re-ingests it

---

## Source configuration

`statement_sources.py` contains `STATEMENT_SOURCES: list[StatementSource]`.

Each `StatementSource` has:
- `source_id` — stable key (e.g. "chase_freedom")
- `institution_type` — routes to the correct parser
- `account_product` — human-readable label shown in UI
- `bucket` — "investments" or "banking"
- `root_path` — absolute path to scan
- `glob_pattern` — default `"**/*.pdf"` (recurses into YYYY/)
- `filename_hints` — optional filters when multiple products share a folder

`PARSEABLE_INSTITUTION_TYPES` lists which institution_types have working parsers. Sources with other types are scanned and counted but not ingested.

---

## Query router (chat intents)

| Intent | SQL path | Example question |
|--------|----------|-----------------|
| `fee_summary` | SQL | "How much did I pay in fees?" |
| `balance_lookup` | SQL | "What's my account balance?" |
| `holdings_lookup` | SQL | "What stocks do I hold?" |
| `transaction_lookup` | SQL | "Show me transactions over $500" |
| `cash_flow_summary` | SQL | "What's my monthly spend?" |
| `document_availability` | SQL | "What documents have I uploaded?" |
| `institution_coverage` | SQL | "Which banks are connected?" |
| `statement_coverage` | SQL | "How far back do my statements go?" |
| `text_explanation` | FTS | "What does Morgan Stanley say about my advisory fees?" |
| `hybrid_financial_question` | SQL + FTS | General fallback |
