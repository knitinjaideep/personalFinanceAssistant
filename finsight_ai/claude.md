# Claude Code Project Guide — Coral v2

## Project Summary
Coral is a **local-first financial statement analyzer**. It parses statements from Morgan Stanley, Chase, E*TRADE, Amex, and Discover, stores structured data in SQLite, and answers financial questions using SQL-first query routing with FTS5 text search and optional vector retrieval.

Stack: FastAPI, SQLite + FTS5, SQLModel, pdfplumber, Ollama (qwen3:8b + nomic-embed-text), React, TypeScript, Tailwind, Zustand, Vite.

## Architecture (v2 — simplified)

- **No LangGraph, no MCP, no Chroma, no agent supervisor**
- SQL-first, deterministic architecture
- Parser plugin system with registry pattern
- Explicit query router with intent classification
- FTS5 for text search, optional vector embeddings in SQLite

## Key Modules

### Backend (`backend/app/`)
- `config.py` — Pydantic settings, env-driven
- `main.py` — FastAPI app factory
- `domain/` — enums, entities (Pydantic), errors
- `db/` — models (SQLModel), engine, repositories, FTS5
- `parsers/` — base interface + registry, per-institution parsers
- `services/` — ingestion, llm, query_router, sql_query, text_search, vector_search, answer_builder
- `api/` — documents, chat, analytics, health routes

### Frontend (`frontend/src/`)
- 2 pages: HomePage (upload + documents + summaries) and ChatPage (Q&A with structured answers)
- Zustand for minimal global state
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

## Query Router
Intent-based routing:
- fee_summary, transaction_lookup, balance_lookup → SQL path
- text_explanation → FTS path
- hybrid_financial_question → SQL + FTS/vector

## Database
- Canonical tables: institutions, accounts, documents, statements, transactions, fees, holdings, balance_snapshots, text_chunks, derived_metrics
- Bank-specific: morgan_stanley_details, chase_details, etrade_details, amex_details, discover_details
- FTS5 virtual table: text_chunks_fts

## Ports
- Backend: 8000
- Frontend: 3000
- Ollama: 11434
