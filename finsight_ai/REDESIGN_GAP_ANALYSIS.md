# Coral — Redesign Gap Analysis

Audit date: 2026-08-09. Companion to [CURRENT_ARCHITECTURE.md](CURRENT_ARCHITECTURE.md). Target: redesigning Overview, Banking, and Investments around a **PLAN → ACTUAL → DRIFT → ACTION** model (Needs 50% / Wants 20% / Savings 15% / Investments 15%, with Savings sub-goals — Emergency Fund 5% / House Fund 5% / Child Savings 5% — and Investments sub-goals — 401(k) 6% / Roth IRA 4% / ESPP 3% / Taxable Brokerage 2%), based on the three mockups in `docs/design/`.

This is an audit only. No implementation code is proposed. Where something already exists and works, this document says so explicitly and does not propose rebuilding it.

---

## What already exists and can be reused

**Frontend visual system** — `GlassCard`, `MetricCard`, `SectionHeader`, `EmptyState`/`ErrorState`/`LoadingState`, `UnderwaterBackground`, `TopNav`/`AppShell`, the underwater/coral aesthetic in `globals.css`, and Framer Motion for stagger/entrance animation are all production-ready and match the mockups' visual language closely (rounded glass cards, soft gradients). No new dependency is needed for cards, layout chrome, or motion.

**Mascot system** — `CoralMascot`/`CoralDropletImage` plus route-aware PNG assets for banking/investments already exist in `public/mascots/`; they're simply not wired into Banking/Investments pages yet (only Chat uses them today). This is close to a direct match for the mockups' hero-mascot card.

**Charting** — Recharts is already an installed dependency (used today only by Chat), so bar charts, line charts, and donut charts for the redesign have no new-install cost. Only the Banking mockup's Sankey-style cash-flow diagram has no existing library support.

**Investments allocation & history data** — `GET /api/v1/dashboard/investments` already returns `allocation` (per-account % of portfolio, ready for a donut chart) and `balance_history` (time series, ready for a line chart). Both are fetched today and simply never rendered. This is a near-zero-cost win independent of any PLAN vs ACTUAL work.

**Account type taxonomy** — `domain/enums.py::AccountType` already includes `roth_ira` and `401k` as valid values, and `individual_brokerage`/`advisory` cover ESPP/Taxable Brokerage conceptually. The enum shape is compatible with the target sub-goal breakdown even though no live data populates those types yet (see Risks).

**Account-bucket classification prior art** — `chat/domains/affordability/data_collector.py::_classify_row()` already classifies accounts into `liquid | investment | retirement | child | other` from `account_type` plus name heuristics. It's scoped to one chat feature today, but its logic is a reasonable starting point to extend into a Savings/Investments sub-goal classifier rather than starting from nothing.

**Category taxonomy** — `TransactionCategory` already has a reasonable category list (`groceries, restaurants, subscriptions, travel, shopping, gas, utilities, healthcare, entertainment, education, insurance, transfers, fees, atm_cash, other`) and two working (if imperfect) keyword-based classifiers already assign it at ingestion time. This is usable as an input to a Needs/Wants mapping layer — it does not need to be rebuilt from scratch, only extended (see "what needs schema changes").

**Statement catalog labels** — `config/statement_catalog.py::ACCOUNT_CATALOG` already has human-readable labels that closely mirror the target sub-goals: "Emergency Fund" (Marcus), "House Downpayment" (Morgan Stanley), and per-child account labels ("Arjun Investment", "Arjun Fun"). These are upload-routing labels, not runtime tags, but they're a ready-made naming reference for whatever new goal-tagging mechanism gets built.

**SQLite + FTS5 + no external vector DB** — nothing about this redesign requires a database migration. All new data (plan targets, goal tags, income tracking) fits comfortably in SQLite as new tables/columns, consistent with the "no Supabase, no DB migration" constraint.

---

## What is missing

- **No budget/plan/goal/target-percentage data model at all** — confirmed by exhaustive grep across the entire backend and frontend. This is the single largest net-new surface area. Nothing to reuse; this is genuinely greenfield.
- **No income as a first-class, reusable, dashboard-visible concept.** It exists only as a private one-off heuristic inside the affordability chat pipeline (`_fetch_monthly_income()`), not persisted, not exposed via any API, and two of its three filter values never match real data.
- **No transfer-pair linkage.** Money moving between the user's own accounts (paycheck → checking, checking → savings, checking → credit-card payoff) is stored as independent, unlinked rows. A PLAN vs ACTUAL Savings/Investments tracker needs to recognize "this outflow from checking became a deposit into the Emergency Fund," which nothing currently computes.
- **No account-level goal tagging** distinguishing "this savings account is the Emergency Fund" vs "this brokerage account is the House Fund" vs "this is just general investing." The closest things (upload-routing `bucket`, affordability `liquid/investment/retirement/child` classifier) don't reach this granularity (see CURRENT_ARCHITECTURE.md §5).
- **No contribution-vs-market-appreciation distinction** for investment accounts — balances are point-in-time snapshots; nothing separates "you contributed $500 this month" from "the market moved your balance by $500 this month." The Investments mockup's "Plan vs Actual Contributions" bars need contribution events, not just balance deltas.
- **No date-range/period picker component** on the frontend, and no unified period parameter on the backend (see CURRENT_ARCHITECTURE.md §11). The mockups' month selector + 1M/3M/6M/YTD pills has zero prior art.
- **No progress-bar, generic badge/pill, or insight-card component.** The mockups lean heavily on progress bars (Plan vs Actual, per-sub-goal target rings) and insight cards ("Overspending in Wants," "On track for 401(k)") — both need to be built from scratch, though they can be built on top of the existing `GlassCard`/design-token system.
- **No Needs/Wants mapping layer.** `TransactionCategory` exists, but nothing maps `groceries → Needs`, `restaurants → Wants`, etc. — that mapping does not exist anywhere in the codebase today.
- **No Sankey/flow-diagram capability** for the Banking page's cash-flow visualization — would need a new dependency or hand-rolled SVG.

---

## What needs schema changes

These require new tables/columns (SQLite, additive, idempotent-migration style consistent with the existing `_apply_migrations()` pattern — no Alembic needed, no DB engine change):

1. **A plan/budget table** — something like `budget_plans` (or per-period `budget_targets`): allocation percentages for Needs/Wants/Savings/Investments and their sub-goals (Emergency Fund/House Fund/Child Savings, 401k/Roth IRA/ESPP/Brokerage), versioned by effective date so historical PLAN vs ACTUAL comparisons remain correct if the plan changes later. The now-dead `derived_metrics` table is schema-adjacent (month_start/year/month + flow fields) and is worth evaluating as a revival candidate for the ACTUAL side of this, rather than building a second parallel rollup table.
2. **A Needs/Wants category-mapping table or config** — maps each `TransactionCategory` (and ideally each `transaction_type`) to one of Needs/Wants/Savings/Investments/Excluded. Could be a simple static Python dict initially (consistent with how `normalization.py`/`categorize.py` already work) rather than a DB table, but it needs to exist somewhere as an explicit, auditable mapping — not inferred ad hoc.
3. **Account-level goal tagging** — a new column on `accounts` (e.g. `goal_tag: Optional[str]`) or a small side table, so a specific Marcus/Morgan Stanley account can be marked "this is the Emergency Fund" / "this is the House Fund" / "this is Arjun's Child Savings" distinctly from "this is just a brokerage account." Needed to make the Savings/Investments sub-goal breakdown possible with per-account precision rather than category-level guessing.
4. **A transfer-linkage mechanism** (lower priority, higher risk — see Risks) — at minimum, a way to flag "this transaction is an internal transfer, exclude it from both spend and income," ideally eventually pairing legs. Even a conservative first pass (reliably excluding `transfer`/`payment` types from Needs/Wants totals) needs verification that the exclusion is complete and doesn't double-count.
5. **Income as a queryable, persisted-or-reliably-derivable concept** — either a new `income_events` concept, or (more consistent with the rest of this deterministic-SQL codebase) a well-defined, dashboard-exposed SQL view/query function that reuses and hardens the existing `_fetch_monthly_income()` heuristic (fixing its dead `'credit'`/`'payroll'` filter values first).
6. **Institution/account type taxonomy fixes** — add `bofa`/`marcus` to `InstitutionType`, reconcile the `bank_of_america` vs `bofa` slug mismatch in `normalization.py`, before building new features on top of institution-type filtering (small fix, but a prerequisite — silent zero-result bugs are worse than loud ones).

---

## What can be derived dynamically (no schema change needed)

- **ACTUAL spend by Needs/Wants/Savings/Investments** — once a category→bucket mapping exists (item 2 above), actual amounts can be computed live from existing `transactions`/`category` data via SQL `GROUP BY`, the same way `banking_spend_by_category()` already works today. No new fact table is strictly required for a first version — a mapping layer plus existing aggregation queries gets you there.
- **DRIFT** (Target vs Actual delta) — pure arithmetic once PLAN (schema item 1) and ACTUAL (derivable) both exist. No new persistence needed beyond the plan table itself.
- **Portfolio allocation donut** — already computed server-side (`allocation_by_account`), just needs frontend wiring (§ "What already exists").
- **"Where You're Off Plan" table** (mockup: Housing/Groceries/Dining/Shopping/Transportation with Target/Actual/Drift) — derivable the same way as bucket-level drift, once category-level targets are added to the plan schema (a natural extension of item 1, not a separate concept).
- **Simple "next month" suggestions** (e.g. "increase savings by $X to stay on track") — can be computed deterministically from PLAN − ACTUAL, consistent with this codebase's existing philosophy of deterministic math + LLM-narration-only (already the pattern used in `chat/domains/affordability/`). No new ML/LLM-driven recommendation engine is needed to hit the mockups' insight-card copy style.

---

## What new APIs will be needed

- `GET /api/v1/dashboard/plan` (or similar) — returns the current active budget plan (targets by bucket and sub-goal).
- `POST/PUT` for editing the plan (the mockups show "Edit plan" / "View details" affordances) — even if plan editing is out of scope for this redesign phase, the read endpoint is needed for Overview/Banking/Investments to render targets at all.
- `GET /api/v1/dashboard/overview` (new, or an extension of `/summary`) — Income vs Spent vs Saved time series, Plan vs Actual per bucket, would likely aggregate across both banking and investment data, which today are computed in two separate query modules with no shared caller.
- Extend `GET /api/v1/dashboard/banking` (or add a new endpoint) with: income (currently absent), Needs/Wants/Savings bucket rollups, "off plan" category table, a corrected/relabeled cash-flow response.
- Extend `GET /api/v1/dashboard/investments` with: per-sub-goal (401k/Roth IRA/ESPP/Brokerage) contribution-vs-target data — this depends on the contribution-tracking gap above and may need to ship as "target vs current balance" rather than true monthly-contribution tracking in a first version, given contributions aren't currently distinguishable from market movement.
- A period parameter needs to be added consistently across whichever endpoints don't already have one (`/dashboard/investments` has none today; `/dashboard/banking` has one but the frontend never surfaces it).

---

## What old UI should eventually disappear

- The four duplicated `page.tsx` wrapper shells should eventually collapse into the already-existing-but-unused `PageContainer.tsx`.
- `HomePageClient`'s hardcoded "Banking Docs"/"Investment Docs: Upload to populate" placeholder tiles should go away once Overview actually fetches banking/investment data.
- The static `INSIGHT_PROMPTS` "Ask Coral" cards at the bottom of Banking/Investments (copy-pasted between the two pages) are natural candidates to be replaced by real computed insight cards once the plan/actual/drift data exists — though they could also stay as a secondary "ask a follow-up" affordance alongside new insight cards, that's a product decision, not an audit finding.
- The inline, non-extracted `CollapsibleSection`/`AccountRow` (Banking) and `AccountCard` (Investments) components matched against hardcoded `KNOWN_ACCOUNTS` maps are fragile (any account rename breaks the match) and are reasonable to replace during the redesign rather than preserve.
- `components/motion/{FadeIn,StaggerGroup,FloatingPage}.tsx` and `components/layout/PageTransition.tsx` are currently dead code (zero importers, or an unreachable branch) — worth removing rather than carrying forward, though this is cleanup, not a redesign blocker.
- Whether the older `/api/v1/analytics/*` endpoint family should be deprecated is a decision for the team, not dictated by this redesign, but it's worth resolving before adding a third generation of overlapping summary endpoints.

---

## Risks

### Risk: transfer double-counting
Because transfer/payment legs aren't linked, a naive "sum all outflows and bucket them into Needs/Wants/Savings/Investments" risks either (a) double-counting money that moves checking → savings → back to checking-adjacent spend, or (b) undercounting Savings if transfers into a savings/investment account aren't reliably recognized as "this month's Savings contribution." The current dashboard sidesteps this by simply excluding `transfer`/`payment` from spend totals — that's safe for Needs/Wants, but Savings/Investments ACTUAL cannot use the same simple exclusion, since for those buckets the transfer *is* the signal, not noise. This needs careful, explicit design before implementation — it is the single highest-risk correctness area for this redesign.

### Risk: paycheck deductions (401k/insurance withheld pre-deposit)
If any of the user's income sources have 401(k) contributions, health insurance, or other deductions withheld *before* the paycheck hits checking (typical for W-2 employment), then the "deposit" amount seen in `transactions` already excludes that money — it never appears as an outflow anywhere in the bank data. A PLAN vs ACTUAL Investments tracker built purely from observed transactions would silently under-report 401(k) contributions (or worse, only see 401(k) balance growth with no corresponding "contribution" transaction to point to). This needs to be explicitly reasoned about: does 401(k) ACTUAL come from account balance deltas (contaminated by market movement) or from an assumed-but-unverified gross-income figure? Neither data source that exists today cleanly answers this.

### Risk: investment contributions vs. market performance
Directly related to the above — `balance_snapshots` captures point-in-time totals, not itemized contribution events. A month where the market drops 5% could show as "behind on your 401(k) contribution target" even if the actual contribution was on-plan, and vice versa in an up month. Any Investments PLAN vs ACTUAL feature needs to either (a) find/derive a contribution-only signal (e.g. from statement line items already captured per-institution in the detail tables, if such line items exist — not confirmed in this audit and would need follow-up), or (b) be explicit in the UI that it's showing balance-vs-target rather than contribution-vs-target, which is a materially different (and less accurate) claim.

### Risk: transaction classification / category reliability
Live data shows **~63% of transactions have `category = NULL`** and another ~27% are bucketed into the catch-all `other` — meaning roughly 90% of transactions currently have no usable category for a Needs/Wants split. The NULL bucket is dominated by non-purchase transaction types (trades, dividends, deposits) which arguably shouldn't be categorized as Needs/Wants anyway (they're not spend), but the `other` bucket (1235 rows) is a real gap — those are real transactions that fell through both keyword-matching category assigners. **A Needs/Wants breakdown built directly on today's `category` field will show a large, unexplained "uncategorized" chunk unless this is addressed first**, either by improving the keyword lists, adding an "Unclassified — tell us Needs or Wants" UI affordance (consistent with the mockup's "Looks right / Change" pattern already sketched in the Banking mockup's "Needs vs Wants Review" section — that pattern may be less a nice-to-have and more a load-bearing necessity given current data quality), or both.

### Risk: category mapping reliability for Needs/Wants specifically
Even where a category *is* assigned, category→Needs/Wants is not always a clean 1:1 mapping in reality (e.g. "shopping" could be a Need — replacing a broken appliance — or a Want — discretionary purchase; "travel" is almost always a Want but could be work travel). The mockup itself seems to anticipate this with its per-transaction "Looks right / Change" override UI. Treat category→bucket as a *default heuristic requiring user override*, not a guaranteed-correct classifier, in both the UI design and any completeness claims made to the user.

### Risk: sign-convention bug in existing cash-flow query
As documented in CURRENT_ARCHITECTURE.md §2, `banking_cash_flow()`'s inflow/outflow labels appear inverted relative to the rest of the codebase's sign convention. If the redesign's "Income vs Spent vs Saved" chart or any Overview cash-flow number reuses this function as-is, it risks displaying backwards numbers. This should be verified against real account statements (not just code-read) before reuse, and is a small, isolated, easy-to-verify fix — but it must be caught before it propagates into a user-facing headline number.

### Risk: sparse/zero data for several target sub-goals
Live data has zero accounts typed `savings`, `roth_ira`, or `401k`, and Marcus (the emergency-fund/general-savings institution) plus 529 have no parser at all yet. The Investments and Savings sub-goal breakdowns in the mockups will show entirely empty/placeholder states for several rows regardless of how well the redesign is built, until (a) a Marcus parser exists, and (b) the relevant Morgan Stanley/other accounts are correctly typed. This is a data-completeness constraint, not a UI bug — worth setting expectations that the full mockup won't be "live" end-to-end until ingestion gaps are separately closed (explicitly out of scope for this redesign per the constraints given, but worth flagging as a dependency).

---

## Suggested implementation sequence

This is a sequencing suggestion based on dependency order and risk front-loading, not a committed plan — no implementation should start without separate design/planning for the schema and API work.

1. **Fix the small, isolated correctness issues first** (cheap, de-risks everything downstream): verify/fix the `banking_cash_flow()` sign labeling; add `bofa`/`marcus` to `InstitutionType`; reconcile the `bank_of_america`/`bofa` slug mismatch.
2. **Design and land the category→Needs/Wants/Savings/Investments mapping** (config-level, not necessarily a DB table yet) and measure real coverage against live data — this determines whether the "90% uncategorized" risk above is as bad as it looks once trade/dividend/deposit rows are correctly excluded from the denominator.
3. **Design and land the plan/budget schema** (item 1 under "what needs schema changes") — targets by bucket and sub-goal, versioned by effective date. Ship a read-only API before any edit UI.
4. **Wire up the already-fetched-but-unrendered `allocation`/`balance_history` investment data** — pure frontend work, zero backend dependency, immediate visible progress, good early win to validate the new chart/visual patterns before the harder plan/actual work.
5. **Build the Overview page's Income vs Spent vs Saved + Plan vs Actual bucket rollup**, gated on income being derivable (harden `_fetch_monthly_income()` or its successor) and the category mapping from step 2. This is the highest-value, highest-complexity piece — sequence it after the cheaper wins above so the visual language and data plumbing are already validated.
6. **Tackle transfer/paycheck-deduction handling explicitly** (the two biggest correctness risks) before trusting any Savings/Investments ACTUAL number in production — this may end up scoped as "best-effort with a visible confidence/caveat in the UI" rather than fully solved, consistent with this codebase's existing pattern of explicit data-quality notes (`data_quality_notes` in the affordability pipeline is a good precedent to follow here).
7. **Account-level goal tagging** for Savings/Investments sub-goals — needed before per-sub-goal (Emergency Fund vs House Fund, 401k vs Roth IRA) breakdowns can be anything more than category-level guessing.
8. **Date-range picker + unified period parameter** — needed across all pages, but can be built in parallel with steps 3–7 since it's largely orthogonal (frontend component + backend param threading, not new business logic).
9. **New/derived UI elements** (progress bars, insight cards, drift table, Sankey diagram) — build once the underlying data contracts from steps 2–7 are stable, to avoid rebuilding UI against a moving data shape.

---

## Summary

### READY TO REUSE
- `GlassCard`, `MetricCard`, `SectionHeader`, `EmptyState`/`ErrorState`/`LoadingState`, `UnderwaterBackground`, `TopNav`/`AppShell`, Framer Motion patterns, `globals.css` design tokens
- `CoralMascot` system + existing banking/investments mascot assets (just not wired in yet)
- Recharts (already installed, idle on these three pages)
- `investmentsApi.investments()`'s `allocation` and `balance_history` fields (fetched, unrendered)
- `TransactionCategory` / `AccountType` enum shapes (already include `roth_ira`/`401k`)
- `chat/domains/affordability/data_collector.py`'s liquid/investment/retirement/child classifier as a starting point
- SQLite as-is — no DB migration needed for any of this

### NEEDS MODIFICATION
- `banking_cash_flow()` — verify/fix inflow/outflow sign labeling
- `domain/enums.py::InstitutionType` — add `bofa`/`marcus`
- `services/normalization.py` — reconcile `bank_of_america`/`bofa` slug mismatch
- `_fetch_monthly_income()` — harden and promote from a private chat heuristic to a reusable, dashboard-exposed query; fix dead `'credit'`/`'payroll'` filter values
- Category keyword lists (`parsers/categorize.py`, `services/normalization.py`) — improve coverage given ~27% of banking transactions currently land in `other`
- `HomePageClient` — wire real banking/investments data instead of hardcoded placeholder tiles
- `BankingPageClient`/`InvestmentsPageClient` — replace hardcoded `KNOWN_ACCOUNTS` matching with real account data joins

### NEEDS TO BE BUILT
- Budget/plan schema + read API (targets by bucket and sub-goal, versioned)
- Category → Needs/Wants/Savings/Investments mapping layer
- Account-level goal tagging (Emergency Fund vs House Fund vs generic investment, per-child accounts)
- Income as a first-class, dashboard-exposed concept
- Transfer/payment-leg-aware Savings/Investments contribution tracking (or an explicit, honest best-effort approximation)
- Date-range picker component + unified backend period parameter
- Progress-bar, badge/pill, and insight-card components
- Sankey/flow-diagram visualization (new dependency or hand-rolled)
- Plan vs Actual / Drift computation and "Where You're Off Plan" table
- New Overview endpoint aggregating across banking + investment data

### RISKS
- **Transfer double-counting** — highest-priority correctness risk; current exclude-transfers approach works for Needs/Wants but breaks for Savings/Investments ACTUAL
- **Paycheck deductions** (pre-tax 401k/insurance) invisible to transaction data — 401(k) ACTUAL cannot be cleanly derived from observed transactions alone
- **Contribution vs. market performance** conflation in investment balance deltas
- **~90% of transactions currently uncategorized or `other`** — Needs/Wants breakdown will show a large unexplained bucket unless addressed, or explicitly surfaced with a user-correction affordance
- **Category→bucket mapping is inherently fuzzy** (e.g. "shopping" could be Need or Want) — needs to be designed as an overridable default, not a guaranteed classifier
- **Sign-convention bug** in existing cash-flow query, if reused without verification
- **Sparse live data** for several target sub-goals (no `savings`/`roth_ira`/`401k`-typed accounts yet, Marcus/529 unparsed) — several mockup rows will be empty regardless of UI quality until ingestion gaps close (out of scope here, but a real dependency)

### RECOMMENDED PR ORDER
1. Small correctness fixes (cash-flow sign, enum/slug gaps) — cheap, de-risks everything else
2. Category→bucket mapping + coverage measurement against live data
3. Plan/budget schema + read-only API
4. Frontend: wire existing unused `allocation`/`balance_history` data (fast, visible win)
5. Overview: Income vs Spent vs Saved + Plan vs Actual rollup
6. Transfer/paycheck-deduction handling for Savings/Investments ACTUAL (explicit best-effort, with visible data-quality caveats)
7. Account-level goal tagging for sub-goal breakdowns
8. Date-range picker + unified period parameter (parallelizable with 3–7)
9. New UI primitives (progress bars, insight cards, drift table, Sankey) once data contracts are stable
