# Coral — Local-First Financial Statement Analyzer

Coral is a personal finance workbench that runs entirely on your machine. No cloud APIs, no telemetry, no subscriptions.

It scans your local statement folders, parses PDFs from your financial institutions, persists structured data into a local SQLite database, and lets you explore your finances through dashboards and a conversational AI chat interface.

---

## What it does

- **Scans** configured local folders for statement PDFs (recurses into YYYY/ subfolders)
- **Deduplicates** via SHA-256 so re-scanning never re-ingests the same file
- **Parses** statements from Morgan Stanley, E\*TRADE, Chase, Amex, Discover, and Bank of America
- **Persists** structured canonical data (transactions, holdings, fees, balances) into SQLite
- **Investments dashboard** — portfolio value, unrealized gains, holdings breakdown, fee tracking, balance history charts
- **Banking dashboard** — monthly spend trend, category breakdown, top merchants, per-card summary, subscriptions
- **Chat** — ask plain-English questions, answered via SQL-first routing (+ FTS5/vector for document lookups and affordability analysis)

---

## Quick start

```bash
# 1. Start Ollama (required for chat and extraction)
ollama serve
ollama pull qwen3:8b          # classification + extraction
ollama pull gemma4:latest     # chat + analysis
ollama pull nomic-embed-text  # embeddings (optional, vector search)

# 2. Start the backend
cd finsight_ai/backend
pip install -e ".[dev]"       # or: poetry install
uvicorn app.main:app --reload --port 8000

# 3. Start the frontend
cd finsight_ai/frontend-next
npm install
npm run dev                    # → http://localhost:3001
```

Then open http://localhost:3001, click **Upload** (or **Scan & Ingest**) to load your statements.

---

## Supported institutions

| Institution          | Bucket      | Parser |
|----------------------|-------------|--------|
| Morgan Stanley       | Investments | ✅ Full |
| E\*TRADE             | Investments | ✅ Full |
| Chase (all products) | Investments | ✅ Full |
| American Express     | Investments | ✅ Full |
| Discover             | Investments | ✅ Full |
| Bank of America      | Banking     | ✅ Full |
| Marcus (Goldman Sachs) | Banking   | 🔲 Stub (catalog-only, no parser) |
| 529 College Savings  | Investments | 🔲 Stub (catalog-only, no parser) |

See [`backend/app/config/statement_catalog.py`](backend/app/config/statement_catalog.py) for the full 18-account catalog and bucket rules.

---

## Docs

| File | Contents |
|------|----------|
| [README_SETUP.md](README_SETUP.md) | Local setup, folder configuration, how to run |
| [README_ARCHITECTURE.md](README_ARCHITECTURE.md) | System architecture, data flow, component map |
| [README_DATABASE.md](README_DATABASE.md) | Database schema, dashboard query locations |
| [queries.sql](queries.sql) | Copy-paste SQL reference for the live database |

---

## Tech stack

**Backend:** Python 3.12, FastAPI, SQLite + FTS5, SQLModel, pdfplumber, Ollama (`qwen3:8b` classification/extraction, `gemma4:latest` chat/analysis, `nomic-embed-text` embeddings)

**Frontend:** Next.js 14 (App Router), TypeScript, Tailwind CSS, Framer Motion, Zustand, Recharts

**Privacy:** 100% local — your data never leaves your machine
