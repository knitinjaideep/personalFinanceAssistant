# Coral — Local-First Financial Statement Analyzer

Coral is a personal finance workbench that runs entirely on your machine. No cloud APIs, no telemetry, no subscriptions.

It scans your local statement folders, parses PDFs from your financial institutions, persists structured data into a local SQLite database, and lets you explore your finances through dashboards and a conversational AI chat interface.

---

## What it does

- **Scans** configured local folders for statement PDFs (recurses into YYYY/ subfolders)
- **Deduplicates** via SHA-256 so re-scanning never re-ingests the same file
- **Parses** statements from Morgan Stanley, E\*TRADE, Chase, Amex, and Discover
- **Persists** structured canonical data (transactions, holdings, fees, balances) into SQLite
- **Investments dashboard** — portfolio value, unrealized gains, holdings breakdown, fee tracking, balance history charts
- **Banking dashboard** — monthly spend trend, category breakdown, top merchants, per-card summary, subscriptions
- **Chat** — ask plain-English questions answered from your DB

---

## Quick start

```bash
# 1. Start Ollama (required for chat and extraction)
ollama serve
ollama pull qwen3:8b
ollama pull nomic-embed-text

# 2. Start the backend
cd finsight_ai/backend
pip install -e ".[dev]"       # or: poetry install
uvicorn app.main:app --reload --port 8000

# 3. Start the frontend
cd finsight_ai/frontend
npm install
npm run dev                    # → http://localhost:3000
```

Then open http://localhost:3000, click **Scan & Ingest** to load your statements.

---

## Supported institutions

| Institution          | Bucket      | Parser |
|----------------------|-------------|--------|
| Morgan Stanley       | Investments | ✅ Full |
| E\*TRADE             | Investments | ✅ Full |
| Chase (all products) | Banking     | ✅ Full |
| American Express     | Banking     | ✅ Full |
| Discover             | Banking     | ✅ Full |
| Bank of America      | Banking     | 🔲 Stub (scanned, not yet parsed) |
| Marcus Goldman Sachs | Banking     | 🔲 Stub (scanned, not yet parsed) |

---

## Docs

| File | Contents |
|------|----------|
| [README_SETUP.md](README_SETUP.md) | Local setup, folder configuration, how to run |
| [README_ARCHITECTURE.md](README_ARCHITECTURE.md) | System architecture, data flow, component map |
| [README_DATABASE.md](README_DATABASE.md) | Database schema, example queries, dashboard query locations |

---

## Tech stack

**Backend:** Python 3.12, FastAPI, SQLite + FTS5, SQLModel, pdfplumber, Ollama (qwen3:8b + nomic-embed-text)

**Frontend:** React 18, TypeScript, Tailwind CSS, Vite, Recharts, Framer Motion, Zustand

**Privacy:** 100% local — your data never leaves your machine
