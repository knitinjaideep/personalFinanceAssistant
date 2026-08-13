# Coral Accounting Invariants

These invariants are non-negotiable.

Every financial-engine change must preserve them.

## 1. Internal transfer neutrality

Moving money between user-owned accounts does not create spending.

Example:

Checking → Savings

does not increase Needs or Wants.

## 2. Credit-card payment neutrality

If individual credit-card purchases are already represented as expenses:

Checking → Credit Card Payment

must not be counted again as spending.

## 3. Savings is not consumption

Checking → HYSA may represent a savings contribution.

It must not simultaneously appear as ordinary spending.

## 4. Investment contribution is not consumption

Checking → Brokerage may represent an investment contribution.

It must not appear as Needs/Wants spending.

## 5. Savings to investment movement

Savings → Brokerage may change financial purpose.

Do not count the same dollars repeatedly as both new income allocation and repeated consumption.

Implement according to the period/allocation model.

## 6. Refunds

Refunds must reduce or offset economic spending appropriately.

A refund should not appear as ordinary new income unless the application's accounting model explicitly and correctly defines it that way.

## 7. Investment rollovers

401(k) rollover, IRA rollover, or brokerage transfer is not a new monthly investment contribution.

## 8. User correction precedence

A user's explicit classification overrides automated classifications.

## 9. Source preservation

Never destroy imported/raw transaction/category information merely because Coral adds a derived classification.

## 10. Incomplete data honesty

If payroll information, account coverage, or classifications are incomplete:

report incompleteness.

Never manufacture values to make a chart reconcile.

## Required invariant tests

Maintain tests covering at least:

- checking → savings neutrality
- checking → brokerage neutrality
- card purchase + card payment counts purchase once
- refund reduces spending
- investment rollover is not contribution
- internal transfer between checking accounts is neutral
- user override beats automated classification
- 50/20/15/15 targets total 100
- historical plan change does not rewrite previous periods