# PR 12 — Redesign Investments

Completely redesign Coral's Investments page using the mockup under /docs/design/.

Primary question:

"Am I investing according to plan?"

Do not lead with Total Portfolio, Unrealized G/L, account count, or Last Updated.
These can remain lower on the page.

Use the global FinancialPeriodSelector.

## Hero

Investment Contribution Tree:

Investments
Target 15%
Actual X%
  -> 401(k) target 6%
  -> Roth IRA target 4%
  -> ESPP target 3%
  -> Brokerage target 2%

Each child shows target %, actual %, status, and gap $.

Use actual API values.

## Secondary Sections

Plan vs Actual Contributions:
horizontal target-vs-actual bars.

Next Month Contribution Plan:
deterministic recommendations such as Keep at X or Add ~$Y.

Do not invent transfer/execution capability.
Use advisory buttons like View plan or Adjust target.

Coral Investment Insights:
maximum 3.

Portfolio Health:
- diversification
- employer stock concentration
- cash waiting to invest
- asset concentration
Only when supported by actual imported data.

Portfolio Allocation:
secondary, compact donut/bars are fine.

Keep account details/holdings accessible lower on page or through drill-down.
Do not delete useful existing functionality.

Add responsive behavior and tests.
