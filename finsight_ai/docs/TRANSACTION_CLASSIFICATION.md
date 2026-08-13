# Transaction Classification Model

Coral's classification layer maps every `transactions` row onto the
Plan→Actual model that `docs/FINANCIAL_PLAN_MODEL.md` defines targets for.
It is a **derived, additive layer** — it never rewrites the raw data a parser
imported, and it never lets an LLM decide a financial amount. It only decides
*labels* (bucket / category / cash-flow type), and only as a last resort, only
when nothing deterministic could.

This is the PR 03 (M1 — Transaction Intelligence) deliverable. PR 04 (Plan vs
Actual Engine) consumes `master_bucket` / `classification_category` /
`cash_flow_type` to compute target-vs-actual variance per bucket/category.

## Why this exists

Before this layer, a transaction only had a single, parser-assigned
`category` (e.g. `"groceries"`, `"restaurants"`, `"other"`) — a flat,
12-value taxonomy (`app.domain.enums.TransactionCategory`) good enough for
free-text search and simple SQL grouping, but with no concept of Needs vs
Wants vs Savings vs Investments, no cash-flow semantics (a Zelle transfer and
a grocery purchase both just had *some* category), and no way for a user to
correct a wrong guess.

## Model

Every transaction can be classified along three independent axes:

### 1. Cash Flow Type (`transactions.cash_flow_type`)

What kind of money movement this is — this is what makes internal transfers,
card payments, refunds, and investment rollovers **not** count as ordinary
spending (accounting-invariants.md #1–#7):

| Value                      | Meaning                                                              |
|-----------------------------|-----------------------------------------------------------------------|
| `income`                    | Payroll / direct deposit / other new money in                        |
| `expense`                   | Ordinary Needs/Wants spending                                        |
| `transfer`                  | Internal account-to-account movement, incl. credit-card payments     |
| `savings_contribution`      | New money moved toward a savings goal (HYSA, emergency fund, etc.)   |
| `investment_contribution`   | New money moved toward a brokerage/retirement account                |
| `investment_activity`       | Activity *within* an investment account (dividends, trades, rollovers) — not new contributed cash |
| `refund`                    | Money returned for a prior purchase — must not inflate spending      |
| `other`                     | Fees and anything that doesn't fit the above                         |

### 2. Master Bucket (`transactions.master_bucket`)

Which of the four Financial Plan buckets this belongs to — only meaningful
for `expense`/`refund` (Needs/Wants) and `savings_contribution`/
`investment_contribution`/`investment_activity` (Savings/Investments) rows.
Everything else (`transfer`, `income`, `other`) is `unclassified` — transfers
and income are not consumption and don't belong to any of the four buckets.

- `needs`
- `wants`
- `savings`
- `investments`
- `unclassified`

### 3. Category (`transactions.classification_category`)

The specific sub-category within a bucket. Exact lists (must match
`docs/coral-redesign/pr-03-classification.md`):

| Needs           | Wants               | Savings         | Investments        |
|-----------------|---------------------|-----------------|---------------------|
| Housing         | Dining               | Emergency Fund  | 401(k)              |
| Utilities       | Entertainment        | House / Goals   | Roth IRA            |
| Connectivity    | Travel               | Child Savings   | ESPP                |
| Groceries       | Shopping             |                 | Taxable Brokerage   |
| Transportation  | Personal Care        |                 |                     |
| Insurance       | Fitness/Hobbies      |                 |                     |
| Healthcare      | Home Decor           |                 |                     |
| Minimum Debt    | Gifts/Celebrations   |                 |                     |

Savings/Investments category names are exactly the suballocation names seeded
in `financial_plan.py`, so PR 04 can join classified transactions straight
onto plan suballocations without a translation table.

`classification_category` can be `None` — e.g. a savings/investment transfer
whose sub-goal can't be determined from statement text ("we know this is
savings, we don't know *which* goal") is left unset rather than guessed
(accounting-invariants.md #10 — incomplete data honesty).

### Metadata

- `classification_source` — how the classification was produced (below).
- `classification_confidence` — `0.0`–`1.0`.
- `needs_review` — `True` when Coral could not confidently classify the
  transaction (ambiguous merchant, low-confidence LLM guess, or truly
  unresolvable) and a human should look at it.

**`transactions.category` (the raw, parser-assigned value) is never modified
by this layer.** All new fields are additive columns — see
accounting-invariants.md #9 (source preservation).

## Classification source & precedence

`classification_source` records *which tier* produced the final answer:

| Source              | Tier | Meaning                                                        |
|----------------------|------|-----------------------------------------------------------------|
| `user`               | 1, 2 | Explicit per-transaction override, or a user-authored merchant rule |
| `deterministic_rule` | 3    | Structural/keyword rule (transfers, investment/savings institutions, card payments, refunds, rollovers, payroll) |
| `existing_category`  | 4    | Parser-assigned `category` mapped through a trusted, unambiguous table |
| `heuristic`          | 5    | Merchant/description keyword match (or the ambiguous-merchant gate) |
| `llm`                | 6    | Caller-supplied LLM fallback (only reached when tiers 3–5 found nothing) |
| `unknown`            | 7    | Nothing matched — `unclassified`, `needs_review=True`            |

Precedence is fixed and enforced in
`app.domain.transaction_classification.classify_transaction()`:

```
1. explicit user transaction override         (always wins, never silently overwritten)
2. explicit user merchant rule
3. deterministic known transfer/investment/savings/refund/income rule
4. trusted existing (parser-assigned) category mapping
5. heuristic/merchant keyword classifier        (includes the ambiguous-merchant gate)
6. LLM fallback                                 (caller-supplied; engine never calls Ollama itself)
7. unclassified
```

A **user override always wins** and is **never silently overwritten** by any
later automated run: `TransactionClassificationService.classify()` /
`classify_batch()` re-check the override row on every call, so re-running
classification (e.g. after a re-ingest) reproduces the user's choice instead
of reverting it.

### Deterministic rules (tier 3)

Pure keyword/structural rules over `transaction_type`, `description`, and
`merchant_name` — no DB access, no network calls:

- Rollover language (`"rollover"`) → `investment_activity`, never
  `investment_contribution` (accounting-invariants.md #7).
- `transaction_type` in `{dividend, trade_buy, trade_sell, tax_withholding,
  advisory_fee}` → `investment_activity` (in-account activity, not new cash).
- `transaction_type == "interest"` depends on the account: inside an
  investment account it is `investment_activity`; anywhere else it is a
  finance charge or interest earned and belongs to no master bucket
  (`other`/`unclassified`, same treatment as fees). The Amex/Chase/Discover
  extractors stamp `interest` on credit-card *interest charge* lines, which
  must never land in the Investments bucket.
- Unambiguous card-payment language (`"payment thank you"`, `"credit card
  payment"`, `"card payment"`, `"crd epay"`, `"minimum payment"`, `"statement
  credit"`, …) → `transfer`, `unclassified` (accounting-invariants.md #2 — the
  purchases are already expensed individually, so the payment itself must not
  double-count).
- Generic payment/autopay wording (`"autopay"`, `"online payment"`, `"bill
  payment"`, `"thank you"`, or `transaction_type == "payment"`) is **weaker
  evidence** and only becomes a neutral transfer when tiers 4/5 found no
  spending evidence. This matters because `chase/parser.py::_classify_type`
  and `bank_of_america/parser.py::_classify_type` stamp
  `transaction_type="payment"` on *any* description containing the word
  "payment" — treating that as a card payment would silently drop
  "RENT PAYMENT", "PSEG ELECTRIC PAYMENT" or "VERIZON AUTOPAY" out of Needs.
- Explicit refund/return/reversal language → `cash_flow_type=refund`, but the
  bucket/category is still resolved via tiers 4/5 so a refund can net against
  the category it reversed (accounting-invariants.md #6).
- Investment institution/contribution keywords (401k, Roth, ESPP, brokerage,
  E*TRADE, Morgan Stanley, Schwab, Fidelity, Vanguard, Robinhood, "ira
  contribution") → `investment_contribution`, `investments`
  (accounting-invariants.md #4).
- Savings institution/goal keywords (HYSA, Marcus, Goldman Sachs, "emergency
  fund", "house fund", "529", …) → `savings_contribution`, `savings`
  (accounting-invariants.md #3).
- **Inflow on a savings/investment account with no keyword evidence** →
  `savings_contribution` / `investment_contribution` by `account_type` alone
  (tier 3f2). Being *on* a savings/brokerage/retirement account
  (`account_type` in `SAVINGS_ACCOUNT_TYPES` / `INVESTMENT_ACCOUNT_TYPES`) is
  itself contribution evidence for a positive-amount transaction, independent
  of description wording. Added per `docs/coral-redesign/BLOCKED.md`: without
  it, realistic destination-side statement lines — `"CONTRIBUTION"`,
  `"FUNDS RECEIVED"`, `"ACH DEPOSIT"`, `"TRANSFER IN"`,
  `"DEPOSIT FROM CHASE CHECKING"`, `"ONLINE TRANSFER FROM CHK"` — landed as
  `other`/`transfer`/`unclassified` even while sitting on an unambiguous
  savings/investment account, because tiers 3e/3f require a savings/investment
  keyword in the text. This tier only fires when nothing above it (rollover,
  investment activity, interest, card payment, explicit refund, or a
  keyword-based savings/investment match) already resolved the row, and only
  for genuine inflows (`amount > 0`) — the matching outflow direction is left
  untouched (still a withdrawal, never a contribution). `category` stays
  `None` unless the description also happens to name a specific goal
  (`"Roth IRA"`, `"401(k)"`, …).
- Generic transfer language (`"transfer"`, Zelle, Venmo, PayPal transfer, or
  `transaction_type == "transfer"`) → `transfer`, `unclassified`
  (accounting-invariants.md #1). Checked *after* tier 3f2, so an inflow
  landing on a savings/investment account (e.g. `"TRANSFER IN"`) is caught by
  the account-type rule above rather than falling through to this generic,
  weaker rule.

**Direction matters for savings/investment rules.** A contribution is money
moving *toward* the savings/investment side. Seen from a savings/investment
account (`account_type` in `savings` / `ira` / `roth_ira` / `advisory` /
`individual_brokerage` / `401k`) the inflow (`amount > 0`) is the
contribution; seen from a cash or credit account — or when the account type is
unknown, which is the common checking-statement case — the outflow
(`amount < 0`) is. The opposite direction ("TRANSFER FROM MARCUS SAVINGS
+$1,000") is a **withdrawal** and is classified `transfer`/`unclassified`, so
it can never inflate savings or investing actuals.
- Payroll/direct-deposit language on a deposit → `income`, `unclassified`.
- `transaction_type == "fee"` → `other`, `unclassified`.

### Trusted existing category (tier 4)

`transactions.category` is populated at ingest time by the shared
`app.parsers.categorize.categorize()` keyword classifier (used by every
institution parser). Only the subset that maps **unambiguously** onto a
single Needs/Wants category is trusted here: `groceries`, `gas`, `utilities`,
`healthcare`, `insurance`, `restaurants`, `travel`, `entertainment`.
`shopping`, `subscriptions`, `education`, `transfers`, `fees`, `atm_cash`, and
`other` are deliberately excluded — they're too broad to trust blindly — and
fall through to tier 5.

### Heuristic keyword classifier + ambiguous-merchant gate (tier 5)

An independent keyword table (`app.domain.transaction_classification`) covers
all 16 Needs/Wants categories directly from merchant/description text (e.g.
`"rent"`/`"mortgage"` → Housing, `"starbucks"`/`"doordash"` → Dining).

**Before** either tier 4 or tier 5 runs, every spending-shaped transaction is
checked against `KNOWN_AMBIGUOUS_MERCHANTS`:

```
Amazon, Target, Walmart, Costco, CVS
```

These merchants sell across Needs and Wants (groceries, electronics, home
goods, pharmacy, apparel — all from the same storefront), so a statement line
alone can never reliably say which. Matching one of these **short-circuits
straight to `unclassified` + `needs_review=True`**, even if the raw parser
category (e.g. CVS → `healthcare`) would otherwise look confident. This is
intentional: a merchant name is not proof of what was purchased there, and
Coral must not fabricate false confidence (accounting-invariants.md #10). A
user override or merchant rule (tiers 1–2) is the only way to resolve these
with confidence — Coral will remember the choice from then on.

### LLM fallback (tier 6)

The engine (`classify_transaction()`) never calls an LLM itself — it accepts
an already-computed `llm_result` and only uses it when tiers 1–5 produced
nothing (`source == unknown`). `TransactionClassificationService` accepts an
optional `llm_classifier` callable and only invokes it after probing the
deterministic tiers first, so no LLM call is ever made speculatively. Any
result with confidence `< 0.6` is force-flagged `needs_review=True` — the LLM
can suggest a label, never a guaranteed answer, and it is never the source of
a financial total (see CLAUDE.md "Financial correctness" and
`.claude/rules/backend.md`).

### Unclassified (tier 7)

Nothing matched: `unclassified`, `category=None`, `confidence=0.0`,
`needs_review=True`. Honest "we don't know" beats a fabricated guess.

## Refund / expense sign resolution

Coral's canonical amount sign convention (see `app/parsers/*/parser.py`) is
**negative = money out**. For a spending-shaped transaction (not already
resolved to transfer/income/investment/savings by tier 3):

- explicit refund language in the description → `cash_flow_type=refund`
  regardless of amount sign;
- otherwise, if the row **resolved to a Needs/Wants label** (tier 4/5):
  `amount < 0` → `expense`, `amount > 0` → `refund` (a positive amount landing
  in a spending category, with no other explanation, is virtually always money
  coming back);
- if the row did **not** resolve to any label (tier 7): `amount < 0` →
  `expense`, `amount >= 0` → `other`. An unexplained deposit (a paycheck whose
  description lacks payroll wording, a mobile check deposit, a tax refund) must
  never be labelled `refund`, because PR 04 nets refunds against spending and a
  mislabel there would silently erase real expenses.

The bucket/category is resolved the same way for both `expense` and `refund`
rows, so a refund can net against the category it reverses instead of being
dumped into `unclassified` and losing that linkage.

## User overrides and merchant rules

Two new tables, kept separate from the derived fields on `transactions` (see
`backend/app/db/models.py`):

```
transaction_classification_overrides   (tier 1 — one row per overridden transaction)
  id, transaction_id (unique), master_bucket, category, cash_flow_type, created_at, updated_at

merchant_classification_rules          (tier 2 — applies going forward)
  id, scope ("merchant" | "merchant_account" | "category"),
  merchant_key, source_category, account_id,
  master_bucket, category, cash_flow_type, created_at, updated_at
```

Rule scope:

- `merchant` — matches this merchant/description substring on any account.
- `merchant_account` — matches only on one specific account (more specific,
  checked first).
- `category` — matches a raw imported `transactions.category` value (e.g.
  "always treat 'shopping' on my Amex as Wants/Shopping").

`TransactionClassificationService.apply_merchant_rule()` creates the rule and
(by default) reclassifies existing matching transactions — except any
transaction that already has an explicit per-transaction override, which
tier 1 continues to protect.

## Service API

`app.services.transaction_classification.TransactionClassificationService`
(no FastAPI import — usable from ingestion, chat domains, or a future API
route, exactly like `app.services.financial_plan`):

- `resolve(session, txn) -> ClassificationResult` — compute without persisting.
- `classify(session, transaction_id) -> ClassificationResult` — compute and persist.
- `classify_batch(session, *, account_id=None, only_unclassified=True) -> BatchClassificationSummary`
- `apply_user_override(session, transaction_id, *, master_bucket, cash_flow_type, category=None)`
- `apply_merchant_rule(session, *, master_bucket, cash_flow_type, category=None, scope, merchant_key=None, source_category=None, account_id=None)`
- `get_needs_review(session, limit=100) -> list[TransactionModel]`

## Known limitations / product decisions to revisit

- **Uber/Lyft** are classified as Needs/Transportation (commute), not
  Wants/Travel. Real usage is genuinely mixed (commute vs. leisure); revisit
  once PR 04 shows how much this skews Needs.
- **Home Depot/Lowe's** currently match no keyword and fall through to
  `unclassified` + `needs_review`. They are genuinely split between home-repair
  Needs and Home Decor Wants, and the pr-03 category list has no "Home Repair"
  Needs category — so they are surfaced for the user rather than guessed. A
  merchant rule resolves them permanently.
- **The same dollar movement seen on two statements is not yet de-duplicated
  at the classification layer.** A checking→brokerage transfer appears as an
  outflow on the checking statement *and* as an inflow on the brokerage
  statement; both legs classify as `investment_contribution` from their own
  account's perspective. Classification alone cannot see across statements —
  PR 04 (`docs/PLAN_VS_ACTUAL_ENGINE.md`) resolves the dedup with a
  **coverage-aware hybrid** (Option C, `docs/coral-redesign/BLOCKED.md`): the
  destination leg counts when the relevant savings/investment account type has
  any ingested transaction that period; otherwise the origin (checking/credit)
  leg counts instead. This tier's account-type inflow rule (3f2, above) is
  what makes the destination leg reliably classifiable once its statement is
  ingested — without it, most destination-side lines fell through to
  `other`/`transfer` regardless of which leg PR 04 chose to count.
- **Tier 3f2 outranks the income rule (3h) on a savings account.** A payroll
  direct deposit that lands *directly* on a `savings`-typed account
  (`"ACME CORP PAYROLL DIRECT DEP"`, `transaction_type="deposit"`, amount
  `+3,000`) is classified `savings_contribution`, **not** `income`, because
  3f2 is checked before 3h. That money therefore does **not** enter PR 04's
  Plannable Income denominator, which inflates every bucket's actual % for the
  period, and simultaneously inflates the Savings actual $. The movement is
  genuinely both income *and* a savings contribution, and a single
  `cash_flow_type` cannot express both — resolving it is a product/modelling
  decision, not an implementation detail. **Currently unreachable**: every
  `savings`-typed account in `statement_catalog.py` (Marcus, 529) is
  `parseable=False`, so no such row can exist yet. **Must be decided before a
  savings parser lands.** Pinned by
  `test_payroll_deposit_landing_on_a_savings_account_is_currently_a_contribution`.
- **Tier 3f2 cannot tell a checking→brokerage contribution from a
  brokerage→brokerage move.** A bare `"TRANSFER IN"` / `"JOURNAL ENTRY
  CREDIT"` inflow on an investment account is classified
  `investment_contribution` regardless of where the money came from. Before
  3f2 these fell through to a neutral `transfer`; the account-type rule was
  required by Option C so destination legs are classifiable at all, and a
  checking→brokerage contribution is by far the more common shape, but an
  internal investment→investment move now reads as *new* investing (the
  matching outflow stays neutral, so it is counted once, not twice). Explicit
  `"rollover"` wording is still caught earlier by tier 3a and stays
  `investment_activity` (`accounting-invariants.md` #7). Pinned by
  `test_investment_to_investment_transfer_in_currently_reads_as_a_contribution`.
- **Generic savings/investment transfers** (e.g. "Transfer to Savings" with
  no goal name) get `savings_contribution`/`investment_contribution` with
  `category=None` — PR 04's per-suballocation actuals will need to handle
  `category IS NULL` rows (uncategorized-but-bucketed) explicitly rather than
  assuming every savings/investment row has a specific goal.
- **Plannable income** (payroll-deducted 401(k)/ESPP contributions that never
  touch checking) is out of scope for this PR — `cash_flow_type=income` is
  only assigned from bank-side deposit lines. PR 04 (per
  `financial-model.md`) will need a separate mechanism for payroll-side
  contributions that never appear as a checking-account transaction at all.
