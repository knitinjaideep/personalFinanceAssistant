# Coral Development Instructions

## Project

Coral is a local-first personal financial assistant.

Primary stack:

- Frontend: Next.js / TypeScript
- Backend: FastAPI / Python
- Database: SQLite
- Local AI: Ollama
- Vector store: existing project implementation

Do not change major infrastructure unless explicitly requested.

## Architecture

Preserve separation between:

Frontend
→ API
→ services/domain logic
→ repositories/data layer
→ database

Business logic must not live primarily inside React components.

Financial calculations must live in deterministic backend/domain services.

Reuse existing services before creating new parallel implementations.

## Database

Keep SQLite unless explicitly instructed otherwise.

Do not migrate Coral to:

- Supabase
- PostgreSQL
- MongoDB
- graph databases

as part of unrelated work.

Database schema changes must be backward compatible with existing Coral data whenever practical.

Use the repository's existing migration strategy.

## Financial correctness

LLMs must never be the authoritative source for:

- totals
- balances
- percentages
- budget variance
- investment contribution calculations
- savings gaps
- financial reconciliation

Those values must come from deterministic code.

Never double count:

- internal account transfers
- checking → savings movements
- checking → brokerage movements
- credit-card payments when purchases are already represented
- investment rollovers
- refunds
- transfers between investment accounts

Raw imported records should be preserved.

Derived classifications should not destructively overwrite source data.

User corrections always take precedence over automated classification.

## Existing functionality

Unless a task explicitly requires it, do not redesign or rewrite:

- Chat
- chat routing
- document ingestion
- PDF parsers
- upload workflow
- Ollama configuration

Regression-test these areas when shared code changes affect them.

## Privacy

Coral contains sensitive financial information.

Never:

- log raw statements unnecessarily
- add real personal financial values to fixtures
- commit financial PDFs
- commit SQLite database files
- commit `.env`
- commit secrets or API keys

Use synthetic test data.

## Engineering standards

Before implementing:

1. inspect the existing implementation
2. determine whether required functionality already exists
3. reuse/refactor before duplicating

For every meaningful change:

- add or update tests
- run relevant tests
- run lint/typecheck when applicable
- inspect git diff

Never disable tests merely to make a change pass.

Never hide errors with broad exception handling unless recovery is intentional and documented.

## Git

Do not:

- force push
- reset --hard
- delete unrelated work
- modify main directly
- deploy production
- merge PRs automatically

Work on the current feature branch.

Create coherent atomic commits only after verification passes.