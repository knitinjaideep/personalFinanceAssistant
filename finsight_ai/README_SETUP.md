# Coral -- Detailed Setup Guide

This guide covers the full installation and configuration process for running Coral locally.

---

## System requirements

| Requirement | Minimum | Recommended |
|---|---|---|
| Python | 3.11+ | 3.12 |
| Node.js | 18+ | 20 LTS |
| RAM | 8 GB | 16 GB (Ollama loads models into memory) |
| Disk | 10 GB free | 20 GB (models + uploaded PDFs) |
| OS | macOS, Linux | macOS Apple Silicon for best Ollama performance |

---

## 1. Install Ollama

Ollama runs the LLM and embedding models locally.

### macOS

```bash
brew install ollama
```

Or download from https://ollama.com/download

### Linux

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### Verify Ollama is running

```bash
ollama --version
# Ollama should auto-start. If not:
ollama serve
```

Ollama listens on http://localhost:11434 by default.

---

## 2. Pull required models

Coral uses two Ollama models:

```bash
# LLM for classification, extraction, chat, and SQL generation
ollama pull qwen3:8b

# Embedding model for semantic vector search (768 dimensions)
ollama pull nomic-embed-text
```

Verify they are available:

```bash
ollama list
# Should show qwen3:8b and nomic-embed-text
```

### Model sizes

| Model | Size on disk | RAM usage |
|---|---|---|
| `qwen3:8b` | ~5 GB | ~6 GB |
| `nomic-embed-text` | ~270 MB | ~300 MB |

### Using alternative models

All model assignments are config-driven. To swap models, set environment variables:

```bash
# Use a different chat model
CORAL_OLLAMA_CHAT_MODEL=llama3.1:8b

# Use a different extraction model (can differ from chat)
CORAL_OLLAMA_EXTRACTION_MODEL=qwen3:8b

# Use a different embedding model
CORAL_OLLAMA_EMBEDDING_MODEL=mxbai-embed-large
```

Each task type (classification, extraction, chat, analysis, embedding) can be routed to a different model independently.

---

## 3. Backend setup

### Create a virtual environment

```bash
cd coral/backend
python -m venv .venv
source .venv/bin/activate    # macOS/Linux
# .venv\Scripts\activate     # Windows
```

### Install dependencies

```bash
pip install -r requirements.txt
```

Key Python packages:

| Package | Purpose |
|---|---|
| `fastapi` | Web framework |
| `uvicorn[standard]` | ASGI server |
| `sqlmodel` | ORM (SQLModel = SQLAlchemy + Pydantic) |
| `aiosqlite` | Async SQLite driver |
| `pdfplumber` | PDF text and table extraction |
| `pypdf` | PDF metadata reading |
| `httpx` | Async HTTP client for Ollama |
| `pydantic-settings` | Environment-based configuration |
| `structlog` | Structured logging |
| `python-multipart` | File upload handling |

### Configure environment

```bash
cp ../.env.example .env
```

Edit `.env` as needed. The defaults work out of the box for local development.

### Start the backend

```bash
# Option 1: Using the run script (auto-reload enabled)
python run.py

# Option 2: Using uvicorn directly
uvicorn app.main:app --reload --port 8000 --host 0.0.0.0
```

The API is available at http://localhost:8000. Interactive docs at http://localhost:8000/docs.

### Verify backend health

```bash
curl http://localhost:8000/health
# {"status":"healthy","version":"2.0.0"}
```

---

## 4. Frontend setup

### Install dependencies

```bash
cd coral/frontend
npm install
```

Key frontend packages:

| Package | Purpose |
|---|---|
| `react` + `react-dom` | UI framework |
| `react-router-dom` | Client-side routing |
| `zustand` | Lightweight state management |
| `recharts` | Charts for analytics dashboards |
| `react-dropzone` | Drag-and-drop file upload |
| `lucide-react` | Icon library |
| `date-fns` | Date formatting |
| `react-hot-toast` | Notification toasts |
| `tailwindcss` | Utility-first CSS |
| `vite` | Build tool and dev server |
| `typescript` | Type safety |

### Start the dev server

```bash
npm run dev
```

The frontend is available at http://localhost:3000.

### Build for production

```bash
npm run build
npm run preview    # serves the production build locally
```

---

## 5. Environment variables reference

All settings use the `CORAL_` prefix and are defined in `backend/app/config.py`.

### Application

| Variable | Default | Description |
|---|---|---|
| `CORAL_ENVIRONMENT` | `development` | `development`, `production`, or `test` |
| `CORAL_DEBUG` | `true` | Enables `/docs` and `/redoc` endpoints |
| `CORAL_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `CORAL_CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed CORS origins (JSON array) |

### Ollama

| Variable | Default | Description |
|---|---|---|
| `CORAL_OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `CORAL_OLLAMA_CLASSIFICATION_MODEL` | `qwen3:8b` | Model for institution/type classification |
| `CORAL_OLLAMA_EXTRACTION_MODEL` | `qwen3:8b` | Model for structured data extraction |
| `CORAL_OLLAMA_CHAT_MODEL` | `qwen3:8b` | Model for chat response generation |
| `CORAL_OLLAMA_ANALYSIS_MODEL` | `qwen3:8b` | Model for SQL generation and analysis |
| `CORAL_OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model |
| `CORAL_OLLAMA_TEMPERATURE` | `0.1` | Generation temperature (0.0--2.0) |
| `CORAL_OLLAMA_NUM_CTX` | `8192` | Context window size |
| `CORAL_OLLAMA_TIMEOUT_SECONDS` | `120` | Request timeout |

### Database

| Variable | Default | Description |
|---|---|---|
| `CORAL_DB_PATH` | `data/db/finsight.db` | SQLite database file path (relative to backend/) |
| `CORAL_DB_ECHO_SQL` | `false` | Log all SQL queries to stdout |

### Chroma (vector store)

| Variable | Default | Description |
|---|---|---|
| `CORAL_CHROMA_PERSIST_DIRECTORY` | `data/chroma` | Chroma storage directory |
| `CORAL_CHROMA_COLLECTION_NAME` | `coral_statements` | Chroma collection name |
| `CORAL_CHROMA_RETRIEVAL_TOP_K` | `6` | Number of vector results per query |

### Storage

| Variable | Default | Description |
|---|---|---|
| `CORAL_STORAGE_UPLOADS_DIRECTORY` | `data/uploads` | Directory for uploaded PDFs |
| `CORAL_STORAGE_MAX_FILE_SIZE_MB` | `50` | Maximum upload file size |

### Search

| Variable | Default | Description |
|---|---|---|
| `CORAL_SEARCH_VECTOR_SEARCH_ENABLED` | `true` | Enable/disable Chroma vector search |
| `CORAL_SEARCH_VECTOR_TOP_K` | `6` | Vector search result count |
| `CORAL_SEARCH_FTS_TOP_K` | `10` | FTS5 search result count |
| `CORAL_SEARCH_EMBEDDING_DIMENSIONS` | `768` | Embedding vector dimensions |

---

## 6. Data directories

Coral creates these directories automatically on first run:

```
coral/
├── backend/data/
│   └── db/
│       ├── finsight.db          # Main SQLite database
│       └── finsight_cache.db    # Cache database (embed, LLM, retrieval)
├── data/
│   ├── chroma/                  # Chroma vector store
│   │   └── chroma.sqlite3       # Chroma's internal SQLite
│   └── uploads/                 # Uploaded PDF files
```

All data directories are in `.gitignore`. To reset completely:

```bash
rm -rf backend/data/ data/chroma/ data/uploads/
```

The database and FTS5 tables are recreated automatically on next startup.

---

## 7. Running all services together

Open three terminal windows:

```bash
# Terminal 1: Ollama (if not auto-started)
ollama serve

# Terminal 2: Backend
cd coral/backend
source .venv/bin/activate
python run.py

# Terminal 3: Frontend
cd coral/frontend
npm run dev
```

Then open http://localhost:3000 in your browser.

---

## 8. Common issues

| Problem | Solution |
|---|---|
| `Connection refused` on port 11434 | Start Ollama: `ollama serve` |
| `model 'qwen3:8b' not found` | Pull the model: `ollama pull qwen3:8b` |
| Backend fails to start with DB errors | Delete `backend/data/db/` and restart -- tables auto-create |
| CORS errors in browser console | Ensure `CORAL_CORS_ORIGINS` includes `http://localhost:3000` |
| Slow first query after restart | Ollama loads models on first use; subsequent queries are faster |
| `aiosqlite` import error | Ensure you activated the virtual environment: `source .venv/bin/activate` |
| Frontend shows blank page | Check that the backend is running on port 8000 |
| Upload fails with 413 | Increase `CORAL_STORAGE_MAX_FILE_SIZE_MB` |
