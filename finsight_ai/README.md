# Coral

**Local-first AI financial intelligence workbench.** Upload bank and brokerage statements from Morgan Stanley, Chase, E\*TRADE, Amex, and Discover -- then query your finances in plain English. Every byte stays on your machine.

---

## Features

| Capability | Detail |
|---|---|
| **5 institution parsers** | Auto-detects Morgan Stanley, Chase, E\*TRADE, Amex, Discover from raw PDF text |
| **SQL-first query engine** | Deterministic SQL templates for fees, transactions, balances, holdings, cash flow -- no LLM needed for common questions |
| **FTS5 text search** | SQLite FTS5 virtual table indexes every document chunk for fast keyword search |
| **Semantic vector search** | Chroma + `nomic-embed-text` embeddings for open-ended natural-language questions |
| **Structured answer cards** | Typed financial answers rendered as cards with evidence drawers and confidence indicators |
| **Streaming ingestion** | Real-time SSE events during the full pipeline: parse, classify, extract, persist, embed |
| **Bucket scoping** | Group documents into INVESTMENTS or BANKING buckets; all queries are scoped accordingly |
| **Human-in-the-loop review** | Low-confidence extractions are staged for manual review before promotion |
| **Analytics dashboards** | Investment portfolio overview, fee trends, banking spend by category, subscription detection |
| **100% local** | Ollama LLM inference, SQLite storage, Chroma vectors -- no cloud APIs, no telemetry |

## Supported institutions

| Institution | Statement types |
|---|---|
| Morgan Stanley | IRA, Roth IRA, Advisory, Individual Brokerage |
| Chase | Checking, Sapphire, Freedom, United, Southwest, Ink (credit card variants) |
| E\*TRADE | Individual Brokerage (holdings, trades, balances, fees) |
| American Express | Platinum, Gold, Blue Cash, Delta, EveryDay |
| Discover | it, More, Miles, Cashback Debit |

## Screenshot description

The interface has a sidebar for navigation and two primary views:

- **Home** -- Upload panel with drag-and-drop PDF support, a real-time event stream panel showing each ingestion stage, a document list with status indicators, and a metrics overview dashboard with net-worth and spending-trend charts.
- **Chat** -- Conversational Q&A interface showing structured answer cards (fee summary tables, transaction lists, balance timelines), source citations with page references, and an agent trace panel that reveals the SQL queries and retrieval steps behind each answer.

---

## Quick start

### Prerequisites

- Python 3.11+
- Node.js 18+
- [Ollama](https://ollama.com) installed and running on port 11434

### 1. Pull the required models

```bash
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

### 2. Start the backend

```bash
cd coral/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env        # adjust values if needed
python run.py                  # http://localhost:8000
```

### 3. Start the frontend

```bash
cd coral/frontend
npm install
npm run dev                    # http://localhost:3000
```

### 4. Upload and query

1. Open http://localhost:3000
2. Create a bucket (e.g., "My Investments", type INVESTMENTS)
3. Drop a PDF statement -- watch the live SSE progress panel
4. Switch to Chat, select the bucket, and ask:

```
What are my total fees?
Show my largest transactions
What is my portfolio value?
Spending by category
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLModel, SQLAlchemy 2, aiosqlite, pdfplumber, structlog |
| LLM | Ollama `qwen3:8b` (classification, extraction, chat, SQL generation) |
| Embeddings | Ollama `nomic-embed-text` (768 dimensions) |
| Database | SQLite (canonical data + FTS5 text search) + Chroma (vector search) |
| Frontend | React 18, TypeScript, Tailwind CSS, Zustand, Vite, Recharts, Lucide |
| Orchestration | LangGraph (ingestion pipeline with SSE events) |
| Transport | REST + Server-Sent Events (SSE) for streaming |

---

## Project structure

```
coral/
├── backend/
│   ├── app/
│   │   ├── api/             # FastAPI routers + Pydantic request/response schemas
│   │   ├── agents/          # LangGraph supervisor + institution agents
│   │   ├── db/              # ORM models, engine, FTS5, repositories
│   │   ├── database/        # Async session engine + additional repositories
│   │   ├── domain/          # Entities, enums, typed error hierarchy
│   │   ├── ollama/          # Async Ollama HTTP client + task-based model router
│   │   ├── parsers/         # InstitutionParser interface + 5 institution packages
│   │   ├── rag/             # Chroma store, hybrid retriever, SQL templates, prompt builder
│   │   ├── services/        # Ingestion, chat, analytics, cache, review, metrics
│   │   ├── config.py        # pydantic-settings (all env-overridable)
│   │   └── main.py          # FastAPI app factory + lifespan
│   ├── data/                # SQLite DBs + uploaded PDFs (gitignored)
│   ├── migrations/
│   ├── tests/
│   ├── requirements.txt
│   └── run.py               # Dev server entry point
├── frontend/
│   ├── src/
│   │   ├── api/             # Typed HTTP client modules
│   │   ├── components/      # React components organized by feature
│   │   ├── hooks/           # useChat, useDocuments, useEventStream, usePipelineReducer
│   │   ├── pages/           # HomePage, ChatPage, AnalyticsPage, MetricsPage
│   │   ├── store/           # Zustand global store
│   │   └── types/           # TypeScript type definitions
│   └── package.json
├── data/                    # Chroma vector DB (gitignored)
├── .env.example
└── README.md
```

---

## Documentation

| Document | Contents |
|---|---|
| [README_SETUP.md](README_SETUP.md) | Detailed installation, environment variables, model configuration |
| [README_ARCHITECTURE.md](README_ARCHITECTURE.md) | System architecture with Mermaid diagrams, query routing, DB schema |
| [README_DATABASE.md](README_DATABASE.md) | Schema reference, table relationships, example SQL queries |
| [README_OPERATIONS.md](README_OPERATIONS.md) | Adding parsers, re-indexing, troubleshooting, log inspection |

---

## Ports

| Service | Port |
|---|---|
| Backend (FastAPI) | 8000 |
| Frontend (Vite) | 3000 |
| Ollama | 11434 |

---

## License

Private project. All rights reserved.
