# Claude Code Project Guide — Coral v2

## Project Summary
Coral is a **local-first financial statement analyzer**. It parses statements from Morgan Stanley, Chase, E*TRADE, Amex, Discover, and Bank of America, stores structured data in SQLite, and answers financial questions using SQL-first query routing with FTS5 text search and optional in-SQLite vector retrieval.

Stack: FastAPI, SQLite + FTS5, SQLModel, pdfplumber, Ollama (`qwen3:8b` classification/extraction + `gemma4:latest` chat/analysis + `nomic-embed-text` embeddings), Next.js 14 (App Router), TypeScript, Tailwind, Zustand.

## Architecture (v2 — simplified)

- **No LangGraph, no MCP, no Chroma wired to any route** — `langgraph`/`chromadb` remain unused deps in `backend/pyproject.toml`; startup logs report `langgraph_wired_to_chat: False`
- SQL-first, deterministic architecture — the LLM never writes SQL and never invents numbers
- Parser plugin system with registry pattern
- Two intent systems: `ChatIntent`/`RouteType` (primary, LLM-classified) mapped to internal `QueryIntent`/`QueryPath` (what the SQL handlers key off)
- FTS5 for text search, vector embeddings stored as JSON in `text_chunks.embedding` (cosine similarity in Python, no external vector DB)
- Dedicated deterministic 7-layer pipeline for affordability questions (`chat/domains/affordability/`) — bypasses SQL, does math in Decimal, LLM only narrates a Python-computed verdict

Full pipeline diagrams and module-by-module detail: [README_ARCHITECTURE.md](README_ARCHITECTURE.md).

## Key Modules

### Backend (`backend/app/`)
- `config/__init__.py` — Pydantic settings, env-driven (`CORAL_*`); `config/statement_catalog.py` — 18-account institution/upload catalog
- `main.py` — FastAPI app factory
- `domain/` — enums (`QueryIntent`/`QueryPath`), `classification.py` (`ChatIntent`/`RouteType`), entities (Pydantic), errors
- `db/` — models (SQLModel), engine (+ idempotent column migrations), repositories, FTS5 (`fts.py`)
- `parsers/` — base interface + registry, per-institution parsers (`morgan_stanley`, `chase`, `etrade`, `amex`, `discover`, `bank_of_america`)
- `services/` — ingestion, llm, `chat_router.py` (primary chat pipeline), `query_router.py` (legacy, not live), `intent_classifier.py`, `intent_mapping.py`, `sql_query.py` (13 handlers), `text_search.py`, `vector_search.py`, `answer_builder.py`, `financial_plan.py` (versioned allocation plan, no HTTP coupling), `dashboard/`
- `chat/` — `streaming.py` (SSE), `query_planner.py`, `answer_style.py`, `fact_builder.py`, `insight_builder.py`, `answer_verifier.py`, `guardrails.py`, `retrieval.py`, `services/conversation_context.py`, `evals/`, `domains/affordability/` (7-layer pipeline)
- `api/` — documents, chat, analytics, dashboard, scan, catalog, health, financial-plan routes
- `statement_sources.py` — scanner's folder→institution map (separate from `config/statement_catalog.py`, used by structured upload)

### Frontend (`frontend-next/`)
- Next.js 14 App Router; old Vite/React `frontend/` directory is fully removed
- Routes: `/` (home), `/banking`, `/investments`, `/documents`, `/chat`, `/upload`
- Zustand (`store/appStore.ts`) for chat history + theme state
- Types mirror backend Pydantic schemas

## Non-Negotiable Rules
- Never send financial data to external APIs
- SQL is the primary source of truth, not vectors
- Prefer deterministic rules over LLM for critical finance logic
- Keep it simple — avoid introducing complexity unless clearly justified

## Parser System
Each parser implements `InstitutionParser`:
- `can_handle(text, metadata) → float` — confidence score
- `extract(document) → ParsedStatement` — structured data extraction
- `ParserRegistry.detect_institution()` auto-routes documents

Marcus and 529 are catalog-only stubs (`parseable=False`) with no parser registered yet.

## Query Router
`services/chat_router.py::route()` is the live entry point (`api/chat.py` and `chat/streaming.py` both call it). It classifies into a `ChatIntent`, builds a `RouteDecision`/`RouteType`, and dispatches:
- `RouteType.AFFORDABILITY` → `chat/domains/affordability::analyze()`, bypasses SQL entirely
- `SIMPLE_SQL` / `SQL_ANALYSIS` / most `HYBRID` → `sql_query.execute_for_intent()` (13 deterministic handlers), with a labeled relaxed-filter retry on empty results
- `DOCUMENT_SEARCH` / SQL-empty fallback → FTS5 (`text_search.py`) + vector search (`vector_search.py`)
- `CLARIFICATION` / nothing found → helpful fallback that surfaces available categories/institutions/date range, never a bare "no data"

`services/query_router.py` (regex-based, keyed on `QueryIntent` directly) still exists for backward compat but is not the code path in use.

## Database
- Canonical tables: institutions, accounts, documents, statements, transactions, fees, holdings, balance_snapshots, text_chunks, derived_metrics
- Financial Plan tables: financial_plans, financial_plan_versions, plan_allocations, plan_suballocations — the user's intended allocation, versioned/effective-dated, kept separate from actual transactions. See [FINANCIAL_PLAN_MODEL.md](docs/FINANCIAL_PLAN_MODEL.md).
- Bank-specific: morgan_stanley_details, chase_details, etrade_details, amex_details, discover_details (Bank of America has no detail table — canonical rows only)
- FTS5 virtual table: text_chunks_fts
- SQL reference: [queries.sql](queries.sql)

## Ports
- Backend: 8000
- Frontend (frontend-next): 3001
- Ollama: 11434
