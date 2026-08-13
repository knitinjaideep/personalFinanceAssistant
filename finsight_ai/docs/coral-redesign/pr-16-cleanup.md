# PR 16 — Remove Old Dashboard Clutter

Perform cleanup after new Overview, Banking, and Investments are functional.

Do not remove backend functionality.

Remove/demote obsolete UI replaced by:
- Plan vs Actual
- Cash Flow Tree
- Investment Contribution Tree
- Coral Insights
- Next Month Plan

Audit:
- unused KPI cards
- duplicate charts
- unused hooks
- obsolete selectors
- duplicate API calls
- dead CSS
- unused Tailwind classes
- unused icons
- unused dependencies
- stale types

Overview should no longer be dominated by document metrics.
Banking should no longer be dominated by generic Cash In/Cash Out/Net Flow and giant merchant tables.
Investments should no longer be dominated by account count/last updated/raw balance cards.

Do not delete useful drill-down functionality.

Verify no regression in:
- document upload
- statement processing
- chat
- banking account detail
- investment account detail

Run full tests and production builds.
