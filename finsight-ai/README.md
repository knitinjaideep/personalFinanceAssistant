# FinSight AI — Local-First Financial Intelligence

A fully private, AI-powered system for analyzing financial statements from Morgan Stanley, Chase, and E*TRADE. Every computation — parsing, extraction, embeddings, LLM inference — runs locally on your machine. Your financial data never leaves your device.

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
   - [API Layer](#9-api-layer)
   - [Frontend](#10-frontend)
   - [Configuration](#11-configuration)
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

FinSight AI ingests PDF financial statements, extracts structured data (balances, transactions, fees, holdings) using a combination of regex and local LLMs, stores everything in SQLite, embeds document text in a Chroma vector store, and surfaces a hybrid RAG chat interface for natural-language financial queries.

**Core properties:**
- **100% local** — Ollama for LLM inference and embeddings, Chroma + SQLite for storage
- **Privacy-first** — zero external API calls; your data stays on disk
- **Multi-institution** — pluggable agent architecture (Morgan Stanley live, Chase/E*TRADE next)
- **Hybrid retrieval** — semantic vector search *plus* generated SQL for precise aggregations
- **Real-time feedback** — SSE event streaming during ingestion and chat

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend API | FastAPI (async) |
| ORM | SQLModel + SQLAlchemy 2 + aiosqlite |
| Agent orchestration | LangGraph |
| LLM inference | Ollama (`qwen3:8b`) |
| Embeddings | Ollama (`nomic-embed-text`) |
| Vector store | Chroma (persistent, in-process) |
| PDF parsing | pdfplumber |
| Structured logging | structlog |
| Frontend | React 18 + TypeScript + Vite |
| UI styling | Tailwind CSS |
| Global state | Zustand |
| Charts | Recharts |

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│  Browser (localhost:3000)                                     │
│  React 18 + TypeScript + Tailwind CSS + Zustand              │
│  ┌────────────┐  ┌──────────────┐  ┌───────────┐            │
│  │  Upload UI │  │   Chat UI    │  │ Analytics │            │
│  └─────┬──────┘  └──────┬───────┘  └─────┬─────┘            │
└────────┼────────────────┼────────────────┼──────────────────┘
         │  REST + SSE    │  REST + SSE    │  REST
         ▼                ▼                ▼
┌──────────────────────────────────────────────────────────────┐
│  FastAPI Backend (localhost:8000)                            │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  API Routes                                          │   │
│  │  /documents  /statements  /chat  /analytics /buckets │   │
│  └────────────────────────┬─────────────────────────────┘   │
│                           │                                  │
│          ┌────────────────┼─────────────────┐               │
│          ▼                ▼                 ▼               │
│  ┌──────────────┐  ┌────────────┐  ┌─────────────────┐     │
│  │  Ingestion   │  │    Chat    │  │   Analytics     │     │
│  │  Service     │  │  Service   │  │   Service       │     │
│  └──────┬───────┘  └─────┬──────┘  └────────┬────────┘     │
│         │                │                  │               │
│         ▼                ▼                  ▼               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  LangGraph Ingestion Graph                           │   │
│  │                                                      │   │
│  │  parse → classify → route → [institution] →         │   │
│  │  persist → embed → report                           │   │
│  │                                                      │   │
│  │  ┌──────────────────┐  ┌───────┐  ┌──────────────┐ │   │
│  │  │ MorganStanleyAgent│  │Chase  │  │ ETradeAgent  │ │   │
│  │  │  (implemented)   │  │(stub) │  │   (stub)     │ │   │
│  │  └──────────────────┘  └───────┘  └──────────────┘ │   │
│  └──────────────────────────────────────────────────────┘   │
│                           │                                  │
│          ┌────────────────┼─────────────────┐               │
│          ▼                ▼                 ▼               │
│  ┌──────────────┐  ┌────────────┐  ┌─────────────────┐     │
│  │    SQLite    │  │   Chroma   │  │     Ollama      │     │
│  │  (SQLModel)  │  │  (vectors) │  │  qwen3:8b       │     │
│  │              │  │            │  │  nomic-embed-   │     │
│  │  Structured  │  │  Semantic  │  │  text           │     │
│  │  financial   │  │  document  │  │                 │     │
│  │  data        │  │  search    │  │  localhost:11434│     │
│  └──────────────┘  └────────────┘  └─────────────────┘     │
└──────────────────────────────────────────────────────────────┘
         │                  │
         ▼                  ▼
   data/db/             data/chroma/        data/uploads/
   finsight.db          (persistent)        {uuid}.pdf
```

---

## Directory Structure

```
finsight-ai/
├── backend/
│   ├── app/
│   │   ├── main.py                   # FastAPI app factory + lifespan
│   │   ├── config.py                 # Pydantic-settings (all env-overridable)
│   │   ├── logging_config.py         # structlog setup
│   │   │
│   │   ├── domain/                   # Pure business logic — no I/O
│   │   │   ├── entities.py           # Pydantic domain models
│   │   │   ├── enums.py              # All enumerations
│   │   │   └── errors.py             # Typed exception hierarchy
│   │   │
│   │   ├── database/                 # Persistence layer
│   │   │   ├── engine.py             # Async SQLAlchemy engine + session factory
│   │   │   ├── models.py             # SQLModel ORM table definitions
│   │   │   └── repositories/
│   │   │       ├── statement_repo.py
│   │   │       └── account_repo.py
│   │   │
│   │   ├── agents/                   # LangGraph orchestration
│   │   │   ├── supervisor.py         # Ingestion graph (nodes + edges)
│   │   │   ├── state.py              # IngestionState + ChatState TypedDicts
│   │   │   └── institutions/
│   │   │       ├── base.py           # BaseInstitutionAgent ABC
│   │   │       ├── morgan_stanley.py # Full implementation
│   │   │       ├── chase.py          # Stub (Phase 2)
│   │   │       └── etrade.py         # Stub (Phase 2)
│   │   │
│   │   ├── parsers/                  # PDF → structured data
│   │   │   ├── base.py               # ParsedDocument, ParsedPage, BaseParser ABC
│   │   │   ├── pdf_parser.py         # pdfplumber implementation
│   │   │   └── morgan_stanley/
│   │   │       ├── classifier.py     # Regex + LLM institution detection
│   │   │       └── extractor.py      # Regex + LLM field extraction
│   │   │
│   │   ├── rag/                      # Retrieval-augmented generation
│   │   │   ├── chroma_store.py       # Async Chroma wrapper
│   │   │   ├── chunker.py            # Section-aware document chunking
│   │   │   ├── retriever.py          # Hybrid vector + SQL retrieval
│   │   │   └── prompt_builder.py     # RAG prompt assembly
│   │   │
│   │   ├── services/                 # Application services (orchestration)
│   │   │   ├── ingestion_service.py  # Upload validation + background processing
│   │   │   ├── chat_service.py       # RAG-powered Q&A
│   │   │   ├── embedding_service.py  # Chunk + embed into Chroma
│   │   │   └── analytics_service.py  # Fee + balance queries
│   │   │
│   │   ├── ollama/                   # Local LLM client
│   │   │   ├── client.py             # Async HTTP client + retry logic
│   │   │   └── model_router.py       # Task → Model routing (config-driven)
│   │   │
│   │   ├── mcp_tools/                # Pluggable agent tools
│   │   │   ├── registry.py           # MCPTool base + registry
│   │   │   ├── ingest_tool.py
│   │   │   ├── rag_query_tool.py
│   │   │   ├── fee_analysis_tool.py
│   │   │   └── report_tool.py
│   │   │
│   │   └── api/                      # HTTP interface
│   │       ├── deps.py               # FastAPI dependency providers
│   │       └── routes/
│   │           ├── statements.py
│   │           ├── analytics.py
│   │           └── (documents, chat, buckets)
│   │
│   ├── run.py                        # Dev server entry point
│   └── pyproject.toml
│
├── frontend/
│   └── src/
│       ├── App.tsx                   # Root router
│       ├── main.tsx                  # React entry point
│       ├── components/
│       │   ├── layout/Sidebar.tsx
│       │   ├── upload/
│       │   │   ├── DocumentUpload.tsx
│       │   │   ├── BucketSelector.tsx
│       │   │   └── EventStreamPanel.tsx
│       │   ├── chat/
│       │   │   ├── ChatInterface.tsx
│       │   │   ├── AgentTrace.tsx
│       │   │   ├── SourceCitations.tsx
│       │   │   └── BucketPicker.tsx
│       │   ├── statements/StatementList.tsx
│       │   └── analytics/
│       │       ├── FeeChart.tsx
│       │       └── BalanceTimeline.tsx
│       ├── hooks/
│       │   ├── useChat.ts
│       │   ├── useDocuments.ts
│       │   ├── useBuckets.ts
│       │   └── useEventStream.ts
│       ├── api/                      # Typed API client modules
│       ├── store/appStore.ts         # Zustand global state
│       └── types/index.ts
│
├── data/
│   ├── uploads/                      # Uploaded PDFs (UUID-named)
│   ├── db/finsight.db                # SQLite database
│   └── chroma/                       # Chroma vector store persistence
│
└── .env.example
```

---

## Component Deep Dives

### 1. Domain Layer

**Location:** `backend/app/domain/`

The domain layer contains pure Pydantic models with no I/O, database, or HTTP dependencies. It defines the canonical shape of all business objects.

#### Entities (`entities.py`)

| Entity | Purpose | Key Fields |
|--------|---------|-----------|
| `StatementDocument` | Raw uploaded file | `id`, `original_filename`, `file_path`, `document_status` |
| `Statement` | Parsed financial statement | `id`, `document_id`, `institution_id`, `account_id`, `statement_type`, `period`, `transactions[]`, `fees[]`, `holdings[]`, `balance_snapshots[]` |
| `Transaction` | Single transaction line | `transaction_date`, `description`, `amount (Decimal)`, `transaction_type` |
| `Fee` | Extracted fee record | `fee_date`, `amount (Decimal)`, `fee_category`, `annualized_rate` |
| `Holding` | Security/asset holding | `symbol`, `quantity`, `market_value`, `cost_basis`, `unrealized_gain_loss` |
| `BalanceSnapshot` | Point-in-time balance | `snapshot_date`, `total_value`, `cash_value`, `invested_value` |
| `ExtractionResult` | Agent output envelope | `document_id`, `institution_type`, `statement`, `status`, `overall_confidence`, `field_confidences` |
| `EmbeddingRecord` | Chroma chunk metadata | `document_id`, `chunk_index`, `page_number`, `section` |
| `Bucket` | Document workspace/scope | `id`, `name`, `institution_type`, `document_count` |
| `ProcessingEvent` | SSE event payload | `event_type`, `status`, `message`, `progress` |

**Key design patterns:**
- **Monetary values** — all `Decimal` in domain models, stored as `TEXT` strings in SQLite (no float precision loss)
- **`ConfidenceField[T]`** — wraps any extracted value with a `0.0–1.0` confidence score for auditability
- **`SourceLocation`** — carries `page_number`, `section`, `raw_text` for each extracted value, enabling source attribution in the chat UI

#### Enums (`enums.py`)

```
InstitutionType:     MORGAN_STANLEY | CHASE | ETRADE | UNKNOWN
StatementType:       BROKERAGE | BANK | CREDIT_CARD | RETIREMENT | ADVISORY | UNKNOWN
AccountType:         BROKERAGE | CHECKING | SAVINGS | IRA | ROTH_IRA | 401K | ADVISORY | ...
TransactionType:     DEPOSIT | WITHDRAWAL | TRADE_BUY | TRADE_SELL | FEE | DIVIDEND | ADVISORY_FEE | ...
ExtractionStatus:    PENDING | PROCESSING | SUCCESS | PARTIAL | FAILED
DocumentStatus:      UPLOADED | QUEUED | PROCESSING | PARSED | EMBEDDED | PROCESSED | FAILED | DELETED
BucketStatus:        ACTIVE | ARCHIVED | DELETED
ProcessingEventType: FILE_RECEIVED | PARSING_STARTED | CLASSIFICATION_COMPLETE |
                     EXTRACTION_STARTED | EMBEDDING_COMPLETE | INGESTION_COMPLETE | ...
```

#### Error Hierarchy (`errors.py`)

```
FinSightError
├── DocumentIngestionError
│   ├── UnsupportedFileTypeError
│   └── FileTooLargeError
├── DocumentParseError
│   └── PageExtractionError
├── ClassificationError
├── ExtractionError
├── NormalizationError
├── OllamaConnectionError
├── OllamaModelNotFoundError
├── LLMResponseParseError
├── VectorStoreError
└── RepositoryError
    └── EntityNotFoundError
```

---

### 2. Persistence Layer

**Location:** `backend/app/database/`

#### ORM Models (`models.py`)

Built with **SQLModel** (unified SQLAlchemy + Pydantic). All UUIDs stored as strings (SQLite has no native UUID type). All monetary amounts stored as `TEXT` (Decimal strings).

| Table | Primary Relationships | Notes |
|-------|-----------------------|-------|
| `institutions` | parent of `accounts` | Indexed on `name` |
| `accounts` | child of `institutions`, parent of transactions/fees/holdings | Indexed on `institution_id` |
| `statement_documents` | standalone (upload record) | Tracks file path, mime type, status, error message |
| `statements` | child of `documents`, `institutions`, `accounts` | Stores extraction status + confidence |
| `balance_snapshots` | child of `accounts`, `statements` | Indexed on `snapshot_date` |
| `transactions` | child of `accounts`, `statements` | Indexed on `transaction_date`, `symbol` |
| `fees` | child of `accounts`, `statements` | Indexed on `fee_date`, `fee_category` |
| `holdings` | child of `accounts`, `statements` | Indexed on `symbol` |
| `buckets` | standalone | Document workspace scoping |
| `bucket_documents` | join table: `buckets` ↔ `statement_documents` | Many-to-many |
| `processing_events` | references `documents`, `buckets` | Full audit trail, indexed on `session_id` |
| `deletion_records` | references deleted `document_id` | Stores JSON list of removed embedding IDs + SQL rows |

All tables use **status columns** rather than hard deletes (soft-delete pattern).

#### Engine (`engine.py`)

```python
# Async engine, created once at startup
_engine: AsyncEngine = create_async_engine("sqlite+aiosqlite:///data/db/finsight.db")

async def init_db()            # Creates all tables via SQLModel.metadata.create_all()
async def get_session()        # Async context manager (used in services)
async def get_db_session()     # FastAPI dependency (yield-based)
```

#### Repositories (`repositories/`)

Each repository provides a clean data-access interface with no raw SQL in services:
- `create(entity)` / `get_or_create(entity)`
- `get_by_id(id)` / `list_by_filter(**kwargs)`
- `update_status(id, status)`

---

### 3. Ingestion Pipeline (LangGraph)

**Location:** `backend/app/agents/supervisor.py`

The ingestion pipeline is a **LangGraph directed graph** where each node is an async function that reads from and writes to a shared `IngestionState` TypedDict.

```
START
  │
  ▼
[parse_node]
  PDFParser.parse(file_path)
  → ParsedDocument { pages: [ParsedPage { raw_text, tables }] }
  │
  ▼
[classify_node]
  For each agent in INSTITUTION_AGENT_REGISTRY:
    (can_handle, confidence) = await agent.can_handle(parsed_document)
  Select agent with highest confidence
  → state.institution_type, state.classification_confidence
  │
  ▼
[route_node]  ← conditional edge
  │
  ├──► [morgan_stanley_node]   → MorganStanleyAgent.extract()
  ├──► [chase_node]            → ChaseAgent.extract()
  ├──► [etrade_node]           → ETradeAgent.extract()
  └──► [unknown_node]          → Log + mark FAILED
  │
  ▼
[persist_node]
  Write Statement + nested entities to SQLite via repositories
  Update document status → PROCESSED (or PARTIALLY_PARSED)
  │
  ▼
[embed_node]
  EmbeddingService.embed_document(parsed_document)
  → DocumentChunker.chunk() → chunks
  → ModelRouter.embed_batch() → Ollama vectors
  → ChromaStore.add_chunks() → persist to Chroma
  │
  ▼
[report_node]
  Log extraction summary + finalize IngestionState
  │
  ▼
END
```

**Error handling:** Errors append to `state["errors"]` but do not crash the graph. The pipeline attempts each subsequent node regardless, ensuring partial results are always persisted.

**State shape (`state.py`):**
```python
class IngestionState(TypedDict):
    document_id: str
    file_path: str
    original_filename: str
    document: StatementDocument
    parsed_document: ParsedDocument
    institution_type: InstitutionType
    statement_type: StatementType
    classification_confidence: float
    extraction_result: ExtractionResult
    errors: list[str]
    warnings: list[str]
    document_status: str
    page_count: int

class ChatState(TypedDict):
    question: str
    conversation_history: list[dict]
    retrieved_chunks: list[str]
    sql_results: list[dict]
    sql_query: str | None
    answer: str
    source_ids: list[str]
```

---

### 4. Institution Agents

**Location:** `backend/app/agents/institutions/`

#### Abstract Base (`base.py`)

```python
class BaseInstitutionAgent(ABC):
    @property
    @abstractmethod
    def institution_type(self) -> InstitutionType: ...

    @abstractmethod
    async def can_handle(
        self, document: ParsedDocument
    ) -> tuple[bool, float]: ...          # (matches, confidence 0–1)

    @abstractmethod
    async def extract(
        self, document: ParsedDocument, state: IngestionState
    ) -> ExtractionResult: ...

    async def run(self, state: IngestionState) -> IngestionState:
        # LangGraph node wrapper with error handling + timing
```

#### Morgan Stanley Agent (`morgan_stanley.py`)

1. `can_handle()` → delegates to `MorganStanleyClassifier.is_morgan_stanley()`
2. `extract()`:
   - Calls `classifier.classify_statement_type()` to determine sub-type (brokerage, advisory, retirement)
   - Calls `MorganStanleyExtractor.extract(document, statement_type)`
   - Wraps output in `ExtractionResult` with confidence scoring
3. Measures total extraction time, included in result metadata

#### Registry in `supervisor.py`

```python
INSTITUTION_AGENT_REGISTRY: list[BaseInstitutionAgent] = [
    MorganStanleyAgent(),
    ChaseAgent(),       # stub
    ETradeAgent(),      # stub
]
```

Adding a new institution requires only adding an entry here — the `classify_node` iterates the registry automatically.

---

### 5. Parsing Layer

**Location:** `backend/app/parsers/`

#### PDF Parser (`pdf_parser.py`)

- Uses **pdfplumber** for both text and table extraction
- Table strategy: `vertical_strategy: "lines"` first, fallback to `"text"` strategy
- Text extraction: layout-preserving with tolerance settings for columnar PDFs
- **CPU-bound** work runs via `asyncio.to_thread()` to avoid blocking the event loop
- Single-page errors are caught and logged; the rest of the document still processes
- Auto-detects table headers via heuristic (short, non-numeric top row)

#### Morgan Stanley Classifier (`morgan_stanley/classifier.py`)

**Two-pass strategy:**

| Pass | Mechanism | Confidence |
|------|-----------|-----------|
| Fast (regex) | Scan first 3 pages for `"morgan stanley"` pattern | 2+ matches → 0.95, 1 match → 0.75 |
| LLM fallback | If regex confidence < threshold, ask `qwen3:8b` with JSON format | 0.5–0.9 |

Also classifies statement sub-type (brokerage, advisory, retirement) using keyword matching on page text.

#### Morgan Stanley Extractor (`morgan_stanley/extractor.py`)

**Hybrid regex + LLM extraction:**

| Field Category | Method | Example Pattern |
|----------------|--------|-----------------|
| Statement period | Regex | `"For the period (\w+ \d+, \d{4}) to (\w+ \d+, \d{4})"` |
| Dollar amounts | Regex | `\$[\d,]+\.?\d*` or `\([\d,]+\.?\d*\)` for negatives |
| Account numbers | Regex | Masked formats like `XXX-1234` |
| Dates | Regex | `January 31, 2026`, `01/31/2026`, `2026-01-31` |
| Fees | Regex + LLM | Keyword match → LLM to extract amount and category |
| Holdings table | pdfplumber table + Regex | Row-by-row parsing of holdings grids |
| Narrative sections | LLM | Free-text passages describing account activity |

Each extracted value is wrapped in `ConfidenceField` with a `SourceLocation` (page number, section name, raw text snippet).

---

### 6. RAG System

**Location:** `backend/app/rag/`

#### Chunker (`chunker.py`)

**Section-aware chunking strategy:**

1. Identify logical section boundaries using header patterns (e.g., "Account Summary", "Holdings", "Transaction History", "Fees and Charges")
2. Within each section, apply a sliding window with overlap
3. Tables are converted to pipe-delimited text and tagged as `[TABLE]`

| Parameter | Default | Notes |
|-----------|---------|-------|
| `chunk_size` | 1500 chars | ~400–600 tokens for nomic-embed-text |
| `chunk_overlap` | 200 chars | Context continuity across chunk boundaries |

**Metadata per chunk:**
```python
{
    "document_id": str,
    "statement_id": str | None,
    "chunk_index": int,
    "page_number": int,
    "section": str | None,          # e.g. "holdings", "fees"
    "institution_type": str,
    "statement_period": str | None  # "2026-01-01/2026-01-31"
}
```

#### Chroma Store (`chroma_store.py`)

Async wrapper over `chromadb` (persistent SQLite backend at `data/chroma/`). All Chroma calls run via `asyncio.to_thread()` since chromadb is not async-safe.

| Operation | Signature |
|-----------|-----------|
| `initialize()` | Connect or create persistent collection |
| `add_chunks(ids, embeddings, texts, metadatas)` | Upsert batch |
| `query(embedding, n_results, where?)` | ANN search with optional metadata filter |
| `delete_by_document(document_id)` | Remove all chunks for a document |
| `count()` | Total chunks in collection |

#### Hybrid Retriever (`retriever.py`)

Combines vector search (semantic) and SQL (aggregation) for each query:

```
Query: "How much did I pay in advisory fees in Q4 2025?"
  │
  ├─► Vector search
  │     embed(question) → top-6 nearest chunks from Chroma
  │     → document excerpts with source metadata
  │
  ├─► SQL decision
  │     Regex check: contains "how much|total|fees|compare|trend" → yes
  │
  ├─► SQL generation
  │     LLM: "Generate a safe SELECT query for: {question}"
  │     Constraints: SELECT-only, LIMIT 100, no subqueries
  │
  ├─► SQL execution
  │     SQLAlchemy execute(generated_sql) → rows
  │
  └─► Format context
        "=== Document Excerpts ===\n" + chunks
        "=== Database Results ===\n" + rows
```

**SQL trigger keywords:** `how much`, `total`, `sum`, `average`, `compare`, `highest`, `lowest`, `which month`, `fees`, `trend`

#### Prompt Builder (`prompt_builder.py`)

```
SYSTEM: You are FinSight AI, a private financial intelligence assistant.
        - Answer ONLY based on provided context
        - If context lacks info, say so explicitly
        - Use bullet points for lists
        - Cite sources (institution, period, page)
        - Never fabricate figures

CONTEXT:
  === Document Excerpts ===
  [vector search results]

  === Database Results ===
  [SQL query results]

HISTORY:
  [last 4 conversation turns]

USER: {question}

INSTRUCTION: Answer using only the context above.
```

---

### 7. LLM & Embeddings (Ollama)

**Location:** `backend/app/ollama/`

#### Async Client (`client.py`)

Thin async wrapper over the official `ollama` Python SDK:

| Method | Purpose |
|--------|---------|
| `generate(model, prompt, system, temperature, num_ctx, format)` | Text completion with configurable params |
| `embed(model, text)` | Single embedding vector |
| `embed_batch(model, texts)` | Concurrent batch embedding |
| `list_models()` | Enumerate available models |
| `health_check()` | Verify Ollama is running |

**Retry strategy:** Exponential backoff, max 3 attempts on transient network errors.

**Error mapping:**
- `asyncio.TimeoutError` → `OllamaConnectionError`
- HTTP 404 (model not found) → `OllamaModelNotFoundError`
- Other HTTP errors → `OllamaConnectionError` with context

#### Model Router (`model_router.py`)

Decouples task type from model selection. All defaults point to `qwen3:8b` but are fully config-overridable per environment:

```python
class TaskType(Enum):
    CLASSIFICATION  # → settings.ollama.classification_model
    EXTRACTION      # → settings.ollama.extraction_model
    ANALYSIS        # → settings.ollama.analysis_model
    CHAT            # → settings.ollama.chat_model
    EMBEDDING       # → settings.ollama.embedding_model (nomic-embed-text)

class ModelRouter:
    def model_for(task: TaskType) -> str
    async def generate(task, prompt, system?, format?) -> str
    async def embed(text) -> list[float]
    async def embed_batch(texts) -> list[list[float]]
```

This means you can swap, e.g., the extraction model to `mistral:7b` via `.env` with zero code changes.

---

### 8. Services Layer

**Location:** `backend/app/services/`

Services are the primary orchestration layer, invoked by API routes. They hold no HTTP context and are individually testable.

#### Ingestion Service (`ingestion_service.py`)

```
HTTP request arrives → ingest_upload()
  1. Validate file type (.pdf / .csv) and size (≤ 50 MB)
  2. Store to data/uploads/{uuid}.pdf  (prevents path traversal + collisions)
  3. Create StatementDocument record in SQLite (status=UPLOADED)
  4. Fire-and-forget: asyncio.create_task(_process_document(...))
  5. Return DocumentUploadResponse immediately (non-blocking)

Background: _process_document()
  1. Update status → PROCESSING
  2. Build IngestionState
  3. ingestion_graph.ainvoke(state)
  4. Catch all errors (HTTP response already sent)
```

#### Chat Service (`chat_service.py`)

```
answer(request: ChatRequest) → ChatResponse
  1. HybridRetriever.retrieve(question, bucket_ids?)
  2. PromptBuilder.build_chat_prompt(question, context, history)
  3. ModelRouter.generate(task=CHAT, prompt, system)
  4. Build EmbeddingRecord sources from chunk metadata
  5. Return { answer, sources, sql_query_used, processing_time_seconds }
```

#### Embedding Service (`embedding_service.py`)

```
embed_document(document, document_id, statement_id, institution_type)
  1. DocumentChunker.chunk(document) → chunks[]
  2. ModelRouter.embed_batch(chunk.texts) → embeddings[]
     (runs 4 at a time via asyncio.gather with semaphore)
  3. Prepare metadata for each chunk
  4. ChromaStore.add_chunks(ids, embeddings, texts, metadatas)
  5. Return chunk_count
```

#### Analytics Service (`analytics_service.py`)

Provides pre-built analytical queries:
- Total fees by category and time period
- Balance trend per account
- Fee anomaly detection (month-over-month comparison)
- Holdings allocation breakdown

---

### 9. API Layer

**Location:** `backend/app/api/`

#### App Factory (`main.py`)

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()              # Create all SQLite tables
    await chroma_store.initialize()  # Connect Chroma collection
    app.state.chroma = chroma_store  # Available via request.app.state
    yield
    logger.info("shutdown")

app = create_app()
# Routers mounted at /api/v1/:
#   /documents   /statements   /chat   /analytics   /buckets
# Health check: GET /health
# CORS: allow localhost:3000
```

#### Key Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/documents/upload` | Upload PDF; returns `document_id` immediately; processes async |
| `GET` | `/api/v1/documents/` | List uploaded documents with status |
| `DELETE` | `/api/v1/documents/{id}` | Soft-delete + remove Chroma embeddings |
| `GET` | `/api/v1/statements/` | List parsed statements |
| `GET` | `/api/v1/statements/{id}/fees` | Fees for a statement |
| `GET` | `/api/v1/statements/{id}/holdings` | Holdings for a statement |
| `POST` | `/api/v1/chat/query` | Synchronous RAG query → `ChatResponse` |
| `POST` | `/api/v1/chat/stream` | SSE RAG stream → events + final answer |
| `GET` | `/api/v1/analytics/fees` | Fee aggregations with time filters |
| `GET` | `/api/v1/analytics/balances` | Balance timeline per account |
| `GET/POST/DELETE` | `/api/v1/buckets/` | Bucket CRUD |

#### SSE Events (Chat Stream)

```
event: supervisor_routing     {"message": "Selecting retrieval strategy..."}
event: retrieval_started      {"message": "Searching document embeddings..."}
event: retrieval_complete     {"chunks_found": 6, "sql_used": true}
event: generating_response    {"message": "Generating answer with qwen3:8b..."}
event: response_complete      {"answer": "...", "sources": [...], "sql_query": "..."}
```

---

### 10. Frontend

**Location:** `frontend/src/`

#### Pages & Components

| Component | Route | Purpose |
|-----------|-------|---------|
| `DocumentUpload` | `/upload` | Dropzone + bucket assignment + SSE event stream panel |
| `StatementList` | `/statements` | Table of all parsed statements with status and confidence |
| `ChatInterface` | `/chat` | Q&A input + conversation history + source citations |
| `FeeChart` | `/analytics` | Recharts bar chart of fees over time |
| `BalanceTimeline` | `/analytics` | Recharts line chart of balance history |
| `AgentTrace` | (chat panel) | Real-time SSE event log showing agent decisions |
| `SourceCitations` | (chat panel) | Vector chunk excerpts with institution + period + page |

#### Global State (Zustand)

```typescript
interface AppStore {
    activePage: "upload" | "statements" | "chat" | "analytics"
    buckets: Bucket[]
    selectedBucket: Bucket | null
    // setters...
}
```

#### Custom Hooks

| Hook | Purpose |
|------|---------|
| `useChat(question, bucketIds?)` | POST to `/chat/query`, returns `ChatResponse` |
| `useDocuments()` | List + upload + delete documents |
| `useBuckets()` | Full CRUD for bucket management |
| `useEventStream(sessionId)` | Open SSE connection, parse and dispatch events |

---

### 11. Configuration

**Location:** `backend/app/config.py`

Pydantic-settings with nested config groups. Every field is overridable via environment variable or `.env` file.

```python
class Settings:
    app_name: str = "FinSight AI"
    environment: Literal["development", "production", "test"] = "development"
    debug: bool = True
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:3000"]

    ollama: OllamaModelConfig
    database: DatabaseConfig
    chroma: ChromaConfig
    storage: StorageConfig

class OllamaModelConfig:
    base_url: str = "http://localhost:11434"
    classification_model: str = "qwen3:8b"
    extraction_model: str = "qwen3:8b"
    analysis_model: str = "qwen3:8b"
    chat_model: str = "qwen3:8b"
    embedding_model: str = "nomic-embed-text"
    temperature: float = 0.1
    num_ctx: int = 8192
    timeout_seconds: int = 120

class DatabaseConfig:
    path: str = "data/db/finsight.db"
    echo_sql: bool = False

class ChromaConfig:
    persist_directory: str = "data/chroma"
    collection_name: str = "finsight_statements"
    retrieval_top_k: int = 6

class StorageConfig:
    uploads_directory: str = "data/uploads"
    max_file_size_mb: int = 50
    allowed_extensions: list[str] = [".pdf", ".csv"]
```

**Environment variable naming:** `FINSIGHT_<GROUP>_<FIELD>` (e.g., `FINSIGHT_OLLAMA_CHAT_MODEL`, `FINSIGHT_CHROMA_RETRIEVAL_TOP_K`)

---

## Data Flow Diagrams

### Document Ingestion Pipeline

```
User drops PDF in browser
        │
        ▼
POST /api/v1/documents/upload
        │
        ▼
IngestionService.ingest_upload()
  ├─ Validate: type=PDF, size≤50MB
  ├─ Write to data/uploads/{uuid}.pdf
  ├─ INSERT statement_documents (status=UPLOADED)
  ├─ asyncio.create_task(_process_document())   ← background
  └─ Return { document_id, status="queued" }   ← immediate HTTP response
        │
        ▼  (background)
ingestion_graph.ainvoke(IngestionState)
        │
        ├─► parse_node
        │     PDFParser.parse() → ParsedDocument
        │     (runs in thread pool via asyncio.to_thread)
        │
        ├─► classify_node
        │     agent.can_handle() for each in registry
        │     → select highest-confidence agent
        │
        ├─► route_node (conditional edge)
        │     → morgan_stanley_node
        │
        ├─► morgan_stanley_node
        │     MorganStanleyClassifier → statement type
        │     MorganStanleyExtractor  → Statement entity
        │       ├─ Regex: dates, amounts, account numbers
        │       └─ LLM (qwen3:8b): narrative sections, fee categories
        │
        ├─► persist_node
        │     INSERT: statement, transactions, fees, holdings, balance_snapshots
        │     UPDATE: document status → PROCESSED
        │
        ├─► embed_node
        │     DocumentChunker.chunk(parsed_document)
        │     OllamaClient.embed_batch(chunk_texts)   ← nomic-embed-text
        │     ChromaStore.add_chunks(embeddings, metadata)
        │
        └─► report_node
              Log: extraction confidence, chunk count, elapsed time
```

### Chat Query (RAG Pipeline)

```
User types: "How much did I pay in advisory fees in 2025?"
        │
        ▼
POST /api/v1/chat/query   (or /chat/stream for SSE)
        │
        ▼
ChatService.answer(request)
        │
        ├─► HybridRetriever.retrieve(question)
        │     │
        │     ├─► Vector search
        │     │     OllamaClient.embed(question)          → 768-dim vector
        │     │     ChromaStore.query(embedding, k=6)     → top-6 chunks
        │     │     (with optional where={"bucket_id": ...} filter)
        │     │
        │     ├─► SQL decision
        │     │     regex match: "how much|fees|total" → true
        │     │
        │     ├─► SQL generation
        │     │     LLM: "Generate SELECT query for: {question}"
        │     │     → SELECT strftime('%Y', fee_date), SUM(CAST(amount AS REAL))
        │     │          FROM fees WHERE ...
        │     │
        │     └─► SQL execution
        │           SQLAlchemy execute(sql) → [{"2025": 4823.50}]
        │
        ├─► PromptBuilder.build_chat_prompt()
        │     System: "FinSight AI rules..."
        │     Context: vector excerpts + SQL rows
        │     History: last 4 turns
        │     User: question
        │
        ├─► ModelRouter.generate(task=CHAT, prompt)
        │     OllamaClient.generate(model="qwen3:8b", ...)
        │     → "In 2025, you paid $4,823.50 in advisory fees across..."
        │
        └─► Return ChatResponse
              { answer, sources: [EmbeddingRecord], sql_query, processing_time }
```

---

## Database Schema

```sql
-- Core document tracking
statement_documents (id TEXT PK, original_filename, stored_filename,
                     file_path, file_size_bytes, mime_type, institution_type,
                     document_status, page_count, upload_timestamp, error_message)

-- Institution + account hierarchy
institutions (id TEXT PK, name TEXT IDX, institution_type, website, created_at)
accounts     (id TEXT PK, institution_id FK IDX, account_number_masked,
              account_type, currency, created_at)

-- Parsed statement records
statements (id TEXT PK, document_id FK IDX, institution_id FK, account_id FK,
            statement_type, period_start, period_end, currency,
            extraction_status, overall_confidence, extraction_notes JSON,
            created_at, updated_at)

-- Financial data (all amounts stored as TEXT/Decimal)
balance_snapshots (id PK, account_id FK IDX, statement_id FK, snapshot_date IDX,
                   total_value TEXT, cash_value TEXT, invested_value TEXT,
                   unrealized_gain_loss TEXT, currency, confidence,
                   source_page, source_section)

transactions (id PK, account_id FK IDX, statement_id FK, transaction_date IDX,
              description, transaction_type, amount TEXT, currency,
              quantity TEXT, price_per_unit TEXT, symbol IDX,
              confidence, source_page, source_section)

fees (id PK, account_id FK IDX, statement_id FK, fee_date IDX,
      description, amount TEXT, fee_category IDX, annualized_rate TEXT,
      currency, confidence, source_page, source_section)

holdings (id PK, account_id FK IDX, statement_id FK, symbol IDX,
          description, quantity TEXT, price TEXT, market_value TEXT,
          cost_basis TEXT, unrealized_gain_loss TEXT, percent_of_portfolio TEXT,
          asset_class, currency, confidence, source_page, source_section)

-- Bucket / workspace scoping
buckets          (id PK, name IDX, description, institution_type, status,
                  color, icon, document_count, created_at, updated_at)
bucket_documents (id PK, bucket_id FK IDX, document_id FK, assigned_at)

-- Audit + events
processing_events (id PK, session_id IDX, event_type, status, agent_name,
                   step_name, message, bucket_id, document_id, progress,
                   metadata_json, timestamp)

deletion_records  (id PK, document_id IDX, original_filename, deleted_at,
                   deleted_by, bucket_ids_removed JSON, embedding_ids_removed,
                   sql_rows_json)
```

---

## Prerequisites & Quick Start

### Requirements

| Dependency | Version | Install |
|------------|---------|---------|
| Python | 3.11+ | `brew install python@3.11` |
| Node.js | 20+ | `brew install node` |
| Ollama | latest | [ollama.ai](https://ollama.ai) |

### 1. Pull Ollama Models

```bash
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

### 2. Backend

```bash
cd finsight-ai/backend

python3.11 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -e ".[dev]"

cp ../.env.example .env          # Edit as needed

python run.py
# → Listening on http://localhost:8000
# → API docs: http://localhost:8000/docs
```

### 3. Frontend

```bash
cd finsight-ai/frontend

npm install
npm run dev
# → http://localhost:3000
```

### Usage

1. Open `http://localhost:3000`
2. **Upload** — drag and drop a Morgan Stanley PDF statement
3. Watch real-time processing events (parse → classify → extract → embed)
4. **Chat** — ask natural language questions:
   - *"How much did I pay in advisory fees last year?"*
   - *"Did my portfolio balance increase in Q4?"*
   - *"Show all transactions over $10,000."*
   - *"Compare my fees month-over-month for 2025."*
5. **Analytics** — view fee breakdown charts and balance timeline

---

## Configuration Reference

All settings live in `.env` (copied from `.env.example`):

```bash
# Environment
FINSIGHT_ENVIRONMENT=development
FINSIGHT_DEBUG=true
FINSIGHT_LOG_LEVEL=INFO

# Ollama (all default to qwen3:8b except embedding)
FINSIGHT_OLLAMA_BASE_URL=http://localhost:11434
FINSIGHT_OLLAMA_CHAT_MODEL=qwen3:8b
FINSIGHT_OLLAMA_EXTRACTION_MODEL=qwen3:8b
FINSIGHT_OLLAMA_CLASSIFICATION_MODEL=qwen3:8b
FINSIGHT_OLLAMA_ANALYSIS_MODEL=qwen3:8b
FINSIGHT_OLLAMA_EMBEDDING_MODEL=nomic-embed-text
FINSIGHT_OLLAMA_TEMPERATURE=0.1
FINSIGHT_OLLAMA_NUM_CTX=8192
FINSIGHT_OLLAMA_TIMEOUT_SECONDS=120

# Database
FINSIGHT_DATABASE_PATH=data/db/finsight.db
FINSIGHT_DATABASE_ECHO_SQL=false

# Vector store
FINSIGHT_CHROMA_PERSIST_DIRECTORY=data/chroma
FINSIGHT_CHROMA_COLLECTION_NAME=finsight_statements
FINSIGHT_CHROMA_RETRIEVAL_TOP_K=6

# Storage
FINSIGHT_STORAGE_UPLOADS_DIRECTORY=data/uploads
FINSIGHT_STORAGE_MAX_FILE_SIZE_MB=50
```

**Example: use different models per task**
```bash
FINSIGHT_OLLAMA_EXTRACTION_MODEL=mistral:7b
FINSIGHT_OLLAMA_CHAT_MODEL=llama3.1:8b
FINSIGHT_OLLAMA_NUM_CTX=16384        # Larger context for complex statements
FINSIGHT_CHROMA_RETRIEVAL_TOP_K=10   # Return more chunks per query
```

---

## Adding a New Institution

1. **Create the agent** in `backend/app/agents/institutions/<name>.py`:

```python
from app.agents.institutions.base import BaseInstitutionAgent

class FirstBankAgent(BaseInstitutionAgent):
    @property
    def institution_type(self) -> InstitutionType:
        return InstitutionType.FIRST_BANK

    async def can_handle(self, document: ParsedDocument) -> tuple[bool, float]:
        # Check first 3 pages for institution name
        ...

    async def extract(self, document: ParsedDocument, state: IngestionState) -> ExtractionResult:
        # Use FirstBankExtractor + FirstBankClassifier
        ...
```

2. **Create the parser** in `backend/app/parsers/<name>/`:
   - `classifier.py` — `is_<name>()` + `classify_statement_type()`
   - `extractor.py` — regex + LLM field extraction

3. **Register the agent** in `backend/app/agents/supervisor.py`:

```python
INSTITUTION_AGENT_REGISTRY: list[BaseInstitutionAgent] = [
    MorganStanleyAgent(),
    ChaseAgent(),
    ETradeAgent(),
    FirstBankAgent(),   # ← add here
]
```

4. **Add enum value** in `backend/app/domain/enums.py`:
```python
class InstitutionType(str, Enum):
    FIRST_BANK = "first_bank"
```

No other changes required — the `classify_node` iterates the registry automatically and routes to the highest-confidence match.

---

## Phase Roadmap

| Phase | Status | Scope |
|-------|--------|-------|
| **1 — MVP** | ✅ Complete | Morgan Stanley full pipeline, SQLite, Chroma, hybrid RAG, React UI, SSE streaming |
| **2** | Planned | Chase + E*TRADE agent implementations, improved fee anomaly detection, correction workflows |
| **3** | Planned | OCR support for scanned PDFs, multi-user support, MCP networked server mode |

---

## Key Architectural Decisions

| Decision | Rationale |
|----------|-----------|
| **Decimal strings for money** | SQLite has no decimal type; TEXT avoids float precision loss that would corrupt financial figures |
| **Async I/O throughout** | FastAPI + aiosqlite + `asyncio.to_thread()` for CPU-bound work; single event loop, no blocking |
| **LangGraph for ingestion** | Structured, composable graph with typed state; partial failures don't crash the pipeline |
| **Hybrid RAG (vector + SQL)** | Vector search handles semantics; SQL handles exact aggregations that embeddings can't answer |
| **Section-aware chunking** | Preserves document structure — "Account Summary" chunks don't mix with "Transaction History" |
| **UUID file naming** | Prevents path traversal attacks and filename collisions on upload |
| **Soft deletes (status columns)** | Preserves full audit trail; `deletion_records` tracks what was removed from Chroma + SQLite |
| **Config-driven model routing** | Any task's model is swappable via `.env`; no code changes to try different LLMs |
| **MCP tool registry** | Open/closed principle — new agent capabilities added without modifying existing agents |
| **100% local stack** | Ollama + Chroma + SQLite — zero cloud dependencies, zero data egress |
