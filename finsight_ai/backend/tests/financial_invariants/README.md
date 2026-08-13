# Financial Invariant Tests

These tests protect Coral's financial semantics against regressions.

Required invariants:

1. Checking → Savings is not Needs/Wants spending.
2. Checking → Brokerage is not Needs/Wants spending.
3. Credit-card purchases plus card payment count consumer spending once.
4. Refunds offset relevant spending.
5. Investment rollovers are not new monthly contributions.
6. Internal account transfers are economically neutral unless explicitly classified as a new allocation event.
7. User classification overrides automated classification.
8. Master financial-plan allocation totals 100%.
9. Historical plan versions remain historically stable.
10. Missing payroll/contribution data does not produce fabricated actual values.

All financial-engine redesign work must keep this suite passing.