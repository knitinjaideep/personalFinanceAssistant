# Plan vs Actual Engine

This is the PR 04 (M1 — Coral redesign) deliverable: `PLAN vs ACTUAL = DRIFT`.

It consumes the classification layer PR 03 built
(`docs/TRANSACTION_CLASSIFICATION.md` — `master_bucket` /
`classification_category` / `cash_flow_type` on every transaction) and the
Financial Plan model (`docs/FINANCIAL_PLAN_MODEL.md` — versioned,
effective-dated Needs/Wants/Savings/Investments targets) and produces, for any
requested period, a deterministic target-vs-actual-vs-variance-vs-status
result for every master bucket, with recursive drill-down into categories and
merchants.

Everything here is Decimal arithmetic in Python. **The LLM is never involved
in computing a total, a percentage, a variance, or a status** — it may only
ever narrate a number this engine already produced (see
`.claude/skills/coral-redesign/references/accounting-invariants.md`).

## Module layout

- `app/domain/plan_vs_actual.py` — pure, DB-free calculation engine (Period,
  status thresholds, aggregation, completeness metadata, result shapes).
  Fully unit-testable without a database.
- `app/services/plan_vs_actual.py` — wires the engine to the database:
  resolves the plan version for the period, backfills any never-classified
  transaction, loads transactions + their accounts, and calls the domain
  functions. No FastAPI imports (usable from chat, a future scheduled job,
  etc.), matching `app.services.financial_plan`.
- `app/api/plan_vs_actual.py` — thin FastAPI routes
  (`GET /api/v1/plan-vs-actual`, `.../buckets/{bucket}`, `.../merchants`)
  that only open a session and translate errors.

## Plannable Income

**Definition:** the sum of every transaction in the period classified as
`cash_flow_type == income` (payroll/direct-deposit, see PR 03 tier 3h),
across every account. See `compute_plannable_income()`.

This is the sole denominator for every target-$/actual-% calculation in the
engine. It is intentionally defined as *observed cash landing in the user's
accounts*, and nothing else — Coral never estimates, backfills, or infers a
gross-pay figure.

**Known, documented limitation:** payroll-deducted contributions (401(k),
ESPP) are withheld from a paycheck *before* net pay reaches checking, so they
never appear as an `income` transaction anywhere in Coral's data. Plannable
Income can therefore understate true gross income whenever such deductions
exist. Coral does **not** try to reconstruct gross pay — doing so would mean
inventing a number invariant #10 explicitly forbids. Instead:

- `payroll_deduction_signal()` detects when a canonical 401(k)/ESPP
  contribution leg exists directly on an investment/retirement account (the
  only place such a contribution can appear — see below).
- When detected, `CompletenessMetadata.payroll_deduction_signal_detected` is
  set `True` with an explanatory note, and the overall result is marked
  incomplete (`completeness.is_complete == False`) rather than silently
  presenting a partial percentage as if it were the whole picture.

If `plannable_income <= 0` for a period (no income observed at all), the
engine still reports every bucket's real `actual_amount` and its
`target_percentage` (the plan is known regardless) — but reports
`actual_percentage`, `target_amount`, `variance_amount`,
`variance_percentage_points` and `status` as `None`/`DriftStatus.UNKNOWN`
rather than dividing by zero or fabricating a `$0.00` target. A `$0` target
would surface as "Target $0 / Actual $500 / +$500 over plan", which is
fabricated precision for what is almost always missing payroll coverage.

**Scoping caveat:** passing `account_id` narrows both the actuals *and* the
Plannable Income denominator to that one account. Scoping to an account where
no payroll lands (a credit card, a brokerage) therefore yields
`income_observed=False` and `UNKNOWN` statuses rather than a percentage
computed against a partial denominator. Household-level Plan vs Actual must be
requested without `account_id`.

## Cross-statement double counting (the PR 03 reviewer finding this PR must resolve)

PR 03's classifier cannot see across statements. A checking → brokerage (or
checking → savings) transfer is visible **twice** whenever both the source
and destination statements have been ingested:

- the checking/depository account shows an **outflow** — classified
  `investment_contribution` / `savings_contribution` because, from that
  account's perspective, money is leaving toward a savings/investment
  destination;
- the savings/investment account shows the matching **inflow** — classified
  the same way, because money is arriving.

Both legs are individually correct classifications; the problem is only that
naively summing every `investment_contribution` row in the period would count
the same real-world dollar twice.

### The rule (resolved decision — Option C, coverage-aware hybrid)

**Status: RESOLVED**, see `docs/coral-redesign/BLOCKED.md` (user decision,
2026-08-13). The engine originally counted the destination leg
unconditionally ("destination-leg-only"). That rule is correct and
non-double-counting, but produces a structural **$0.00** Savings actual for
any period where the savings/investment side has no ingested transaction
coverage — including Coral's real account coverage today, where the Marcus
HYSA accounts and the 529 are catalog-only stubs with no parser
(`parseable=False`), so no `account_type == "savings"` row can ever exist.
Meanwhile the checking-side origin leg — the one PR 03 reliably classifies —
was exactly the leg being discarded.

**The rule now (coverage-aware hybrid):** for each of the Savings and
Investments buckets *independently*, count the destination leg **when that
bucket's destination account type has ingested transaction coverage for the
period**; otherwise fall back to the origin leg.

Concretely (`compute_transfer_leg_coverage()` + `is_canonical_contribution_leg()`):

1. Compute `savings_has_coverage` / `investment_has_coverage` once per period
   — True when ANY transaction that period lives on an account whose
   `account_type` is in `SAVINGS_ACCOUNT_TYPES` / `INVESTMENT_ACCOUNT_TYPES`
   (regardless of that transaction's own classification — a $0 monthly-fee
   line inside the Marcus account still proves the Marcus statement was
   ingested).
2. If the relevant side **has coverage**: only the transaction that lives on
   that destination account type is canonical — exactly the original rule.
   The origin (checking/credit) leg is excluded as a duplicate.
3. If the relevant side **has no coverage**: the origin leg (checking/credit
   side, classified `savings_contribution`/`investment_contribution`) is
   canonical instead — there is no destination statement to have
   double-counted against, so dropping it would silently understate the
   user's real contribution.

The excluded origin leg (case 2) is **never silently dropped**: it is
surfaced via `CompletenessMetadata.origin_only_transfer_legs_count` /
`_amount`. Under this rule that field is only ever populated in the *healthy*
case — coverage exists and dedup worked — not as a signal of missing data
(see the Completeness metadata section below).

**Worked example (the one that blocked this PR):** a Chase checking
statement shows `TRANSFER TO MARCUS SAVINGS -1500.00`; no Marcus statement
has ever been ingested. `savings_has_coverage` is `False` (no
`account_type == "savings"` transaction exists anywhere this period), so the
checking-side leg is canonical: **Savings actual $1,500.00**, not $0.00.
Once a Marcus statement is later ingested for the same period,
`savings_has_coverage` flips to `True` and the destination (Marcus) leg
becomes canonical instead, with the checking leg correctly excluded as a
duplicate — no manual migration needed, the same rule just reads different
data. Covered end-to-end in
`backend/tests/test_plan_vs_actual.py::test_blocked_md_worked_example_savings_actual_is_1500_not_0`.

### Why coverage-aware, not one side always

1. **It also correctly handles payroll-deducted contributions with no
   symmetry problem.** A 401(k)/ESPP contribution withheld from payroll has
   *no* checking-side leg at all — it only ever appears once, directly on the
   retirement/brokerage account. Since that account having a transaction
   this period is itself what sets `investment_has_coverage = True`, the
   destination leg (the only leg that exists) is always canonical — no
   special-casing required.
2. **It avoids fragile cross-statement entity resolution.** The alternative
   (match a checking outflow to its brokerage inflow by date/amount/
   institution) requires fuzzy matching across two independently-parsed
   statements — exactly the kind of heuristic matching most likely to
   silently misfire. Coverage is a static, per-period boolean check with zero
   false-match risk; no amount/date pairing is ever attempted.
3. **It is correct for Coral's real account coverage today** (checking
   ingested, Marcus/529 not parseable) **and stays exactly as correct once
   Marcus/529 parsers land** — the rule does not need to change, only the
   coverage flag it reads.

**Documented, accepted tradeoff — the "mixed-bucket" case.** Coverage is
computed **per bucket**, not per institution/account, so it is a proxy, not
true pairing. If a household has E*TRADE ingested but Morgan Stanley is not,
`investment_has_coverage` is `True` (E*TRADE has a transaction this period) —
so a Morgan-Stanley-directed checking-side origin leg is *also* treated as
covered and excluded, even though the specific Morgan Stanley statement was
never ingested. That contribution silently drops out of the Investments
total in this specific scenario. This is a known, accepted limitation of
Option C (see `docs/coral-redesign/BLOCKED.md`), not a bug: it only affects
households with more than one institution feeding the same bucket where not
all of them are ingested, and it is still strictly better than
destination-leg-only for the common single-institution-per-bucket case.
Pinned by
`backend/tests/financial_invariants/test_plan_vs_actual_invariants.py::test_mixed_bucket_coverage_is_a_documented_known_limitation`
so a future change doesn't silently alter this tradeoff.

**Why this needed a PR 03 change too.** Coverage-aware dedup only helps once
the destination leg is actually classifiable as a contribution. PR 03
originally required a savings/investment *keyword* in the description before
assigning `savings_contribution`/`investment_contribution` — but realistic
destination-side statement lines (`"CONTRIBUTION"`, `"FUNDS RECEIVED"`,
`"ACH DEPOSIT"`, `"TRANSFER IN"`, …) rarely contain one. See
`docs/TRANSACTION_CLASSIFICATION.md` tier 3f2: an inflow landing directly on
a savings/investment account is now itself treated as contribution evidence,
independent of description wording.

## Accounting rules implemented

| Rule | How it's enforced |
|---|---|
| Checking → Savings is not consumption | `master_bucket` for a transfer leg is never `needs`/`wants` (PR 03); the canonical-leg rule also prevents it inflating Savings twice. |
| Checking → Brokerage is not spending | Same as above, for Investments. |
| Checking → Credit Card payment ≠ double-counted spend | PR 03 classifies unambiguous card-payment language as `cash_flow_type=transfer`, `master_bucket=unclassified` — `_counts_toward_bucket()` only sums `expense`/`refund` rows into Needs/Wants, so a payment is never added a second time on top of the purchases it settles. |
| Savings → Brokerage doesn't duplicate totals | Both legs go through the same `is_canonical_contribution_leg` gate, so the movement can only ever be counted once, never on both statements. When the brokerage side has ingested coverage the brokerage leg is canonical and the savings-side leg is excluded; the reverse (brokerage → savings) behaves symmetrically. See the accumulation-to-accumulation caveat under "Known limitations" below — the *dedup* is sound, but whether such a reallocation should count as a *new* contribution at all is an open modelling question. |
| Refunds reverse/adjust spending | `_signed_bucket_amount()` nets `expense` (negative amount) against `refund` (positive amount, same bucket/category) — see `test_refund_reduces_spending_within_same_category`. A period where refunds exceed spend nets to a negative (but real, not clamped) actual $. |
| Investment rollovers are not new contributions | Classified `investment_activity` by PR 03; `_counts_toward_bucket()` only treats `savings_contribution`/`investment_contribution` as bucket-eligible, so rollovers/dividends/trades never appear in Investments actual $ (they answer "portfolio allocation", a deliberately separate question per `financial-model.md`). |
| User override beats automated classification | Inherited directly from PR 03 — the engine reads whatever `master_bucket`/`classification_category`/`cash_flow_type` is currently persisted, and PR 03's `resolve()` always checks the override table first. `test_user_override_survives_plan_vs_actual_auto_classification` proves the auto-classify step in this engine cannot clobber it (it only ever classifies `classification_source IS NULL` rows). |

## Known limitations

All of these are **accepted, pinned by tests, and deliberately visible** rather
than silently hidden. None of them fabricate a number; each either counts a
real movement in a debatable bucket or omits it and reports the omission.

1. **Mixed-bucket coverage** (see the detailed note above). Coverage is a
   per-bucket boolean, not per-institution pairing, so with E*TRADE ingested
   and Morgan Stanley not, a Morgan-Stanley-directed checking origin leg is
   excluded and that contribution drops out of the Investments total. Pinned
   by `test_mixed_bucket_coverage_is_a_documented_known_limitation`.

2. **Accumulation-to-accumulation reallocation.** The origin-leg fallback (the
   "no destination coverage" branch) counts *any* non-destination-typed leg,
   including one that lives on the *other* accumulation account. So a
   `"TRANSFER TO MARCUS SAVINGS -2,000"` line appearing on an **E\*TRADE**
   statement, in a period with no ingested `savings`-typed account, is counted
   as a **$2,000 new Savings contribution** — even though it is a reallocation
   of dollars that were already allocated in an earlier period, not new
   allocation out of this period's income (compare
   `accounting-invariants.md` #5). The symmetric savings → brokerage case
   behaves the same way once a `savings`-typed account is parseable. The
   dedup is still sound (the movement is never counted on both statements),
   but whether it should count at all is an open modelling question that
   Option C did not decide. Pinned by
   `test_accumulation_to_accumulation_move_counts_as_a_new_contribution`.
   **Revisit before PR 06 renders Savings/Investments drift as a headline
   number, and certainly before Marcus/529 parsers land.**

3. **Timing/partial coverage.** Coverage is evaluated over the requested
   period only. If the destination statement is ingested for the period but
   the specific transfer posted just outside it (a month-boundary straddle),
   the origin leg is still excluded and the destination leg is absent, so that
   movement reads as $0 for the period. The exclusion is reported via
   `completeness.origin_only_transfer_legs_count/_amount`, so the gap is
   visible rather than silent.

## Status thresholds (centralized, not magic numbers)

`StatusThresholds` (`watch_pp` / `off_track_pp`, default 3 / 7 percentage
points) is the single place every status decision goes through
(`compute_status()`). Status polarity differs by bucket type:

- **Consumption buckets** (Needs, Wants): overspend is adverse. Underspend is
  never penalized.
- **Accumulation buckets** (Savings, Investments): shortfall is adverse.
  Overshooting the target is never penalized.

`variance_percentage_points is None` (no plan, or no income observed) always
resolves to `DriftStatus.UNKNOWN` — never fabricated as on/off track.

## Recursive drill-down

- `get_plan_vs_actual(period)` — the four master buckets: target %, actual %,
  target $, actual $, variance $, variance percentage points, status.
- `get_bucket_breakdown(period, bucket)` / `get_category_breakdown(...)` (same
  function — the work order lists both names) — category-level rows within
  one bucket. Needs/Wants categories have no plan-defined target (the seeded
  plan only defines suballocation targets for Savings/Investments), so their
  `target_percentage`/`target_amount`/`variance_*`/`status` are honestly
  `None`/`UNKNOWN` rather than fabricated. A `None`/unresolved
  `classification_category` is grouped under the explicit `"Uncategorized"`
  sentinel — never silently dropped.
- `get_merchant_drivers(period, bucket=None, category=None, top_n=10)` — top
  merchants/descriptions by absolute net $, optionally scoped to a bucket
  and/or category. Only transactions that count toward a bucket total are
  considered (a card payment or an excluded origin-leg transfer never shows
  up as a "driver").

## Plan version resolution

`app.services.plan_vs_actual._resolve_plan()` resolves the plan version in
effect at the **start** of the requested period via
`app.services.financial_plan.get_plan_for_date` — never "just the latest"
(`docs/FINANCIAL_PLAN_MODEL.md`: "Historical data must be evaluated against
the plan active during that historical period"). It also checks whether the
plan changed again before the period ended; if so,
`CompletenessMetadata.plan_version_changed_mid_period` is set `True` with an
explanatory note rather than silently picking one side.

## Completeness metadata

Every result carries a `CompletenessMetadata` block that is honest about what
it does and does not fully represent (`accounting-invariants.md #10`):

| Field | Meaning |
|---|---|
| `plan_available` | `False` if no financial plan is in effect for the period. |
| `plan_version_changed_mid_period` | The plan changed between the start and end of the period. |
| `income_observed` | `False` if Plannable Income is `$0` (percentages undefined). |
| `unclassified_transaction_count` / `_amount` | Transactions flagged `needs_review` by PR 03 **and** not counted in any bucket — dollars completely invisible from every total. |
| `needs_review_count` | All PR 03 `needs_review` transactions, whether or not they still landed in a bucket. |
| `origin_only_transfer_legs_count` / `_amount` | Checking/credit-side transfer legs excluded because the coverage-aware hybrid rule found ingested coverage on the destination side and counted that leg instead (see "Cross-statement double counting" above). Under Option C this is only ever populated in the healthy dedup case — when there is no destination coverage, the origin leg is counted (not excluded), so nothing is reported here for that case. |
| `payroll_deduction_signal_detected` | A payroll-deducted 401(k)/ESPP contribution was found — Plannable Income likely understates true income. |
| `notes` | Human-readable explanations of each non-default flag above, deterministically generated (never LLM text). |
| `is_complete` | `True` only when every flag above is at its "nothing to report" default. **`origin_only_transfer_legs_count` is deliberately excluded from this check** (fixed alongside Option C, `docs/coral-redesign/BLOCKED.md` point 4): a nonzero count there is, by construction, the healthy "both legs ingested, coverage-backed dedup worked" case, not a data gap — the previous version of this property treated any exclusion as incomplete, so `is_complete` was permanently `False` even when nothing was missing. |

## API

- `GET /api/v1/plan-vs-actual?year=&month=[&account_id=]` → full
  `PlanVsActualResult`.
- `GET /api/v1/plan-vs-actual/buckets/{bucket}?year=&month=[&account_id=]` →
  `list[CategoryDrift]` for one bucket (`needs`/`wants`/`savings`/`investments`).
- `GET /api/v1/plan-vs-actual/merchants?year=&month=[&bucket=][&category=][&limit=]`
  → `list[MerchantDriver]`.

These are intentionally minimal, additive routes — no existing page/route was
redesigned. Frontend wiring is out of scope for this work item.

## Tests

- `backend/tests/financial_invariants/test_plan_vs_actual_invariants.py` —
  pure domain-level coverage (no DB): perfect 50/20/15/15 month, Wants
  overspend crossing watch/off_track, Savings/Investments under target,
  transfer double-counting (both savings and brokerage), credit-card payment
  neutrality, refund netting, rollover exclusion, multi-account aggregation,
  historical plan-version stability, unclassified/`None`-category handling,
  incomplete payroll-data signaling, zero-income honesty, and status-polarity
  centralization.
- `backend/tests/test_plan_vs_actual.py` — DB-integration coverage: real
  multi-account aggregation, month-boundary scoping, plan-version resolution
  by period via `financial_plan.create_plan_version`, auto-classification of
  never-classified transactions (and that it never clobbers a prior user
  override), category/merchant drill-down through the service layer, and an
  API-layer smoke test.

Run: `cd backend && python3 -m pytest tests/financial_invariants/ tests/test_plan_vs_actual.py -q`
