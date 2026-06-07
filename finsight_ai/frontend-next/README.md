# Coral — Frontend (Next.js)

The Phase 2 redesigned frontend for the Coral local-first personal finance assistant.

## Prerequisites

- Node.js 18+
- The Coral **backend** running on port `8000` (see `../backend/`)
- Ollama running locally on port `11434` (optional — only needed for chat)

## Setup

```bash
cd frontend-next
npm install
```

Copy the environment file and set your backend URL if needed:

```bash
cp .env.local.example .env.local
```

The default config points to `http://localhost:8000`. No changes needed for local dev.

## Run in development

```bash
npm run dev
```

Opens at **http://localhost:3001**

The dev server proxies `/api/v1/*` to `http://localhost:8000/api/v1/*` via `next.config.mjs`.

## Build for production

```bash
npm run build
npm start
```

## Routes

| Route | Description |
|---|---|
| `/` | Home — command center with metrics and quick actions |
| `/banking` | Banking — spending summary, account groups, subscriptions |
| `/investments` | Investments — portfolio overview, accounts, holdings |
| `/documents` | Documents — bucketed library grouped by institution and year |
| `/chat` | Chat — ask Coral anything about your finances |
| `/upload` | Upload — single and bulk document upload |

## Tech stack

- **Next.js 14** App Router
- **TypeScript**
- **Tailwind CSS** with custom Coral design tokens
- **Framer Motion** for animations
- **Zustand** for chat history and theme state
- **lucide-react** for icons
- **react-dropzone** for file upload
- **react-hot-toast** for notifications

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | _(proxied via next.config.mjs)_ | Backend API base URL |

See `.env.local.example` for all options.

## Theme

The app supports **dark mode** (default, deep ocean navy) and **light mode** (soft aqua/pearl). Toggle with the switch in the sidebar.

## Backend must be running

The frontend is a pure UI layer — all data comes from the Coral FastAPI backend. Start the backend first:

```bash
# From the repo root
cd backend
uvicorn app.main:app --reload --port 8000
```
