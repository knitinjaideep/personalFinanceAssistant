# PR 04 — Expected vs Actual Financial Engine

Implement Coral's Plan vs Actual calculation engine.

Backend/domain logic only except for API contracts needed by future UI.
Do not redesign pages yet.
Do not use the LLM for calculations.

## Goal

For any requested financial period calculate:

Plannable Income

For Needs, Wants, Savings, and Investments:
- target %
- actual %
- target $
- actual $
- variance $
- variance percentage points
- status

Also support recursive drill-down into subcategories.

Core principle:

PLAN vs ACTUAL = DRIFT

## Accounting Rules

Avoid double counting.

Checking -> Savings is not consumption.
Checking -> Brokerage is not spending.
Checking -> Credit Card payment should not count as spending if card purchases are already included.
Savings -> Brokerage must not create duplicate savings/investment totals.
Refunds should reverse/adjust the appropriate spending.

Support payroll deductions such as 401(k) and ESPP.
These may not appear in checking.
Do not invent payroll values.
If payroll data is unavailable, return explicit completeness metadata.

Define Plannable Income clearly and make it testable.

API should return a frontend-friendly structure with period, planVersion, income, bucket target/actual/variance/status, and completeness metadata.

Support service methods conceptually like:
- get_plan_vs_actual(period)
- get_bucket_breakdown(period, bucket)
- get_category_breakdown(...)
- get_merchant_drivers(...)

Status logic should be deterministic and centralized/configurable:
- on_track
- watch
- off_track

Tests:
- perfect 50/20/15/15 month
- Wants overspend
- Savings under target
- Investments under target
- transfer handling
- credit-card payment double counting
- refund handling
- multi-account aggregation
- month boundaries
- plan version changes
- missing classifications
- incomplete payroll data

Create docs/PLAN_VS_ACTUAL_ENGINE.md.
