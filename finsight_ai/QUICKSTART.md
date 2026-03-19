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

ollama pull qwen3:8b          # LLM for extraction, analysis, and chat
ollama pull nomic-embed-text  # embedding model for vector search
```

Verify both are available:

```bash
ollama list
# Should show qwen3:8b and nomic-embed-text
```

---

## Step 2 — Backend Setup

```bash
cd coral/backend

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

You should see:

```
INFO  Coral starting up...
INFO  Database initialized
INFO  Chroma vector store ready
INFO  Uvicorn running on http://localhost:8000
```

**API docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Step 3 — Frontend Setup

Open a new terminal tab:

```bash
cd coral/frontend

npm install
npm run dev
```

You should see:

```
  VITE v5.x.x  ready in Xms

  ➜  Local:   http://localhost:3000/
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

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

The chat uses **hybrid retrieval** — vector search for document context plus generated SQL for precise aggregations.

---

## Directory Layout (after first run)

```
coral/
├── backend/
│   ├── .env               ← your local config (git-ignored)
│   └── data/
│       ├── db/
│       │   └── finsight.db    ← SQLite database (auto-created)
│       ├── uploads/           ← uploaded PDFs stored here
│       └── chroma/            ← vector store (auto-created)
└── frontend/
    └── node_modules/      ← installed by npm install
```

---

## Configuration

All settings are controlled by `backend/.env`. The most commonly adjusted values:

```bash
# Use a different model for any task
CORAL_OLLAMA_CHAT_MODEL=llama3.1:8b
CORAL_OLLAMA_EXTRACTION_MODEL=mistral:7b

# Increase context window for large statements
CORAL_OLLAMA_NUM_CTX=16384

# Return more chunks per RAG query (default: 6)
CORAL_CHROMA_RETRIEVAL_TOP_K=10

# Increase max upload size (default: 50 MB)
CORAL_STORAGE_MAX_FILE_SIZE_MB=100
```

All variable names follow the pattern `CORAL_<GROUP>_<FIELD>`. See `.env.example` for the full list.

---

## Troubleshooting

**Backend fails to start with `OllamaConnectionError`**
- Make sure Ollama is running: `ollama serve`
- Check it's reachable: `curl http://localhost:11434/api/tags`

**`OllamaModelNotFoundError` during ingestion**
- The model wasn't pulled: `ollama pull qwen3:8b && ollama pull nomic-embed-text`

**Frontend shows blank page or network errors**
- Confirm the backend is running on port 8000
- Check the browser console for CORS errors — the backend allows `http://localhost:3000` by default

**PDF stuck on "Processing"**
- Check backend logs for extraction errors
- Very large PDFs (100+ pages) can take several minutes depending on hardware

**`pip install` fails on `chromadb`**
- Ensure you're using Python 3.11+: `python --version`
- On Apple Silicon: `pip install --upgrade pip` before installing

---

## Running Tests

```bash
cd coral/backend
source .venv/bin/activate

pytest                        # run all tests
pytest -v                     # verbose output
pytest tests/test_parsers.py  # run a specific file
```

---

## Linting & Type Checking

```bash
cd coral/backend
source .venv/bin/activate

ruff check .        # lint
ruff format .       # auto-format
mypy app/           # type check
```

```bash
cd coral/frontend
npm run lint
```

---

## What's Running Where

| Service | URL | Purpose |
|---------|-----|---------|
| Frontend | http://localhost:3000 | React UI |
| Backend API | http://localhost:8000 | FastAPI REST + SSE |
| API Docs | http://localhost:8000/docs | Swagger UI |
| Ollama | http://localhost:11434 | Local LLM inference |
| SQLite | `data/db/finsight.db` | Structured financial data |
| Chroma | `data/chroma/` | Vector embeddings |
