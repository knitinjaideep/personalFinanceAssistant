# Coral — Quickstart Guide

Get the app running locally in under 10 minutes.

---

## Prerequisites

Make sure the following are installed before you begin:

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ | `brew install python@3.11` |
| Node.js | 20+ | `brew install node` |
| Ollama | latest | [ollama.ai](https://ollama.ai) |

---

## Step 1 — Pull Ollama Models

Ollama must be running before you start the backend. Open a terminal and pull the required models:

```bash
ollama serve   # skip if Ollama is already running as a background service

ollama pull qwen3:8b          # classification + extraction
ollama pull gemma4:latest     # chat + analysis
ollama pull nomic-embed-text  # embedding model for vector search
```

Verify all three are available:

```bash
ollama list
# Should show qwen3:8b, gemma4:latest, and nomic-embed-text
```

---

## Step 2 — Backend Setup

```bash
cd finsight_ai/backend

# Create and activate a virtual environment
python3.11 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install all dependencies
pip install -e ".[dev]"

# Set up environment config
cp ../.env.example .env
```

The defaults in `.env` work out of the box for local development. No changes needed unless you want to customize model names or paths (see [Configuration](#configuration) below).

Start the backend:

```bash
python run.py
```

You should see startup logs confirming the database initialized and the
configured chat model (`gemma4:latest` by default) is available in Ollama,
followed by:

```
INFO  Uvicorn running on http://localhost:8000
```

Note: `langgraph` and `chromadb` are still listed as dependencies and will
install, but neither is wired into any route — the startup log explicitly
reports `langgraph_wired_to_chat: False`. Chat runs entirely on SQLite
(FTS5 + JSON-embedding cosine similarity), not LangGraph/Chroma.

**API docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Step 3 — Frontend Setup

Open a new terminal tab:

```bash
cd finsight_ai/frontend-next

npm install
npm run dev
```

You should see:

```
  ▲ Next.js 14.x.x
  - Local:   http://localhost:3001
```

Open [http://localhost:3001](http://localhost:3001) in your browser. The dev
server proxies `/api/v1/*` to the backend on port 8000.

---

## Step 4 — Upload Your First Statement

1. Navigate to the **Upload** tab
2. Drag and drop a Morgan Stanley PDF statement (or click to browse)
3. Watch the real-time event panel as the system:
   - Parses the PDF
   - Classifies the institution
   - Extracts balances, fees, holdings, and transactions
   - Embeds the document for semantic search
4. Status changes to **Processed** when complete

---

## Step 5 — Ask Questions

Navigate to the **Chat** tab and try:

```
How much did I pay in advisory fees last year?
Did my portfolio balance increase in Q4?
Show all transactions over $10,000.
What is my current allocation breakdown?
Compare my fees month-over-month.
```

The chat pipeline (`services/chat_router.py`) classifies your question, then
answers with **pre-written deterministic SQL** (never LLM-generated SQL),
falling back to FTS5 + in-SQLite vector search over document text when SQL
comes back empty. See [README_ARCHITECTURE.md](README_ARCHITECTURE.md) for the full pipeline.

---

## Directory Layout (after first run)

```
finsight_ai/
├── backend/
│   ├── .env               ← your local config (git-ignored)
│   └── data/
│       ├── db/
│       │   └── finsight.db    ← SQLite database (auto-created)
│       └── uploads/           ← uploaded PDFs stored here
└── frontend-next/
    └── node_modules/      ← installed by npm install
```

---

## Configuration

All settings are controlled by `backend/.env`. The most commonly adjusted values:

```bash
# Use a different model per task role
CORAL_OLLAMA_CHAT_MODEL=gemma4:latest
CORAL_OLLAMA_CLASSIFICATION_MODEL=qwen3:8b
CORAL_OLLAMA_EXTRACTION_MODEL=qwen3:8b

# Increase context window for large statements
CORAL_OLLAMA_NUM_CTX=16384

# Return more chunks per vector/FTS query (defaults: 6 / 10)
CORAL_SEARCH_VECTOR_TOP_K=10
CORAL_SEARCH_FTS_TOP_K=15

# Increase max upload size (default: 50 MB)
CORAL_STORAGE_MAX_FILE_SIZE_MB=100

# Where statement folders live for the scanner (default: ~/Documents/Personal/Coral)
CORAL_STORAGE_STATEMENTS_ROOT=/your/path/to/Coral
```

All variable names follow the pattern `CORAL_<GROUP>_<FIELD>`. See `.env.example` for the full list.

---

## Troubleshooting

**Backend fails to start / `ollama_unreachable` in logs**
- Make sure Ollama is running: `ollama serve`
- Check it's reachable: `curl http://localhost:11434/api/tags`

**`ollama_model_unavailable` in logs during startup or ingestion**
- The model wasn't pulled: `ollama pull gemma4:latest && ollama pull qwen3:8b && ollama pull nomic-embed-text`

**Frontend shows blank page or network errors**
- Confirm the backend is running on port 8000
- Check the browser console for CORS errors — the backend allows `http://localhost:3000` and `http://localhost:3001` by default (`cors_origins` in `backend/app/config/__init__.py`)

**PDF stuck on "processing"**
- Check backend logs for extraction errors
- Very large PDFs (100+ pages) can take several minutes depending on hardware

---

## Running Tests

```bash
cd finsight_ai/backend
source .venv/bin/activate

pytest                        # run all tests
pytest -v                     # verbose output
pytest app/chat/tests/        # chat pipeline tests
python app/chat/evals/run_chat_evals.py  # golden-question eval suite
```

---

## Linting & Type Checking

```bash
cd finsight_ai/backend
source .venv/bin/activate

ruff check .        # lint
ruff format .       # auto-format
mypy app/           # type check
```

```bash
cd finsight_ai/frontend-next
npm run lint
```

---

## What's Running Where

| Service | URL | Purpose |
|---------|-----|---------|
| Frontend (frontend-next) | http://localhost:3001 | Next.js UI |
| Backend API | http://localhost:8000 | FastAPI REST + SSE |
| API Docs | http://localhost:8000/docs | Swagger UI |
| Ollama | http://localhost:11434 | Local LLM inference |
| SQLite | `backend/data/db/finsight.db` | Structured financial data + FTS5 + vector embeddings (all in one file) |
