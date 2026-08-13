# PR 20 — Final Architecture & Test Audit

Perform a final audit of the Coral financial-dashboard redesign.

Review:
- Overview
- Banking
- Investments
- Financial Plan
- Classification
- Plan vs Actual
- Savings Goals
- Investment Contributions
- Coral Insights
- Next Month Planner

Do not implement new features unless fixing bugs found during audit.

## Audit Areas

1. Financial correctness:
verify no double counting for checking/savings/brokerage transfers, credit-card payments, refunds, investment transfers, or rollovers.

2. Plan correctness:
verify 50% Needs, 20% Wants, 15% Savings, 15% Investments.
Historical plans must use correct effective dates.

3. Classification precedence:
user override > merchant rule > deterministic rule > existing category > heuristic > LLM > unknown.

4. LLM boundaries:
LLM must not calculate totals, percentages, variance, budget gaps, or contribution gaps.

5. UI integrity:
test Overview, Banking, Investments at target resolutions.

6. Privacy:
no raw financial values logged accidentally, no statement contents in frontend logs, no sensitive debug dumps in production.

7. Performance:
check duplicate requests, N+1 queries, unnecessary full-history loads, expensive rerenders, slow charts.

8. Accessibility:
keyboard, focus, contrast, screen-reader labels, reduced motion.

9. Existing functionality:
Chat, Documents, Uploads, Parsers remain working.

10. SQLite:
migrations must be safe and backwards compatible.

Create REDESIGN_FINAL_AUDIT.md with:
- PASS
- ISSUES FIXED
- KNOWN LIMITATIONS
- FUTURE WORK

Run:
- frontend lint
- frontend typecheck
- frontend tests
- frontend production build
- backend tests
- integration tests

Fix regressions discovered during audit.
