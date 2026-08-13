# PR 05 — Global Period Filter

Implement one unified financial period control shared by Overview, Banking, and Investments.

Support:
- Current Month
- 1M
- 3M
- 6M
- YTD
- 1Y
- Custom

Also support month navigation.

Create a reusable <FinancialPeriodSelector />.

The selected period should:
- be reflected in the URL where reasonable
- survive page navigation
- drive backend API queries
- update all three financial pages

Prefer URL/query state where practical.
Handle timezone/date boundaries correctly.

Add loading transitions, keyboard accessibility, custom range picker, and responsive behavior.

Do not fetch all transactions and filter client-side.
Query the backend using the selected range.

Add tests.
