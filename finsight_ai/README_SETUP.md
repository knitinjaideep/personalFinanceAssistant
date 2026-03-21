# Coral — Setup Guide

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.12+ | |
| Node.js | 18+ | |
| Ollama | Latest | https://ollama.com |
| qwen3:8b | — | `ollama pull qwen3:8b` |
| nomic-embed-text | — | `ollama pull nomic-embed-text` (optional, for vector search) |

---

## 1. Configure your statement folders

Open `backend/app/statement_sources.py`.

The file contains a list of `StatementSource` entries, each mapping a local folder to an institution. The default paths are:

```
/Users/nitinkotcherlakota/Documents/Personal/Coral/Chase/Checking/YYYY/
/Users/nitinkotcherlakota/Documents/Personal/Coral/Amex/YYYY/
/Users/nitinkotcherlakota/Documents/Personal/Coral/BOFA/YYYY/
/Users/nitinkotcherlakota/Documents/Personal/Coral/Discover/YYYY/
/Users/nitinkotcherlakota/Documents/Personal/Coral/Marcus/YYYY/
/Users/nitinkotcherlakota/Documents/Personal/Coral/Etrade/YYYY/
/Users/nitinkotcherlakota/Documents/Personal/Coral/Morgan Stanley/IRA/YYYY/
/Users/nitinkotcherlakota/Documents/Personal/Coral/Morgan Stanley/Joint Investment/YYYY/
```

**To change the base path** for your machine, edit `_CORAL_ROOT` at the top of the file:

```python
_CORAL_ROOT = Path("/your/path/to/Coral")
```

**Folder structure:** Each source uses `glob_pattern = "**/*.pdf"` by default, which recurses into any subdirectory including `YYYY/` subfolders.

**Chase products:** All four Chase products share the same `root_path = Chase/Checking`. They are distinguished by `filename_hints`. Each source only claims PDFs whose filename contains its hint (e.g., `Freedom` only picks up `Freedom_January.pdf`).

---

## 2. Start the backend

```bash
cd finsight_ai/backend

# Create virtual environment (first time)
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Run
uvicorn app.main:app --reload --port 8000
```

The backend will auto-create the SQLite database at `data/db/finsight.db` on first run.

---

## 3. Start the frontend

```bash
cd finsight_ai/frontend
npm install
npm run dev
```

Open http://localhost:3000

---

## 4. Scan and ingest statements

1. Open the Dashboard
2. Click **Scan & Ingest** in the top-right of the header
3. Coral scans all configured folders, computes SHA-256 for each PDF, skips already-ingested files, and parses new ones
4. The KPI row and dashboards update automatically when ingestion completes

**Re-scanning is safe** — files are deduped by hash, so clicking Scan & Ingest twice never re-ingests the same file.

The button shows `Scan & Ingest (N)` when N files are pending, or `Scan & Ingest` when everything is current.

---

## 5. Direct API access

Interactive docs: http://localhost:8000/docs

```
GET  /api/v1/scan/status          # Scan folders, return counts (no ingestion)
POST /api/v1/scan/ingest          # Scan + ingest all pending files

GET  /api/v1/dashboard/summary    # KPI counts
GET  /api/v1/dashboard/investments # Investments dashboard data
GET  /api/v1/dashboard/banking    # Banking dashboard data
GET  /api/v1/dashboard/coverage   # Per-institution document coverage

POST /api/v1/chat/query           # Ask a question
GET  /api/v1/documents/           # List all documents
GET  /api/v1/health               # Health + Ollama status
```

---

## 6. Environment variables

Create a `.env` file in `backend/` to override defaults:

```env
CORAL_DB_PATH=data/db/finsight.db
CORAL_OLLAMA_BASE_URL=http://localhost:11434
CORAL_OLLAMA_CHAT_MODEL=qwen3:8b
CORAL_SEARCH_VECTOR_SEARCH_ENABLED=true
```

---

## 7. Direct database access

The SQLite database is at `backend/data/db/finsight.db`.

```bash
sqlite3 backend/data/db/finsight.db
```

GUI tools that work well: TablePlus, DB Browser for SQLite, DBeaver.

See [README_DATABASE.md](README_DATABASE.md) for schema details and example queries.

---

## 8. Adding a new institution

1. Create `backend/app/parsers/<name>/parser.py` implementing `InstitutionParser`
2. Register it in `backend/app/parsers/base.py` → `_register_all_parsers()`
3. Add a `StatementSource` in `backend/app/config/statement_sources.py`
4. Add the institution_type to `PARSEABLE_INSTITUTION_TYPES` in `statement_sources.py`

---

## 9. Ports

| Service | Port |
|---------|------|
| Frontend | 3000 |
| Backend | 8000 |
| Ollama | 11434 |
