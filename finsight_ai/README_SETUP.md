# Coral — Setup Guide

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.12+ | |
| Node.js | 18+ | |
| Ollama | Latest | https://ollama.com |
| qwen3:8b | — | `ollama pull qwen3:8b` (classification + extraction) |
| gemma4:latest | — | `ollama pull gemma4:latest` (chat + analysis) |
| nomic-embed-text | — | `ollama pull nomic-embed-text` (optional, for vector search) |

---

## 1. Configure your statement folders

Coral has **two** places that know about institutions/accounts — see
[README_ARCHITECTURE.md § Source configuration](README_ARCHITECTURE.md#source-configuration--two-parallel-systems)
for how they differ:

- `backend/app/statement_sources.py` — used by the **folder scanner**
- `backend/app/config/statement_catalog.py` — used by the **structured upload** flow (the canonical, 18-account list)

Open `backend/app/statement_sources.py`. It contains a list of `StatementSource`
entries, each mapping a local folder to an institution. The default paths mirror
the layout documented at the top of `statement_catalog.py`:

```
$CORAL_STATEMENTS_ROOT/american_express/blue_cash/YYYY/
$CORAL_STATEMENTS_ROOT/american_express/gold/YYYY/
$CORAL_STATEMENTS_ROOT/bank_of_america/YYYY/
$CORAL_STATEMENTS_ROOT/chase/checking/YYYY/
$CORAL_STATEMENTS_ROOT/chase/freedom_unlimited/YYYY/
$CORAL_STATEMENTS_ROOT/chase/prime/YYYY/
$CORAL_STATEMENTS_ROOT/chase/sapphire_preferred/YYYY/
$CORAL_STATEMENTS_ROOT/chase/united/YYYY/
$CORAL_STATEMENTS_ROOT/discover/YYYY/
$CORAL_STATEMENTS_ROOT/etrade/YYYY/
$CORAL_STATEMENTS_ROOT/marcus/emergency_fund/YYYY/
$CORAL_STATEMENTS_ROOT/marcus/arjun_fun/YYYY/
$CORAL_STATEMENTS_ROOT/morgan_stanley/nitin_ira/YYYY/
$CORAL_STATEMENTS_ROOT/morgan_stanley/pavani_ira/YYYY/
$CORAL_STATEMENTS_ROOT/morgan_stanley/joint_investments/YYYY/
$CORAL_STATEMENTS_ROOT/morgan_stanley/house_downpayment/YYYY/
$CORAL_STATEMENTS_ROOT/morgan_stanley/arjun_investment/YYYY/
$CORAL_STATEMENTS_ROOT/529/YYYY/
```

**To change the base path** for your machine, set `CORAL_STORAGE_STATEMENTS_ROOT`
in `backend/.env`, or edit `_CORAL_ROOT` at the top of `statement_sources.py`.
Default falls back to `~/Documents/Personal/Coral` if unset.

**Folder structure:** Each source uses `glob_pattern = "**/*.pdf"` by default, which recurses into any subdirectory including `YYYY/` subfolders.

**Chase products:** All Chase products (checking + 4 credit cards) share `root_path = chase/<product>` subfolders and are distinguished by `filename_hints` / their own `rel_path`.

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
cd finsight_ai/frontend-next
npm install
npm run dev
```

Open http://localhost:3001 (the dev server proxies `/api/v1/*` to the backend on port 8000 — see `next.config.mjs`)

---

## 4. Upload or scan-and-ingest statements

**Structured upload (recommended):** Go to the Upload page, pick institution/account/year/month
(populated from `GET /api/v1/catalog/institutions`), and drop the PDF. Coral
writes it to the normalized path and ingests it immediately.

**Folder scan:** If you keep statements in the folders configured in
`statement_sources.py`, trigger `POST /api/v1/scan/ingest` (or the equivalent
UI action) to scan all configured folders, compute SHA-256 for each PDF, skip
already-ingested files, and parse new ones.

**Re-scanning is safe** — files are deduped by hash, so re-running ingest twice never re-ingests the same file.

---

## 5. Direct API access

Interactive docs: http://localhost:8000/docs

```
GET  /api/v1/scan/status          # Scan folders, return counts (no ingestion)
POST /api/v1/scan/ingest          # Scan + ingest all pending files
POST /api/v1/documents/upload-local  # Structured upload (institution/account/year/month)
GET  /api/v1/documents/{id}/status   # Ingestion status poll

GET  /api/v1/dashboard/summary    # KPI counts
GET  /api/v1/dashboard/investments # Investments dashboard data
GET  /api/v1/dashboard/banking    # Banking dashboard data
GET  /api/v1/dashboard/coverage   # Per-institution document coverage

GET  /api/v1/catalog/institutions        # Institutions + accounts for upload dropdowns
GET  /api/v1/catalog/destination-preview # Preview the normalized upload path

POST /api/v1/chat/query           # Ask a question (batch JSON response)
POST /api/v1/chat/stream          # Ask a question (SSE streaming)
GET  /api/v1/documents/           # List all documents
GET  /api/v1/health               # Health + Ollama status
```

---

## 6. Environment variables

Create a `.env` file in `backend/` to override defaults:

```env
CORAL_DB_PATH=data/db/finsight.db
CORAL_OLLAMA_BASE_URL=http://localhost:11434
CORAL_OLLAMA_CLASSIFICATION_MODEL=qwen3:8b
CORAL_OLLAMA_CHAT_MODEL=gemma4:latest
CORAL_SEARCH_VECTOR_SEARCH_ENABLED=true
CORAL_STORAGE_STATEMENTS_ROOT=/your/path/to/Coral
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
3. Add a `StatementSource` in `backend/app/statement_sources.py` and add its `institution_type` to `PARSEABLE_INSTITUTION_TYPES`
4. Add an `AccountCatalogEntry` in `backend/app/config/statement_catalog.py` so it shows up in the upload dropdowns
5. Add a bank-specific detail model in `backend/app/db/models.py` if needed

See [README_ARCHITECTURE.md](README_ARCHITECTURE.md#adding-a-new-institution) for more detail.

---

## 9. Ports

| Service | Port |
|---------|------|
| Frontend (frontend-next) | 3001 |
| Backend | 8000 |
| Ollama | 11434 |
