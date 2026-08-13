# PR 11 — Investment Contribution Model

Build investment contribution planning domain logic.

Do not redesign Investments in this PR.

Targets:
- Total Investments: 15%
- 401(k): 6%
- Roth IRA: 4%
- ESPP: 3%
- Taxable Brokerage: 2%

Separate contribution allocation from portfolio allocation.

Contribution allocation:
"How much income am I putting toward each investment vehicle?"

Portfolio allocation:
"What assets do I own?"

Do not combine them.

If payroll data is incomplete, return completeness metadata.

Create/extend an InvestmentPlanService that calculates for each vehicle:
- target_pct
- actual_pct
- target_amount
- actual_amount
- variance_amount
- variance_pct_points
- status
- data_completeness
- recommended_next_month_delta

All calculations must be deterministic.

Tests:
- all targets met
- one target behind
- over-contribution
- missing payroll data
- zero income
- multi-account contributions
- rollovers not counted as monthly contributions
- investment transfers not double counted
