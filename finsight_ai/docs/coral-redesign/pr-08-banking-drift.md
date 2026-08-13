# PR 08 — Banking Drift & Top Drivers

Continue the Banking redesign.

Add <BudgetDriftTable /> titled:

Where You're Off Plan

Columns:
- Category
- Target
- Actual
- Drift

Sort by largest negative financial drift first, not alphabetically.

Display target $, actual $, variance $, and when useful target/actual %.

Use semantic statuses and avoid treating every over-target Need as inherently bad.

Clicking a category should drill into:
Category -> merchants -> transactions

Add Top Drivers for the selected period.

Example:
Shopping +$400
  Amazon +$250
  Target +$100
  Other +$50

Explain in terms of plan drift.
Do not call every large merchant "bad".
Use backend aggregation.
Internal transfers must never appear in Top Drivers.

Add loading/empty/error states.
