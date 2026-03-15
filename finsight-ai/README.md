# FinSight AI — Local-First Financial Intelligence

A fully private, AI-powered system for analyzing financial statements from Morgan Stanley, Chase, E*TRADE, American Express, and Discover. Every computation — parsing, extraction, embeddings, LLM inference — runs locally on your machine. Your financial data never leaves your device.

---

## Table of Contents

1. [Overview](#overview)
2. [Tech Stack](#tech-stack)
3. [Architecture Overview](#architecture-overview)
4. [Directory Structure](#directory-structure)
5. [Component Deep Dives](#component-deep-dives)
   - [Domain Layer](#1-domain-layer)
   - [Persistence Layer](#2-persistence-layer)
   - [Ingestion Pipeline (LangGraph)](#3-ingestion-pipeline-langgraph)
   - [Institution Agents](#4-institution-agents)
   - [Parsing Layer](#5-parsing-layer)
   - [RAG System](#6-rag-system)
   - [LLM & Embeddings (Ollama)](#7-llm--embeddings-ollama)
   - [Services Layer](#8-services-layer)
   - [Analytics](#9-analytics)
   - [API Layer](#10-api-layer)
   - [Frontend](#11-frontend)
   - [Configuration](#12-configuration)
6. [Data Flow Diagrams](#data-flow-diagrams)
   - [Document Ingestion](#document-ingestion-pipeline)
   - [Chat Query (RAG)](#chat-query-rag-pipeline)
7. [Database Schema](#database-schema)
8. [Prerequisites & Quick Start](#prerequisites--quick-start)
9. [Configuration Reference](#configuration-reference)
10. [Adding a New Institution](#adding-a-new-institution)
11. [Phase Roadmap](#phase-roadmap)

---

## Overview

FinSight AI ingests PDF financial statements, extracts structured data using local LLMs, stores everything in SQLite + Chroma, and lets you query your finances in plain English — all without any data leaving your machine.

**Supported institutions:**

| Institution | Statement Types |
|-------------|----------------|
| Morgan Stanley | IRA, Roth IRA, Advisory, Individual Brokerage |
| Chase | Checking, Sapphire, Freedom, United, Southwest, Ink (all credit card variants) |
| E*TRADE | Individual Brokerage (holdings, trades, balances, fees) |
| American Express | Platinum, Gold, Blue Cash, Delta, EveryDay, and more |
| Discover | it, More, Miles, Cashback Debit, and more |

**Core capabilities:**
- Upload PDFs → automatic institution detection → structured extraction
- Ask questions in natural language → answers grounded in your actual data
- Analytics dashboards for investments (portfolio value, holdings, fees) and banking (spend by category, subscriptions, merchant breakdown)
- Bucket system: group documents by purpose (INVESTMENTS vs BANKING) and scope all queries to a bucket
- Confidence scoring and review workflow for low-confidence extractions
- Merchant normalization and spend categorization (offline, rule-based)

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, Python 3.11+, asyncio |
| Orchestration | LangGraph (supervisor + institution agents) |
| Database | SQLite via SQLModel + SQLAlchemy 2 + aiosqlite |
| Vector store | Chroma (in-process, persistent) |
| LLM | qwen3:8b via Ollama |
| Embeddings | nomic-embed-text via Ollama |
| PDF parsing | pdfplumber |
| Frontend | React 18, TypeScript, Tailwind CSS, Zustand |
| API transport | REST + Server-Sent Events (SSE) for streaming |
| Caching | SQLite-backed content-addressed cache (embed + LLM + retrieval) |

---

## Architecture Overview

```
Browser (React :3000)
    │  REST + SSE
    ▼
FastAPI (:8000)
    │
    ├─ Ingestion → LangGraph pipeline → parse → classify → extract → persist → embed
    │                                                ↕ MCP tools
    │                                         Institution Agents (5)
    │
    ├─ Chat    → ChatPipeline (5-stage) → HybridRetriever (Chroma + SQLite, bucket-scoped)
    │                                  → qwen3:8b (Ollama)
    │
    └─ Analytics → InvestmentsAnalyticsService / BankingAnalyticsService → SQLite

Local Storage:
    SQLite   (statements, transactions, fees, holdings, buckets, metrics)
    Chroma   (text chunk embeddings)
    Ollama   (qwen3:8b + nomic-embed-text)
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for full Mermaid diagrams.

---

## Directory Structure

```
finsight-ai/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   └── institutions/     # One agent per institution + base + template
│   │   │       ├── base.py
│   │   │       ├── template.py
│   │   │       ├── morgan_stanley.py
│   │   │       ├── chase.py
│   │   │       ├── etrade.py
│   │   │       ├── amex.py
│   │   │       └── discover.py
│   │   ├── api/
│   │   │   ├── routes/           # FastAPI routers
│   │   │   └── schemas/          # Pydantic request/response schemas
│   │   ├── database/
│   │   │   ├── engine.py
│   │   │   ├── models.py         # All SQLModel table definitions
│   │   │   └── repositories/     # One repo per table
│   │   ├── domain/
│   │   │   ├── entities.py       # Pure domain dataclasses
│   │   │   ├── enums.py          # InstitutionType, AccountType, TransactionCategory, …
│   │   │   └── errors.py         # Typed exception hierarchy
│   │   ├── mcp_tools/
│   │   │   ├── registry.py       # Tool registration + dispatch
│   │   │   ├── contracts.py      # Typed Pydantic request/response contracts
│   │   │   ├── document_store.py # In-memory ParsedDocument store
│   │   │   └── institution_tools.py
│   │   ├── ollama/
│   │   │   ├── client.py         # Async Ollama HTTP client
│   │   │   └── model_router.py   # Task-based model routing
│   │   ├── parsers/
│   │   │   ├── base.py
│   │   │   ├── pdf_parser.py
│   │   │   ├── amex/             # classifier.py + extractor.py
│   │   │   ├── chase/
│   │   │   ├── discover/
│   │   │   ├── etrade/
│   │   │   └── morgan_stanley/
│   │   ├── rag/
│   │   │   ├── chroma_store.py   # Async Chroma wrapper
│   │   │   ├── retriever.py      # HybridRetriever (vector + SQL + bucket filter)
│   │   │   └── prompt_builder.py
│   │   ├── services/
│   │   │   ├── analytics/
│   │   │   │   ├── investments_analytics.py
│   │   │   │   └── banking_analytics.py
│   │   │   ├── chat/
│   │   │   │   ├── pipeline.py   # 5-stage ChatPipeline
│   │   │   │   ├── fallback.py
│   │   │   │   └── no_data.py
│   │   │   ├── normalization/
│   │   │   │   ├── category_rules.py
│   │   │   │   └── merchant_normalizer.py
│   │   │   ├── answer_builder.py
│   │   │   ├── bucket_service.py
│   │   │   ├── cache_service.py
│   │   │   ├── confidence_service.py
│   │   │   ├── correction_service.py
│   │   │   ├── deletion_service.py
│   │   │   ├── embedding_service.py
│   │   │   ├── event_bus.py
│   │   │   ├── ingestion_service.py
│   │   │   ├── metrics_service.py
│   │   │   ├── reconciliation_service.py
│   │   │   └── review_service.py
│   │   ├── config.py             # pydantic-settings, all env-overridable
│   │   └── main.py               # FastAPI app + lifespan
│   ├── migrations/
│   └── tests/
├── frontend/
│   └── src/
│       ├── api/                  # Typed API client functions
│       ├── components/
│       │   ├── analytics/        # BalanceTimeline, FeeChart
│       │   ├── answers/          # AnswerCard, EvidenceDrawer
│       │   ├── chat/             # ChatInterface, BucketPicker, AgentTrace, SourceCitations
│       │   ├── layout/           # Sidebar
│       │   ├── metrics/          # MetricsOverview, NetWorthChart, SpendingTrendChart
│       │   ├── statements/       # StatementList
│       │   └── upload/           # DocumentUpload, BucketSelector, EventStreamPanel
│       ├── hooks/                # useEventStream, usePipelineReducer
│       ├── pages/                # AnalyticsPage, MetricsPage
│       ├── store/                # Zustand app store
│       └── types/                # Shared TypeScript types
└── data/
    ├── chroma/                   # Chroma vector store (persistent)
    ├── db/                       # SQLite databases
    └── uploads/                  # Uploaded PDFs
```

---

## Component Deep Dives

### 1. Domain Layer

`backend/app/domain/` — pure Python, no I/O, no ORM imports.

- **`entities.py`** — dataclasses for `Statement`, `Transaction`, `Fee`, `Holding`, `BalanceSnapshot`, `EmbeddingRecord`, etc. Monetary values are `Decimal`. These are the canonical in-memory representations throughout the system.
- **`enums.py`** — all system enumerations:
  - `InstitutionType`: `morgan_stanley`, `chase`, `etrade`, `amex`, `discover`, `unknown`
  - `AccountType`: `ira`, `roth_ira`, `advisory`, `individual_brokerage`, `401k`, `checking`, `savings`, `credit_card`, `unknown`
  - `BucketType`: `investments`, `banking`
  - `TransactionCategory`: 15 values — `groceries`, `restaurants`, `subscriptions`, `travel`, `shopping`, `gas`, `utilities`, `healthcare`, `entertainment`, `education`, `insurance`, `transfers`, `fees`, `atm_cash`, `other`
  - `ConfidenceTier`: `high`, `medium`, `low`, `needs_review`
  - `StagedRecordStatus`: `extracted`, `inferred`, `needs_review`, `approved`, `corrected`, `rejected`
  - `ReconciliationStatus`: `passed`, `passed_with_warnings`, `failed`, `skipped`
- **`errors.py`** — typed exception hierarchy (`OllamaConnectionError`, `VectorStoreError`, `ExtractionError`, etc.)

### 2. Persistence Layer

`backend/app/database/` — SQLModel + SQLAlchemy 2 async.

All monetary values are stored as `TEXT` (Decimal strings) to avoid floating-point loss. The repository pattern isolates all SQL in `database/repositories/` — no raw SQL outside of those files (except for analytics aggregations and dynamically generated SQL in the retriever).

Tables: `institutions`, `accounts`, `statement_documents`, `statements`, `balance_snapshots`, `transactions`, `fees`, `holdings`, `buckets`, `bucket_documents`, `processing_events`, `derived_monthly_metrics`, `deletion_records`.

### 3. Ingestion Pipeline (LangGraph)

`backend/app/agents/supervisor.py` — a `StateGraph` with typed `IngestionState`.

```
parse_node → classify_node → route_to_institution → <institution_node>
                                                          ↓
                                                    persist_node
                                                          ↓
                                                     embed_node
                                                          ↓
                                                     report_node
```

Each node yields SSE events via the `EventBus` so the frontend can show live progress. The pipeline runs as an `asyncio.create_task` after a 202 Accepted response — the upload endpoint never blocks on parsing.

### 4. Institution Agents

`backend/app/agents/institutions/` — all five are fully implemented.

Each agent subclasses `BaseInstitutionAgent` and must implement:
- `can_handle(parsed_doc) -> float` — returns a 0–1 confidence score
- `run(state) -> IngestionState` — full extraction, returns populated state

The supervisor calls `can_handle()` on all agents, picks the highest-confidence winner, and dispatches to that agent's node. Agents use MCP tools (never direct supervisor imports) to stay decoupled.

Each agent declares `InstitutionCapabilities` — a descriptor listing which fields and statement types it can extract. The supervisor uses this for SSE trace events.

### 5. Parsing Layer

`backend/app/parsers/` — one package per institution.

Each package contains:
- `classifier.py` — pattern-matching heuristics (header text, logo strings, account number formats) to compute `can_handle` confidence without LLM
- `extractor.py` — structured extraction using `pdfplumber` tables + LLM prompts for unstructured fields

`pdf_parser.py` wraps `pdfplumber` and runs in `asyncio.to_thread()` to avoid blocking the event loop.

### 6. RAG System

`backend/app/rag/`

**`HybridRetriever`** — the core of the chat pipeline:
1. Resolves `bucket_ids → document_ids` via the `bucket_documents` join table
2. Runs semantic vector search in Chroma, filtered to those document IDs
3. If the question contains aggregation keywords ("total", "how much", "compare", …), generates and executes a SQL query against SQLite
4. Merges both result sets into a single `RetrievalResult`

**`ChromaStore`** — async wrapper over the Chroma synchronous API. All calls run in `asyncio.to_thread()`. Chunks are keyed by `{document_id}_{chunk_index}` and metadata includes `document_id`, `institution_type`, `statement_period`, `page_number`, `section`.

### 7. LLM & Embeddings (Ollama)

`backend/app/ollama/`

- **`client.py`** — async HTTP client for Ollama's `/api/generate` and `/api/embeddings` endpoints. Implements stall detection (watchdog timer) and surfaces `OllamaStalledException` if the model stops producing tokens.
- **`model_router.py`** — routes tasks to models by `TaskType`. Currently all tasks (`CHAT`, `EXTRACTION`, `CLASSIFICATION`, `ANALYSIS`, `EMBEDDING`) use the same configured models, but the router is config-driven so tasks can be split to different models without code changes.

### 8. Services Layer

`backend/app/services/`

| Service | Purpose |
|---------|---------|
| `ingestion_service.py` | Receives uploaded files, registers EventBus, spawns LangGraph task |
| `embedding_service.py` | Chunks documents, calls Ollama for embeddings, stores in Chroma |
| `bucket_service.py` | CRUD for buckets + bucket-document assignments |
| `cache_service.py` | Three-tier cache: embed (content-hash), LLM (prompt-hash), retrieval (query+bucket hash) |
| `confidence_service.py` | Converts per-field confidence scores → `ConfidenceTier`; PARTIAL caps at MEDIUM |
| `answer_builder.py` | Converts LLM prose + retrieval chunks → `StructuredAnswer` with typed sections |
| `reconciliation_service.py` | Checks extracted facts vs statement totals; emits `ReconciliationStatus` |
| `review_service.py` | Manages low-confidence items in a review queue |
| `correction_service.py` | Persists user corrections; used to improve future extraction |
| `metrics_service.py` | Computes and stores `derived_monthly_metrics` after each ingestion |
| `deletion_service.py` | Soft-deletes documents + cascades; writes `deletion_records` |
| `event_bus.py` | Per-document SSE queue; subscribers receive events until `stream_done` sentinel |

**`services/chat/`**

| Module | Purpose |
|--------|---------|
| `pipeline.py` | 5-stage ChatPipeline: retrieve → prompt → generate → fallback → cache |
| `fallback.py` | Builds retrieval-only answer when LLM times out or stalls |
| `no_data.py` | Deterministic no-data / partial-data answer builders (no LLM) |

**`services/normalization/`**

| Module | Purpose |
|--------|---------|
| `category_rules.py` | ~200 priority-ordered substring rules → `TransactionCategory` |
| `merchant_normalizer.py` | Strips POS codes / location suffixes; applies rules; LLM fallback; subscription detection |

### 9. Analytics

`backend/app/services/analytics/`

Two bucket-typed services, both returning `PartialResult[T]` (never raise HTTP 500):

**`InvestmentsAnalyticsService`** — for INVESTMENTS buckets:
- Portfolio overview (total value, account breakdown)
- Holdings table with market values
- Fee trend (advisory + management fees by month)
- Balance trend (monthly snapshots)
- Period-over-period change metrics

**`BankingAnalyticsService`** — for BANKING buckets:
- Spend summary by `TransactionCategory`
- Top merchants table
- Subscription detection (recurring charge heuristic: same merchant + amount ±$1 across 2+ months)
- Credit card balance overview
- Checking in/out summaries

Both services read primarily from `derived_monthly_metrics` for trend data (pre-aggregated at ingestion time by `MetricsService`) and fall back to live SQL aggregations when needed.

### 10. API Layer

`backend/app/api/routes/`

| Router | Key Endpoints |
|--------|--------------|
| `documents.py` | `POST /documents/upload`, `GET /documents/{id}/stream` (SSE), `DELETE /documents/{id}`, `GET /documents/` |
| `chat.py` | `POST /chat/query`, `POST /chat/stream` (SSE) |
| `statements.py` | `GET /statements/`, `GET /statements/{id}` |
| `analytics.py` | `GET /analytics/investments`, `GET /analytics/investments/portfolio`, `GET /analytics/banking`, `GET /analytics/banking/spend`, `GET /analytics/banking/subscriptions`, legacy: `/analytics/fees`, `/analytics/balances`, `/analytics/missing`, `/analytics/institutions` |
| `buckets.py` | `POST /buckets/`, `GET /buckets/`, `GET /buckets/{id}`, `PUT /buckets/{id}`, `DELETE /buckets/{id}`, `POST /buckets/{id}/documents` |
| `metrics.py` | `GET /metrics/summary`, `GET /metrics/net-worth`, `GET /metrics/spending-trend` |

All endpoints return typed Pydantic responses. Analytics endpoints return `{ data: T, warnings: string[], partial: bool }`.

### 11. Frontend

`frontend/src/`

| Area | Components |
|------|-----------|
| Upload flow | `DocumentUpload`, `BucketSelector`, `EventStreamPanel` (live SSE progress) |
| Chat | `ChatInterface` (BucketPicker + message history + streaming), `AnswerCard` (typed rendering), `EvidenceDrawer` (collapsible sources), `AgentTrace` (SSE step log), `SourceCitations` |
| Analytics | `AnalyticsPage` (investments + banking tabs), `BalanceTimeline`, `FeeChart` |
| Metrics | `MetricsPage`, `MetricsOverview`, `NetWorthChart`, `SpendingTrendChart` |
| Layout | `Sidebar` (navigation) |
| Statements | `StatementList` |

State is managed with Zustand (`appStore.ts`). The `useEventStream` hook handles SSE subscription + reconnect. `usePipelineReducer` manages the multi-stage chat pipeline state machine.

### 12. Configuration

`backend/app/config.py` — pydantic-settings, all fields env-overridable.

Key settings groups: `ollama` (host, models), `chroma` (persist dir, collection name, top-k), `database` (SQLite path), `ingestion` (chunk size, overlap), `cache` (TTL values).

---

## Data Flow Diagrams

### Document Ingestion Pipeline

```
POST /documents/upload (multipart PDF)
  │
  ├─ 202 Accepted → { document_id }
  │
  └─ asyncio.create_task(ingestion_pipeline)
         │
         ├─ parse_node
         │    pdfplumber → ParsedDocument (text + tables)
         │    event: parse_started, text_extracted
         │
         ├─ classify_node
         │    All 5 agents → can_handle() → pick winner by confidence
         │    event: institution_hypotheses
         │
         ├─ route_to_institution (conditional edge)
         │
         ├─ <institution>_node  (e.g. chase_node)
         │    classifier → confirm → extractor → Statement + Transactions + Fees + Holdings
         │    event: extraction_started_v2, fields_detected
         │
         ├─ persist_node
         │    SQLite repos → write all records
         │    MetricsService → update derived_monthly_metrics
         │    event: persist_started, persist_completed
         │
         ├─ embed_node
         │    DocumentChunker → chunks
         │    Ollama nomic-embed-text → embeddings
         │    Chroma.upsert(chunks, embeddings, metadata)
         │    event: embedding_started_v2, embedding_completed
         │
         └─ report_node
              aggregate errors, compute final status
              event: ingestion_pipeline_complete → stream_done
```

### Chat Query (RAG) Pipeline

```
POST /chat/stream  { question, bucket_ids, conversation_history }
  │
  └─ ChatPipeline.stream()
         │
         ├─ Stage 1: HybridRetriever (5s timeout)
         │    bucket_ids → SELECT document_id FROM bucket_documents WHERE bucket_id IN (...)
         │    Chroma.query(embedding, where={document_id: {$in: doc_ids}}) → chunks
         │    If aggregation keywords → LLM generates SQL → SQLite → rows
         │    event: chat_retrieve_started, chat_retrieve_done
         │
         ├─ Short-circuit check
         │    0 chunks + 0 SQL rows → deterministic no-data answer (no LLM)
         │    event: chat_no_data
         │
         ├─ Stage 2: Build prompt
         │    system prompt + retrieved context + conversation history
         │
         ├─ Stage 3: qwen3:8b generation (30s watchdog)
         │    On timeout/stall → Stage 3b: retrieval-only answer
         │    On connection error → Stage 3c: safe error message
         │    event: chat_generate_started, chat_generate_done (or chat_fallback_triggered)
         │
         ├─ Stage 4: Build StructuredAnswer
         │    answer_builder → title + highlights + sections + caveats + followups
         │
         └─ Stage 5: Cache write (fire-and-forget)
              SSE final event: response_complete
```

---

## Database Schema

```sql
institutions (id, name, institution_type, bucket_type, website, created_at)
accounts     (id, institution_id, account_number_masked, account_name, account_type,
              bucket_type, currency, created_at)
statement_documents (id, filename, file_path, file_hash, institution_type,
                     processing_status, error_message, uploaded_at, processed_at)
statements   (id, institution_id, account_id, account_type, bucket_type,
              statement_type, period_start, period_end, overall_confidence, created_at)
balance_snapshots  (id, account_id, statement_id, snapshot_date, total_value)
transactions       (id, account_id, statement_id, transaction_date, description,
                    transaction_type, amount, category, normalized_merchant)
fees               (id, account_id, statement_id, fee_date, description, amount, fee_category)
holdings           (id, account_id, statement_id, symbol, description, quantity,
                    cost_basis, market_value, unrealized_gain_loss)
buckets            (id, name, description, bucket_type, institution_type, status,
                    color, created_at, updated_at)
bucket_documents   (id, bucket_id, document_id, assigned_at)
processing_events  (id, document_id, event_type, step_name, message, status,
                    payload_json, created_at)
derived_monthly_metrics (id, account_id, year, month, metric_type, value, created_at)
deletion_records   (id, document_id, filename, deleted_at, reason)
```

All monetary columns (`amount`, `total_value`, `market_value`, `cost_basis`, `unrealized_gain_loss`) are stored as `TEXT` (Decimal strings) to avoid floating-point precision loss.

---

## Prerequisites & Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- [Ollama](https://ollama.ai) running locally

### Pull required models

```bash
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

### Backend

```bash
cd finsight-ai/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd finsight-ai/frontend
npm install
npm run dev        # starts on :3000
```

### First use

1. Open `http://localhost:3000`
2. Create a bucket (e.g., "My Investments" with type INVESTMENTS)
3. Upload a PDF statement — watch the live SSE progress panel
4. Ask a question in the chat — select your bucket in the BucketPicker first

---

## Configuration Reference

All settings are in `backend/app/config.py` and can be overridden via environment variables or a `.env` file.

| Setting | Default | Description |
|---------|---------|-------------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama base URL |
| `OLLAMA_CHAT_MODEL` | `qwen3:8b` | Model for chat generation |
| `OLLAMA_EXTRACTION_MODEL` | `qwen3:8b` | Model for PDF extraction |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Embedding model |
| `CHROMA_PERSIST_DIR` | `data/chroma` | Chroma vector store directory |
| `CHROMA_COLLECTION_NAME` | `finsight_statements` | Chroma collection name |
| `CHROMA_RETRIEVAL_TOP_K` | `6` | Number of chunks returned per query |
| `DATABASE_URL` | `sqlite+aiosqlite:///data/db/finsight.db` | SQLite path |
| `CACHE_DB_PATH` | `data/db/cache` | Cache SQLite path |
| `UPLOAD_DIR` | `data/uploads` | PDF storage directory |
| `CHUNK_SIZE` | `800` | Embedding chunk size (tokens) |
| `CHUNK_OVERLAP` | `100` | Chunk overlap (tokens) |

---

## Adding a New Institution

1. **Agent** — create `backend/app/agents/institutions/<name>.py` subclassing `BaseInstitutionAgent`. Copy `template.py`.
2. **Parser** — create `backend/app/parsers/<name>/` with `classifier.py` and `extractor.py`.
3. **Enum** — add a value to `InstitutionType` in `backend/app/domain/enums.py`.
4. **Register** — add an instance to `INSTITUTION_AGENT_REGISTRY` in `backend/app/agents/supervisor.py`.

No other files need to change. The supervisor automatically calls `can_handle()` on all registered agents.

---

## Phase Roadmap

| Phase | Feature | Status |
|-------|---------|--------|
| 1 | Morgan Stanley extraction + basic chat | Done |
| 2 | Chase + E*TRADE agents | Done |
| 2 | Amex + Discover agents | Done |
| 2 | SSE event streaming + live progress | Done |
| 2 | Structured answers + AnswerCard UI | Done |
| 2 | Bucket system (scoped documents + queries) | Done |
| 3 | Analytics: investments + banking dashboards | Done |
| 3 | Merchant normalization + spend categorization | Done |
| 3 | Confidence scoring + ConfidenceTier | Done |
| 3 | Three-tier cache service | Done |
| 3 | Reconciliation + review queue | Done |
| 3 | 5-stage chat pipeline with fallbacks | Done |
| 3 | Bucket-scoped retrieval (vector + SQL) | Done |
| 3 | Derived monthly metrics | Done |
| 4 | OCR support for scanned PDFs | Planned |
| 4 | Correction workflows + user feedback loop | Planned |
| 4 | Self-correction / retry loops in agents | Planned |
| 4 | Multi-user support | Planned |
