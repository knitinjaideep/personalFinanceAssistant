# Coral — Current Architecture (pre-redesign audit)

Audit date: 2026-08-09. Scope: everything relevant to a redesign of **Overview / Banking / Investments**. Chat, ingestion, PDF parsing, and Ollama configuration were read only far enough to confirm they are untouched by this audit — see [README_ARCHITECTURE.md](README_ARCHITECTURE.md) for the authoritative chat pipeline docs.

This document states facts about the code as it exists today. It does not propose changes — see [REDESIGN_GAP_ANALYSIS.md](REDESIGN_GAP_ANALYSIS.md) for that.

---

## 1. Frontend architecture

**Stack:** Next.js 14.2 (App Router), React 18.3, TypeScript 6 (`strict: true`), Tailwind 3.4, Zustand 5, Framer Motion 12, Recharts 3.8, lucide-react, react-hot-toast, react-dropzone. No UI component library (no shadcn/Radix/Headless UI) — every card/badge/modal is hand-rolled. No date library. No SWR/React Query.

**Route tree** (`frontend-next/app/`) — single root layout, no nested layouts, no route groups:

```
app/layout.tsx          → RootLayout: loads Manrope/Sora fonts, renders <AppShell>
app/page.tsx             → "/"            Overview/Home  → HomePageClient
app/banking/page.tsx      → "/banking"                   → BankingPageClient
app/investments/page.tsx  → "/investments"                → InvestmentsPageClient
app/documents/page.tsx    → "/documents"                  → DocumentsPageClient
app/chat/page.tsx          → "/chat"                       → ChatWindow (out of scope)
app/upload/page.tsx        → "/upload" — redirects to "/"; upload is a global modal, not a page
app/api/health/route.ts    → route handler
```

`AppShell` (`components/layout/AppShell.tsx`) renders, in order: `UnderwaterBackground` (fixed full-viewport photo/gradient/bubble background), `TopNav` (floating pill nav, active route via `usePathname()`), `<main>{children}</main>`, a lazy-loaded global `UploadModal`, and a `Toaster`. Every `page.tsx` under audit is a ~25-line shell (`marginTop`/scroll-container/`max-w-[1320px]` wrapper) duplicated four times verbatim; `components/layout/PageContainer.tsx` implements this exact wrapper but is unused by any page.

**Component trees (as currently rendered):**

- **Overview** (`HomePageClient`, 378 lines): 6× `MetricCard` ("Data at a Glance" grid), `HomeHeroMascot`, inline `RecentActivityRow`, 3× `SectionHeader`. Fetches only `documentsApi.stats()` + `documentsApi.list(5)` — **no banking or investments data is fetched on Overview today**; the Banking/Investment metric tiles are hardcoded placeholders. "Next Tasks" is a static array, not computed.
- **Banking** (`BankingPageClient`, 454 lines): 6× `MetricCard`, inline `CollapsibleSection`/`AccountRow` (matched against a hardcoded `KNOWN_ACCOUNTS` map), ranked lists for Top Merchants / Spend by Category / Subscriptions, a static "Ask Coral" prompt-links card. Fetches `bankingApi.banking()` once; all totals (`totalSpend`, `netFlow`, etc.) are computed client-side via `.reduce()`. **No chart is rendered anywhere on this page.**
- **Investments** (`InvestmentsPageClient`, 356 lines): 6× `MetricCard`, inline `AccountCard` (matched against hardcoded `KNOWN_ACCOUNTS`), ranked Top Holdings/Gainers/Losers lists, static prompt-links card. Fetches `investmentsApi.investments()` once. The response already includes `allocation` (per-account % of portfolio) and `balance_history` (time series) but **neither is rendered** — dead payload fields ready-made for a donut/line chart. **No chart is rendered anywhere on this page.**

All three page clients are `"use client"`, self-contained, fetch their own data via `useState`/`useEffect` with no shared hook, no cancellation, no cross-page caching — every navigation re-fetches from zero. Contrast with `components/documents/` (7 focused sub-files) and `features/documents/hooks.ts` (a real `useDocuments()` hook with mount-tracking/timeout/polling) — Banking/Investments/Home don't follow either of those patterns.

**Shared components (`components/coral/`):** `GlassCard` (base card, 4 variants), `MetricCard` (KPI tile, 5 sizes, used 6× per page), `SectionHeader`, `EmptyState`/`ErrorState`/`LoadingState` (used by Banking/Investments; Home inlines its own instead), `UnderwaterBackground`/`BubbleField`/`ShimmerLayer` (decorative), `CoralMascot`/`CoralDropletImage` (route-aware mascot system with dedicated PNGs already in `public/mascots/` for banking/investments — **currently wired only into Chat**, not Home/Banking/Investments). `components/motion/` (`FadeIn`, `StaggerGroup`, `FloatingPage`) exist but have zero importers — every page hand-rolls equivalent Framer Motion variants inline instead.

**Design system:** two parallel systems coexist. `tailwind.config.ts` defines a `coral`/`ocean`/`sand` palette, custom radii (`2xl`–`4xl`), rich box-shadows (`glass`, `glow`, `shell`, …), Manrope/Sora fonts, ~13 named gradients, and a keyframe/animation set (`float`, `bubble-rise`, `shimmer`, …) — but this palette is barely used at runtime. Actual component styling reads **CSS custom properties defined in `app/globals.css`** (a separate, darker "deep-sea" palette, `--text-primary`, `--panel-bg`, `--nav-height`, etc., with light/dark variants), which also defines its *own* overlapping-but-differently-named keyframe set (`bubbleRiseAmbient`, `gentleFloat`, `coralDropletFloat`, `heroShimmerSweep`, …). Treat `globals.css` as the source of truth for current visual tokens, not `tailwind.config.ts`.

**API/data layer:** `lib/api-client.ts` is a thin fetch wrapper (`api.get/post/upload/delete`, `ApiError`/`NetworkError`) hitting `BASE_URL = "/api/v1"`, proxied by `next.config.mjs` rewrite to `http://localhost:8000/api/v1/:path*`. Domain-specific typed wrappers live in `features/{banking,investments,documents,upload,chat}/api.ts` (not in `lib/` and not in `types/` — Banking/Investments response types are declared locally inside their own `api.ts` files, not in the shared `types/index.ts`). Relevant calls:
- `bankingApi.banking(months = 12)` → `GET /api/v1/dashboard/banking`
- `investmentsApi.investments()` → `GET /api/v1/dashboard/investments` (no period parameter exists)

**State management:** one Zustand store (`store/appStore.ts`, 119 lines) — `activePage` (seemingly unused; nav derives active state from `usePathname()` instead), `theme` (persisted to `localStorage`), `chatHistory`, `ingestionJobs`, `uploadModalOpen`. **No banking/investments/dashboard data lives in global state** — it's all local `useState` per page. **No budget/plan state exists anywhere** (confirmed by repo-wide grep).

**No date-range picker exists anywhere in the codebase.** The mockups' "August 2026" + "1M/3M/6M/YTD" period control has zero prior art — `bankingApi.banking(months)` accepts a param the UI never surfaces, and `investmentsApi.investments()` has no period parameter at all.

**No `ProgressBar`, `Badge`, `Pill`, or `InsightCard` component exists.** The closest things are a CSS-class-based `.status-badge` (documents only) and copy-pasted "Ask Coral" prompt-link cards at the bottom of Banking/Investments (static suggested questions, not computed insights).

---

## 2. Backend architecture

**Stack:** FastAPI, SQLModel + SQLAlchemy 2.0 + aiosqlite, pdfplumber, Ollama. `alembic` is declared as a dependency but is entirely unused (no `alembic.ini`, no env, zero references in `app/` — custom idempotent migrations are used instead, see §5). `chromadb`/`langgraph`/`langchain*` are declared but not wired into the chat path per `README_ARCHITECTURE.md` (chromadb is used for vector search config plumbing; langgraph/langchain are dead weight). `requirements.txt` and `pyproject.toml` disagree on which of these are listed — treat `pyproject.toml` as authoritative. No `pandas`/`numpy`/chart library as a direct backend dependency; all aggregation is hand-rolled Python (`Decimal`, raw SQL `CAST`/`SUM`).

**Dashboard data flow:**

```
Local folders → Scanner/Upload → Parser Registry → SQLite (canonical tables)
                                                        │
                                    services/dashboard/{investment,banking,summary}_queries.py
                                                        │
                                              api/dashboard.py (assembles JSON)
                                                        │
                                    frontend features/{banking,investments}/api.ts
```

There is also a **second, older, parallel API family** — `api/analytics.py` hitting `app/db/repositories.py` — that duplicates much of what `api/dashboard.py` + `services/dashboard/*` compute (near-identical summary counts, fee summaries, holdings summaries), apparently a prior generation of the same feature that was never removed.

**`api/dashboard.py` endpoints** (all under `/api/v1/dashboard`):
- `GET /summary` → `summary_counts()` — document/statement/transaction/fee/holding/account/institution counts, all-time, no date filter.
- `GET /investments` → 8 sequential (non-concurrent) calls: `investment_portfolio_summary`, `allocation_by_account` (internally re-calls `investment_portfolio_summary` a second time), `top_holdings_by_value`, `top_holdings_by_gain_loss` ×2 (gain/loss), `investment_fees_summary`, `balance_history_by_account`, `document_coverage_investments`.
- `GET /banking?months=12` → 7 sequential calls: `banking_spend_by_month(months)`, `banking_spend_by_category` (no date filter — all-time), `banking_top_merchants` (no date filter), `banking_card_spend_summary` (no date filter), `banking_cash_flow(months)`, `banking_subscriptions` (hardcoded 18-month lookback), `document_coverage_banking`.
- `GET /coverage` → document/statement coverage by institution/product.

**Date filtering is not unified.** Four incompatible paradigms coexist across the dashboard layer alone: (a) a `months` query param → SQLite `date('now', '-N months')`, used by spend-by-month and cash-flow; (b) hardcoded windows baked directly into SQL text with no caller control (`-6 months` fee trend, `-18 months` subscription lookback, `-60 days` staleness cutoff); (c) no filtering at all — "latest snapshot" or all-time totals (most investment queries, spend-by-category, top-merchants, coverage); (d) a completely separate `:date_from`/`:date_to` mechanism used only by the chat SQL layer (`services/sql_query.py`, fed by `normalization.py::normalize_timerange()`). None of these share a common period abstraction.

**Known correctness issue to independently verify before reuse:** `banking_cash_flow()` (`services/dashboard/banking_queries.py:201-234`) labels `outflow = SUM(amount) WHERE amount > 0` and `inflow = SUM(ABS(amount)) WHERE amount < 0`. Every parser in the codebase stores **positive = inflow/deposit, negative = outflow/withdrawal** (e.g. `parsers/bank_of_america/parser.py:209-210`, explicit in the docstring). This function's `inflow`/`outflow` labels therefore appear inverted relative to that convention, and `net = inflow - outflow` would compute the negative of true net cash flow. This directly affects any "Income vs Spent vs Saved" chart the redesign builds on top of it.

---

## 3. Database architecture

SQLite only (`sqlite+aiosqlite:///...`), confirmed via `config/__init__.py::get_database_url()`. No Postgres, no Supabase. Live DB at `backend/data/db/finsight.db` (a stray empty `coral.db` at the repo root is not the live DB — don't confuse the two).

**Canonical tables** (`db/models.py`): `institutions`, `accounts`, `documents`, `statements`, `transactions`, `fees`, `holdings`, `balance_snapshots`, `text_chunks` (+ FTS5 mirror `text_chunks_fts`), `derived_metrics`.

**Bank-specific detail tables**: `morgan_stanley_details`, `chase_details`, `etrade_details`, `amex_details`, `discover_details` (Bank of America and Marcus have none).

**Money is stored as `TEXT` (Decimal-as-string)**, by design, to avoid SQLite float precision loss. Every query re-parses via `CAST(... AS REAL)` in SQL or `Decimal()` in Python — this pattern is repeated ad hoc in nearly every query rather than centralized in one helper.

**Migrations:** no Alembic in practice. `db/engine.py::_apply_migrations()` runs on every startup: (1) idempotent `ALTER TABLE ADD COLUMN` from a hardcoded list, checked via `PRAGMA table_info`; (2) a `sqlite_master` rewrite hack (`PRAGMA writable_schema`) to strip stale `NOT NULL` constraints SQLite can't `ALTER COLUMN` away; (3) a one-off backfill query. Separately, `backend/migrations/phase3_001_add_bucket_and_category_columns.py` is an **orphaned standalone script**, not wired into startup, targeting tables (`buckets`, `derived_monthly_metrics`) that don't exist in the current schema — running it today would raise `sqlite3.OperationalError`. Full copy-paste SQL reference: [queries.sql](queries.sql). Schema/query-location doc: [README_DATABASE.md](README_DATABASE.md).

**`derived_metrics` table is dead.** It's the only table already shaped like a monthly PLAN-vs-ACTUAL rollup (`month_start`, `year`, `month`, balance fields, flow fields, spend fields) — but it has 0 rows, nothing populates it, and it's imported-but-unreferenced in `db/repositories.py`. It's a natural fork point: revive it, or design its replacement, but don't assume it's already working.

---

## 4. Transaction data model

`TransactionModel` (`db/models.py`) fields: `id`, `account_id (fk)`, `statement_id (fk)`, `transaction_date: date`, `description: str`, `amount: str` (Decimal string; **positive = inflow, negative = outflow**, consistent across all parsers), `transaction_type: Optional[str]`, `category: Optional[str]`, `merchant_name: Optional[str]`, `is_recurring: Optional[bool]`, `currency`, `confidence`, `source_page`.

**`transaction_type`** — canonical values in `domain/enums.py::TransactionType`: `deposit, withdrawal, transfer, fee, dividend, interest, trade_buy, trade_sell, tax_withholding, advisory_fee, payment, purchase, refund, other`. No DB-level enum/CHECK constraint — it's free text, populated by per-parser keyword rules (e.g. `parsers/chase/extractor.py::_classify_chase_txn_type`, `parsers/bank_of_america/parser.py::_classify_type`).

**`category`** — canonical values in `domain/enums.py::TransactionCategory`: `groceries, restaurants, subscriptions, travel, shopping, gas, utilities, healthcare, entertainment, education, insurance, transfers, fees, atm_cash, other`. Assigned at ingestion time by `parsers/categorize.py` via keyword matching — a **separate, not-fully-aligned** keyword list from the one used at chat-query time in `services/normalization.py::_CATEGORIES`. Live data distribution: `NULL`→2888 (non-banking rows: trades/dividends/deposits never get categorized), `other`→1235, `shopping`→200, `restaurants`→194, `subscriptions`→126, `groceries`→63, `travel`→43, `gas`→30, `healthcare`→16, `utilities`→13, `insurance`→11, `entertainment`→6. **`education`, `transfers`, `fees`, `atm_cash` never appear** — no keyword ever maps to them in either keyword list, so a query for "education spend" would always return empty.

**Transfers** are not a first-class, linked concept. A credit-card payment gets `transaction_type="payment"` (excluded from "spend" queries via an explicit `transaction_type = 'purchase'` filter, but never linked to the corresponding checking-account debit). An internal transfer (Zelle/wire) gets `transaction_type="transfer"` (107 live rows). **Nothing links the two legs of a transfer or payment** — each row stands alone. There is no `is_transfer_between_own_accounts` flag or transfer-pair table.

**Income is not a first-class concept anywhere in the dashboard layer.** The only income inference in the entire backend is `chat/domains/affordability/data_collector.py::_fetch_monthly_income()` — a one-off heuristic (`AVG` of monthly `SUM(amount) WHERE transaction_type IN ('deposit','credit','payroll') AND amount > 0`) that is not persisted, not exposed via any API, and invisible to Overview/Banking. Note two of its three filter literals (`'credit'`, `'payroll'`) are never actually written by any parser — only `'deposit'` ever matches live data.

---

## 5. Account data model

`AccountModel` fields: `id`, `institution_id (fk)`, `institution_type: str`, `account_number_masked`, `account_name`, `account_type: str = "unknown"`, `currency`, `created_at`.

`domain/enums.py::AccountType`: `ira, roth_ira, advisory, individual_brokerage, 401k, checking, savings, credit_card, unknown`. Already includes `roth_ira`/`401k`, directly relevant to the redesign's Investments sub-goals — but **live data currently has zero rows of either type** (current distribution: `advisory`(1), `checking`(2), `credit_card`(5), `individual_brokerage`(2), `ira`(2) — no `savings`, `roth_ira`, or `401k` accounts populated yet, meaning the ESPP/Roth IRA/401k sub-goal breakdown in the mockups has no backing data today regardless of UI work).

`domain/enums.py::InstitutionType` is out of sync with runtime usage — it lists `morgan_stanley, chase, etrade, amex, discover, unknown` but is **missing `bofa` and `marcus`**, both of which are live, hardcoded strings used throughout `banking_queries.py` and the actual DB (`institutions` table has a row `Bofa | bofa`). Separately, `services/normalization.py`'s canonical slug for Bank of America is `"bank_of_america"`, which disagrees with the DB's actual stored value `"bofa"` — the alias resolver still works for *display* purposes via substring matching, but anything filtering the DB by the *normalized slug* would silently match zero rows.

**Existing account→"bucket" classifiers, and why neither maps to the redesign's Needs/Wants/Savings/Investments buckets:**
1. `config/statement_catalog.py::Bucket` = `"banking" | "investments"` — used purely for upload-folder routing (banking = Bank of America, Chase checking, Marcus; investments = everything else). **This is a document-routing concept, not a budget-allocation concept** — don't conflate the two in the redesign.
2. `chat/domains/affordability/data_collector.py::_classify_row()` — classifies each account into `liquid | investment | retirement | child | other` based on `account_type` (checking/savings → liquid; ira/roth_ira/401k → retirement; individual_brokerage/advisory → investment) plus a name-substring check for `"529"|"child"|"education"` → child. This is the closest existing prior art to a sub-goal classifier, and is worth reusing/extending, but it's presently scoped and used only inside the affordability chat pipeline (never persisted, never exposed via API).

**Neither classifier can currently distinguish "Emergency Fund" vs "House Fund" vs "Child Savings" as separate Savings sub-goals**, even though the statement catalog already has human-readable labels that imply exactly this taxonomy: `marcus/emergency_fund` ("Emergency Fund", not yet parseable — no parser exists, `parseable=False`), `morgan_stanley/house_downpayment` ("House Downpayment", parseable, but catalogued under the `investments` bucket and would classify as `account_type=individual_brokerage/advisory` → the affordability classifier's generic `"investment"` bucket, not a distinguishable "house fund"), `morgan_stanley/arjun_investment` and `marcus/arjun_fun` (apparently a child's accounts — `arjun_fun` under Marcus is not yet parseable). **These are folder/upload labels only** — nothing in the runtime data model tags an account as "this account = the House Fund sub-goal" vs. "this account = general investment brokerage."

---

## 6. Investment data model

`HoldingModel`: `id`, `account_id (fk)`, `statement_id (fk)`, `symbol`, `description`, `quantity`, `price`, `market_value: str`, `cost_basis`, `unrealized_gain_loss`, `percent_of_portfolio`, `asset_class`, `currency`, `confidence`, `source_page`.

`BalanceSnapshotModel`: `id`, `account_id (fk)`, `statement_id (fk)`, `snapshot_date: date`, `total_value: str`, `cash_value`, `invested_value`, `unrealized_gain_loss`, `currency`, `confidence`, `source_page`. Point-in-time snapshot per account per statement period — this is the source for both portfolio totals and the (currently unrendered) balance-history time series.

`FeeModel`: fee records (`fee_category`, `amount`, `annualized_rate`) — advisory/management/late fees, separate from `transactions`.

Investment dashboard queries (`services/dashboard/investment_queries.py`) mostly operate on "latest snapshot"/"latest statement" with **no date-range filtering at all** — a design mismatch with the redesign's month-by-month PLAN vs ACTUAL requirement, which needs a *time series* of contributions per period, not just a current-value snapshot. There is currently no query that computes "how much was contributed to 401(k)/Roth IRA/ESPP/Brokerage this month" — only point-in-time balances and gain/loss.

No contribution-tracking concept exists — the model has balances and holdings, not deposit/contribution events distinguishable from market appreciation. A month-over-month balance delta would conflate contributions with market performance unless computed carefully.

---

## 7. Category system

Two independent, only-partially-overlapping keyword→category mappings exist:
- `parsers/categorize.py::_CATEGORY_KEYWORDS` — runs at **ingestion time**, assigns `transactions.category`.
- `services/normalization.py::_CATEGORIES` — runs at **chat query time**, interprets natural-language category phrases (e.g. "how much on dining") and also provides `category_display_name()` (e.g. canonical `restaurants` → display label `"Dining"` — a naming mismatch to be aware of when labeling UI).

Both are pure rule-based substring matching — no ML, no fuzzy/edit-distance matching, no LLM involvement in category assignment itself. Reasonably reliable for the fixed, small set of merchants/institutions this single-user app currently has, but brittle to new/unrecognized merchants (silently falls through to `other`, which is already 1235 of ~4600 live transaction rows — see §9 for what this means for Needs/Wants classification).

---

## 8. How transfers are represented

Covered in depth in §4. Summary: `transaction_type IN ('transfer', 'payment')` marks *some* internal money movement, but:
- The two legs of a transfer (or a credit-card payment) are **never linked** — no pair ID, no reconciliation.
- Dashboard "spend" queries filter to `transaction_type = 'purchase'` only, which correctly excludes `payment`/`transfer` rows from spend totals — but that same exclusion means the money isn't tracked as going *anywhere* in the current dashboard (it simply isn't counted, not netted against a destination account).
- There's no detection of "this outflow from checking is the same dollar amount, same date, that appeared as an inflow to the Marcus savings account" — i.e., no move-money-between-my-own-accounts reconciliation exists today.

---

## 9. How income is represented

Covered in depth in §4. Summary: **income has no first-class representation anywhere visible to Overview/Banking**. It exists only as a private, unreused heuristic inside the affordability chat pipeline, is not persisted, and none of the three dashboard query modules compute or expose it. A PLAN vs ACTUAL "Income vs Spent vs Saved" chart needs income as reusable, dashboard-visible data — that does not exist today and would be new backend work (see gap analysis).

---

## 10. How transactions are aggregated

Aggregation happens in raw SQL inside `services/dashboard/{banking,investment,summary}_queries.py` (§2) — `GROUP BY strftime('%Y-%m', transaction_date)` for monthly buckets, `GROUP BY category`/`merchant_name`/`account_id` for breakdowns, all with `CAST(amount AS REAL)` for arithmetic since amounts are stored as text. No pandas/numpy; everything is hand-written SQL plus Python `Decimal`/`round()`. Institution-type filter lists (`('chase','amex','discover','bofa','marcral')`-style literals) are **copy-pasted per query** rather than centralized — a would-be single source of truth (`_BANKING_TYPES` constant) is defined but never actually referenced by the functions in the same file.

---

## 11. How date filtering currently works

See §2's "Date filtering is not unified" — four incompatible paradigms (rolling `months` param, hardcoded windows in SQL text, no filtering/latest-only, and a separate `:date_from`/`:date_to` chat-only mechanism). There is no shared backend period abstraction and no frontend period-picker component (§1). Building the mockups' "August 2026 + 1M/3M/6M/YTD" control requires both a new frontend component and a unified backend period parameter that today's dashboard endpoints don't consistently accept.

---

## 12. Current chart libraries

**Recharts 3.8** is installed and is the only charting library in the frontend dependency tree — but it is currently used **only by the chat feature** (`components/chat/AnswerCard.tsx`), not by Overview, Banking, or Investments, which render everything as plain ranked list rows with no charts. This means bar/line/donut visuals for the redesign have zero new-install cost. A **Sankey diagram** (shown in the Banking mockup for the cash-flow visualization) has no built-in Recharts support and no existing dependency — it would require a new library (e.g. `d3-sankey`) or a hand-rolled SVG approach.

---

## 13. Current component hierarchy — Overview / Banking / Investments

See §1 for the full breakdown. In summary, each page is one large (350–450 line) client component that self-fetches data and renders a fixed sequence of `MetricCard`s, inline (non-extracted) sub-components, and static ranked lists — no charts, no progress bars, no plan/actual comparison UI, no shared period filter, inconsistent use of the shared `LoadingState`/`ErrorState`/`EmptyState` trio (Home skips them).

---

## 14. Reusable components

Confirmed reusable as-is for the redesign:
- `GlassCard`, `MetricCard`, `SectionHeader`, `EmptyState`, `ErrorState`, `LoadingState` — the existing visual-primitive layer, used across Banking/Investments today.
- `CoralMascot` / `CoralDropletImage` + route-aware asset map (`lib/mascots.ts`) — banking/investments mascot PNGs already exist in `public/mascots/` but are not currently wired into those pages; directly usable for the mockups' hero-mascot card.
- `UnderwaterBackground`, `BubbleField`, `ShimmerLayer` — decorative background system, page-agnostic.
- `TopNav`, `AppShell` — shared chrome, would need no or minimal changes (CLAUDE.md explicitly allows small shared-layout changes if required).
- Recharts (already a dependency) for bar/line/donut charts.
- `lib/utils.ts::formatCurrency` / `formatCompactCurrency` / `formatDate` — existing formatting helpers.
- `investmentsApi.investments()`'s already-fetched-but-unrendered `allocation` and `balance_history` fields — reusable immediately for a donut/line chart with zero backend change.

Confirmed **not** reusable / needs building: date-range picker, progress-bar component, generic badge/pill component, insight-card component (the current "Ask Coral" cards are static prompt links, not computed insights), any plan/actual/drift UI, any shared page-level data-fetching hook for banking/investments/home (documents has one; the redesign targets don't).

---

## 15. APIs used by Overview / Banking / Investments today

| Page | Calls | Backend endpoint | Notes |
|---|---|---|---|
| Overview | `documentsApi.stats()`, `documentsApi.list(5)` | `GET /documents/stats`, `GET /documents/` | No banking/investments data fetched |
| Banking | `bankingApi.banking(months=12 default, never overridden by UI)` | `GET /api/v1/dashboard/banking?months=12` | Returns `spend_by_month, spend_by_category, top_merchants, card_summary, cash_flow, subscriptions, coverage` |
| Investments | `investmentsApi.investments()` | `GET /api/v1/dashboard/investments` | Returns `portfolio_summary, allocation, top_holdings, top_gainers, top_losers, fees, balance_history, coverage`; no period param exists server-side |

Older, parallel, likely-deprecated-but-still-live: `GET /api/v1/analytics/*` (`api/analytics.py` → `db/repositories.py`) — overlapping summary/fees/holdings/balances endpoints not currently called by the Overview/Banking/Investments frontend, but present and functioning.

---

## 16. Potential technical debt relevant to redesign

1. **No shared date-range abstraction** (backend or frontend) — a prerequisite for any PLAN vs ACTUAL period model (§2, §11).
2. **Likely inflow/outflow sign inversion** in `banking_cash_flow()` — verify before building "Income vs Spent vs Saved" on top of it (§2).
3. **`InstitutionType` enum missing `bofa`/`marcus`**, and a slug mismatch (`bank_of_america` vs live `bofa`) in `normalization.py` — could cause silent zero-result bugs if reused carelessly (§5).
4. **Two parallel, duplicate API generations** (`/api/v1/dashboard/*` vs `/api/v1/analytics/*`) — decide whether `analytics.py` is deprecated before building more on top of either (§2).
5. **`derived_metrics` table is dead** — the one existing table shaped like a monthly rollup has 0 rows and no writer (§3).
6. **Orphaned migration script** referencing nonexistent tables (`buckets`, `derived_monthly_metrics`) — would crash if run; don't assume `migrations/` is authoritative (§3).
7. **Two divergent category keyword lists** (ingestion-time vs chat-time) that never assign `education`/`atm_cash`/`transfers`/`fees` categories in practice — directly affects Needs/Wants category-based rollups (§7, and see Gap Analysis §"category mapping reliability").
8. **`category = NULL` for ~63% of transactions and `other` for another ~27%** in live data — the majority of transactions currently have no usable category for a Needs/Wants split (§4 live distribution).
9. **N+1/redundant dashboard round-trips** — `/dashboard/investments` makes 8 sequential (non-`asyncio.gather`) calls per request, and `allocation_by_account()` redundantly re-runs `investment_portfolio_summary()` (§2).
10. **Two parallel frontend design-token systems** (`tailwind.config.ts` vs `globals.css`) and **two parallel animation-keyframe systems** — pick one source of truth rather than extending the currently-dead Tailwind palette (§1).
11. **Zero `savings`/`roth_ira`/`401k` account rows in live data today** — the Investments sub-goal breakdown (401k/Roth IRA/ESPP/Brokerage) and Savings sub-goal breakdown (Emergency Fund/House Fund/Child Savings) mockups have no backing data yet regardless of UI work, because Marcus (savings/emergency-fund parser) and 529 have no parser, and no account is currently typed `roth_ira`/`401k` (§5, §6).
12. **No account-level tagging for Savings/Investments sub-goals** — existing "bucket" concepts (banking/investments upload routing; liquid/investment/retirement/child affordability classifier) don't distinguish "Emergency Fund" from "House Fund" from generic "investment" (§5).
