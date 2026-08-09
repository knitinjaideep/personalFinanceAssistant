```mermaid
flowchart TD
    subgraph API["FastAPI Layer"]
        UP["POST /documents/upload-local\n(structured upload)"]
        SCAN["POST /scan/ingest\n(folder scanner)"]
        CHAT["POST /chat/query or /chat/stream"]
    end

    subgraph Ingestion["Ingestion pipeline (services/ingestion.py, sequential async)"]
        direction TB
        REG["Register document\n(documents table)"]
        PARSE["pdfplumber\nPDF → raw text + tables"]
        DETECT["ParserRegistry.detect_institution()\nAll parsers' can_handle() →\nbest confidence wins (regex, no LLM)"]
        EXTRACT["parser.extract()\nmorgan_stanley / chase / etrade /\namex / discover / bank_of_america"]
        PERSIST["Persist canonical rows:\ninstitution, account, statement,\ntransactions, fees, holdings, balances"]
        DETAIL["Persist bank-specific detail row\n(chase_details, morgan_stanley_details, ...\nBofA has none)"]
        CHUNK["Chunk text →\ntext_chunks + text_chunks_fts (FTS5)"]
        EMBED["Optional: nomic-embed-text\n→ JSON embedding in text_chunks.embedding"]
    end

    subgraph Storage["Storage — single SQLite file"]
        SQ[("SQLite\nCanonical tables + detail tables +\ntext_chunks + text_chunks_fts + embeddings")]
    end

    subgraph ChatPipeline["Chat (see README_ARCHITECTURE.md for full diagram)"]
        CR["chat_router.route()\nclassify → route decision →\nSQL handlers (13, deterministic) →\nFTS5/vector fallback →\nanswer_builder"]
        AFF["chat/domains/affordability\n7-layer deterministic pipeline\n(bypasses SQL)"]
    end

    subgraph LLM["Local Ollama"]
        QW["qwen3:8b\nclassification / extraction"]
        GM["gemma4:latest\nchat / analysis narration"]
        NE["nomic-embed-text\nembeddings"]
    end

    UP --> REG
    SCAN --> REG
    REG --> PARSE --> DETECT --> EXTRACT --> PERSIST --> DETAIL --> CHUNK --> EMBED
    PERSIST --> SQ
    CHUNK --> SQ
    EMBED --> SQ
    EMBED -->|"generate embeddings"| NE

    CHAT --> CR
    CR -->|"classify"| QW
    CR -->|"affordability route"| AFF
    CR -->|"SQL + FTS5 + vector"| SQ
    CR -->|"narrate answer"| GM
    AFF -->|"balances/transactions"| SQ
    AFF -->|"narrate verdict (Python already computed it)"| GM
```

No LangGraph, no Chroma — both remain unused dependencies (see `README_ARCHITECTURE.md`'s Overview section). Ingestion is a plain sequential async pipeline, not a graph; chat routing is plain Python control flow, not an agent framework. See [README_ARCHITECTURE.md](README_ARCHITECTURE.md) for the detailed chat routing, fallback-chain, and affordability-pipeline diagrams.
