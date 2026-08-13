# Coral Financial Model

## Master financial plan

Coral evaluates financial behavior against an effective-dated plan.

Default model:

Needs           50%
Wants           20%
Savings         15%
Investments     15%

Total          100%

Plans can change over time.

Historical data must be evaluated against the plan active during that historical period.

## Needs

Needs include baseline costs required for health, housing, safety, employment, transportation, and minimum contractual obligations.

Common categories:

- Housing
- Utilities
- Connectivity
- Groceries
- Transportation
- Required Insurance
- Healthcare
- Minimum Debt Payments

## Wants

Wants represent discretionary quality-of-life consumption.

Common categories:

- Dining
- Entertainment
- Travel
- Shopping
- Personal Care
- Fitness / Hobbies
- Home Decor
- Gifts / Celebrations

## Savings

Default target: 15%.

Sub-allocation:

Emergency Fund     5%
House / Goals      5%
Child Savings      5%

Savings represents accumulation of liquid or goal-directed assets rather than consumption.

## Investments

Default target: 15%.

Contribution targets:

401(k)                 6%
Roth IRA               4%
ESPP                    3%
Taxable Brokerage       2%

Contribution allocation is different from portfolio allocation.

### Contribution allocation

Answers:

"Where is new income being invested?"

### Portfolio allocation

Answers:

"What assets does accumulated wealth currently own?"

Never merge these concepts into a single calculation.

## Plannable Income

Coral may need to account for payroll investment contributions such as:

- 401(k)
- ESPP

that happen before net pay reaches checking.

Therefore, account cash deposits alone may not represent the complete denominator for allocation analysis.

The implementation must explicitly define Plannable Income.

If necessary payroll data is unavailable, return incomplete-data metadata instead of inventing contributions.

## Expected vs Actual

For every master bucket calculate:

- target percentage
- actual percentage
- target amount
- actual amount
- variance amount
- percentage-point variance
- status

Where practical provide category and merchant drill-down.

## Effective dates

Changing a financial plan must not rewrite historical interpretation.

Example:

Plan A:
effective 2026-08-01

Plan B:
effective 2027-01-01

December 2026 uses Plan A.

January 2027 uses Plan B.