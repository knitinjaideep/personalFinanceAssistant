# Coral Redesign — BLOCKED

Raised by: independent review of **PR04 — Plan vs Actual Engine** (M1)
Status: **RESOLVED — user selected Option C (coverage-aware hybrid)**, 2026-08-13.
Routed back to `coral-implementer` for repair; reviewer will re-review, verifier will re-verify.

---

## Decision needed

**Which leg of a checking → savings / checking → brokerage transfer counts as
the Savings/Investments contribution in Plan vs Actual?**

PR04 currently implements **destination-leg-only**
(`app/domain/plan_vs_actual.py::is_canonical_contribution_leg`): a
`savings_contribution` / `investment_contribution` row is summed into a bucket
total **only if it lives on an account whose `account_type` is in
`SAVINGS_ACCOUNT_TYPES` / `INVESTMENT_ACCOUNT_TYPES`**. The checking-side
"origin" leg is excluded from every total and reported only via
`completeness.origin_only_transfer_legs_count/_amount`.

This rule is internally consistent, deterministic, well documented, and it
**does** prevent double counting (verified end-to-end). The problem is not the
dedup — it is which side survives.

---

## Why it matters

### 1. Savings actual $ is structurally $0.00 for Coral's real account coverage

`backend/app/config/statement_catalog.py` marks **both Marcus HYSA accounts
and the 529 as `parseable=False`** — no parser is registered, so no
transaction row with `account_type == "savings"` can ever exist in the
database. There is no other `savings`-type account in the catalog.

Under destination-leg-only, that means the Savings bucket can never have a
single canonical leg. Verified end-to-end against a temp DB, with a $10,000
payroll deposit and a real `TRANSFER TO MARCUS SAVINGS -1500.00` on an
ingested Chase checking statement:

```
Savings   target $1,500.00   actual $0.00   variance -$1,500.00   OFF_TRACK
Invest.   target $1,500.00   actual $0.00   variance -$1,500.00   OFF_TRACK
completeness.origin_only_transfer_legs_amount = "2500.00"
```

The user saved $1,500. Coral has the evidence in a parsed statement. The
headline number on the surface that is supposed to answer "How am I doing?"
(M3 / PR06) would say they saved **$0** and are **off track by $1,500**.

### 2. The rule keeps the leg PR03 is *least* able to classify

PR03 requires a savings/investment **keyword in the description text** before
it will assign `savings_contribution` / `investment_contribution`. Being *on*
a savings/brokerage/retirement account is not itself treated as evidence.
Realistic destination-side statement lines therefore classify like this
(traced directly against `classify_transaction`):

| description | account_type | resulting cash_flow_type | canonical leg? |
|---|---|---|---|
| `CONTRIBUTION` | `ira` | `other` | no |
| `FUNDS RECEIVED` | `individual_brokerage` | `other` | no |
| `ACH DEPOSIT` | `individual_brokerage` | `other` | no |
| `TRANSFER IN` | `roth_ira` | `transfer` | no |
| `DEPOSIT FROM CHASE CHECKING` | `savings` | `other` | no |
| `ONLINE TRANSFER FROM CHK` | `savings` | `transfer` | no |
| `EMPLOYEE CONTRIBUTION 401K` | `401k` | `investment_contribution` | **yes** |

Meanwhile the checking-side legs (`TRANSFER TO MARCUS SAVINGS`,
`TRANSFER TO MORGAN STANLEY`, `ETRADE ACH`) *do* match PR03's institution
keywords and *are* classified as contributions — and are exactly the rows
PR04 discards.

So the two PRs currently pull in opposite directions: PR04 keeps the leg PR03
usually cannot label, and drops the leg PR03 reliably can. The net effect is
Savings/Investments actuals near $0 even when *both* statements are ingested.

### 3. Neither the work order nor the invariants pick a side

- `pr-04-plan-vs-actual.md` says only "Checking -> Savings is not consumption"
  and "Savings -> Brokerage must not create duplicate savings/investment
  totals". It does not say the checking leg is not the contribution.
- `accounting-invariants.md` #3 says "**Checking → HYSA may represent a
  savings contribution**" — which reads as endorsing the origin leg as a
  legitimate representation.
- `docs/TRANSACTION_CLASSIFICATION.md` (PR03) recommended the *opposite*
  resolution: "restrict contribution actuals to a single side (e.g.
  **cash-account outflows only**)".

This is a product/accounting-policy choice with a large, user-visible dollar
consequence, not a routine implementation detail — so it is being escalated
rather than decided in review.

### 4. Secondary: `is_complete` is false in the healthy case

`CompletenessMetadata.is_complete` becomes `False` whenever *any* origin leg
was excluded — including the case where both legs were ingested and dedup
worked perfectly. If M2/M3 renders an "incomplete data" banner off this flag,
it will show permanently. Whether the flag should narrow to "excluded with no
destination coverage" depends on which option below is chosen, so it is
bundled into this decision.

---

## Options

### Option A — keep destination-leg-only (status quo)

Count only legs living on a savings/investment account.

- Pro: zero cross-statement matching risk; payroll-deducted 401(k)/ESPP is
  captured with no special case; single testable predicate.
- Con: Savings reads $0 forever until Marcus/529 parsers exist; most
  investment destination lines are not classified as contributions anyway;
  the user sees a wrong headline number today.
- Requires (to be usable): write Marcus + 529 parsers, **and** extend PR03 so
  an inflow on a savings/investment account counts as a contribution by
  account type rather than by description keyword.

### Option B — origin-leg-only (cash-account outflows), plus destination legs with no cash counterpart

Count the checking/credit-side outflow as the contribution; additionally count
destination legs on retirement/brokerage accounts whose category is
`401(k)`/`ESPP` (payroll deductions, which by definition have no cash leg).

- Pro: matches Coral's real data today — the checking statement is the one
  reliably parsed and reliably classified; matches PR03's own recommendation
  and invariant #3's wording; still no fuzzy matching.
- Con: needs an explicit, narrow payroll carve-out (the thing Option A
  avoided); a brokerage-only transfer that never touches checking (e.g. an
  external ACH pull initiated at E*TRADE) would be missed.

### Option C — coverage-aware hybrid (deterministic, no fuzzy pairing)

Count the destination leg when the relevant destination side has ingested
transaction coverage for the period; otherwise fall back to the origin leg.
Concretely: an origin leg classified `savings_contribution` is counted only if
**no** account with `account_type` in `SAVINGS_ACCOUNT_TYPES` has any
transaction in the period (same, independently, for investments).

- Pro: correct today (savings side uncovered → checking leg counts) *and*
  correct later once Marcus is parseable (savings side covered → destination
  leg counts); no amount/date pairing; payroll deductions still counted.
- Con: coverage is a per-bucket proxy, so it is wrong in the mixed case
  (E*TRADE ingested, Morgan Stanley not — the MS transfer would be treated as
  covered and dropped); more moving parts to explain.

### Option D — true cross-statement pairing (amount + date window + institution)

- Pro: exact when it matches.
- Con: fuzzy matching across independently-parsed statements; silent
  mismatches either double count or drop money. Explicitly the approach the
  implementer avoided, and I agree it should stay avoided.

---

## Recommendation

**Option C**, with **Option B as an acceptable simpler fallback.**

Rationale: Option C is the only choice that produces a truthful Savings number
for the account coverage Coral actually has *today* while remaining exactly as
correct as Option A once Marcus/529 parsers land — and it needs no fuzzy
pairing. It also gives `is_complete` a meaningful definition: flag only origin
legs that were excluded *and* had no destination coverage, so the healthy
both-legs-ingested case reports complete.

Whichever option is chosen, PR03 should additionally be extended so that an
inflow **on** a savings/investment account is treated as contribution evidence
by account type, not only by description keyword — otherwise destination legs
stay largely unclassified regardless of which side is counted.

Recommended sequencing: resolve this before M2/M3, because PR06 (Overview)
renders Savings/Investments drift as a primary headline number.

---

## Not blocked

Everything else in PR04 verified clean: no double counting when both legs are
present, credit-card payment neutrality holds through aggregation, refund
netting, rollover exclusion, multi-account aggregation, month-boundary
scoping, historical plan-version resolution, zero LLM involvement, and a
green suite (410 passed).
