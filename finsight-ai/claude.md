# Claude Code Project Guide — FinSight AI Phase 2

## Project Summary
FinSight AI is a **local-first financial intelligence workbench** that analyzes financial statements from institutions such as Morgan Stanley, Chase, and E*TRADE. The stack is fully local: FastAPI, LangGraph, SQLite, Chroma, Ollama, React, TypeScript, Tailwind, and Zustand. Financial data must never leave the device.

Phase 2 transforms the product from a statement parser/chat app into a **transparent, human-in-the-loop, reviewable financial copilot**.

---

## Mission
When working in this repo, optimize for:

1. **Trust** — every extracted or generated answer must be explainable.
2. **Reviewability** — low-confidence facts must be staged for user review.
3. **Local privacy** — no cloud APIs, no remote telemetry, no external inference.
4. **Incremental delivery** — implement in small, testable milestones.
5. **Maintainability** — this project must remain manageable by a solo developer.

---

## Non-Negotiable Rules

### Product Rules
- Never send financial data to external APIs.
- Never add hidden telemetry or analytics.
- Never treat vector store content as canonical truth when structured SQL data exists.
- Never silently overwrite approved or corrected user data.
- Never hide uncertainty. Expose confidence, warnings, and provenance.
- Never blur the distinction between:
  - extracted
  - inferred
  - needs_review
  - approved
  - corrected
  - rejected

### Architecture Rules
- Keep strict separation between:
  - domain
  - persistence
  - services
  - orchestration/agents
  - API
  - frontend
- Prefer typed schemas everywhere.
- Prefer deterministic rules for critical finance logic.
- Prefer explicit repositories/services over giant utility files.
- Favor composition over deep inheritance.
- Use async where it adds value; use `asyncio.to_thread()` for CPU-bound parser/vector operations.
- Use resumable job/state design where background work matters.

### Code Quality Rules
- Python 3.11+, FastAPI, SQLModel, SQLAlchemy 2 style.
- TypeScript everywhere in frontend.
- Add proper exception handling and structured logging.
- Do not produce placeholder “toy” code unless explicitly marked as scaffold.
- Keep files focused and modular.
- Add docstrings to important service/domain classes.
- Add comments only where they genuinely improve clarity.
- Avoid tight coupling between UI and backend response internals.

### UX Rules
- The UI should feel like a **professional AI workbench**.
- Prioritize clarity over visual gimmicks.
- Show progress, evidence, confidence, and warnings.
- Streaming should expose decisions and steps, not raw private reasoning.
- Review workflows must be fast and obvious.
- Structured answers should render as cards, tables, charts, and evidence drawers where appropriate.

---

## Phase 2 Objectives

### 1. Human-in-the-Loop Review Queue
Add staged records and review items for low-confidence or unreconciled extraction results.

### 2. Reconciliation + Integrity Scoring
Introduce a reconciliation subsystem that checks extracted facts against statement totals and emits a trust score.

### 3. Streaming + Trace Upgrade
Upgrade SSE from a thin progress log into a rich execution trace system.

### 4. Correction Store
Persist user corrections and use them to improve future extraction deterministically.

### 5. Structured Answer System
Return typed financial answer objects, not only prose.

### 6. Safer Query Planner
Use intent classification and validated SQL templates before resorting to freeform generation.

### 7. Longitudinal Financial Memory
Generate derived metrics across approved statements for month-over-month analysis.

---

## Preferred Backend Additions
Create or evolve these modules:

- `review_service.py`
- `reconciliation_service.py`
- `correction_service.py`
- `query_planner_service.py`
- `audit_service.py`
- `jobs/` or equivalent durable ingestion runner
- staged models/tables for extracted-but-unapproved records
- derived metrics generation after approval

### Suggested New Tables
- `staged_statements`
- `staged_transactions`
- `staged_fees`
- `staged_holdings`
- `staged_balance_snapshots`
- `review_items`
- `review_sessions`
- `field_corrections`
- `statement_reconciliation_results`
- `derived_monthly_metrics`
- `chat_runs`
- `query_plans`
- `ingestion_jobs`

---

## Preferred Frontend Additions
Create screens/components such as:

- `ReviewQueue`
- `FieldConfidenceTable`
- `CorrectionDiffViewer`
- `StatementIntegrityCard`
- `QueryPlanPanel`
- `EvidenceDrawer`
- `AgentTracePanel`
- `StructuredAnswerCard`
- `RunTimeline`

Frontend expectations:
- React 18 + TypeScript
- Tailwind
- Zustand for focused app state only
- typed API client
- excellent loading/error/empty states
- sticky side panel for trace/evidence when useful

---

## Streaming Event Design Guidance
Events should be meaningful and structured. Favor events like:

- `document_received`
- `parse_started`
- `text_extracted`
- `institution_hypotheses`
- `statement_type_hypotheses`
- `extraction_started`
- `fields_detected`
- `fields_needing_review`
- `reconciliation_started`
- `reconciliation_completed`
- `persist_started`
- `persist_completed`
- `embedding_started`
- `embedding_completed`
- `retrieval_plan_selected`
- `sql_candidate_generated`
- `sql_validated`
- `source_chunks_ranked`
- `response_draft_started`
- `response_complete`

Expose:
- event name
- timestamp
- stage
- human-readable message
- metadata
- warnings
- duration when relevant

Do **not** expose raw chain-of-thought.

---

## Query Planning Rules
For financial questions:
- Prefer SQL-first for exact numeric queries.
- Use vector retrieval for explanation, provenance, and unstructured context.
- Use hybrid only when necessary.
- Avoid direct arbitrary LLM-to-SQL execution.
- Use intent classification and validated query templates.
- Enforce SELECT-only semantics, whitelisted tables/columns, and row limits.

---

## Correction Learning Rules
Corrections should improve the system without full model fine-tuning.

Use corrections to:
- adjust extraction prompts
- enrich institution-specific heuristics
- calibrate confidence
- store prior examples for retrieval during extraction

Do not mutate canonical approved data without explicit user action.

---

## Delivery Style for Claude Code
When asked to implement features:

1. Start with a short architecture recap.
2. Propose the smallest safe milestone.
3. Implement incrementally.
4. Show exact files to create/change.
5. Keep code production-minded.
6. Include tests or validation checks when practical.
7. Avoid giant one-shot rewrites unless explicitly requested.

When ambiguity exists, choose the path that best preserves:
- privacy
- trust
- maintainability
- incremental progress

---

## Definition of Done for Phase 2
A feature is only complete when it includes the following where applicable:

- typed models/schemas
- service layer integration
- route or UI integration
- logging and error handling
- tests or validation plan
- evidence/provenance surfaced to user
- confidence/review state surfaced to user

---

## Final Reminder
This project is not trying to be a generic chatbot.
It is trying to be a **local, high-trust, human-reviewed financial intelligence system**.
Every implementation choice should reinforce that identity.
