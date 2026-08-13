# PR 14 — Coral Next Month Planner

Build Coral's Next Month Planner.

Do not build an autonomous financial agent.
Do not automatically change accounts, contributions, or investments.

Planner inputs:
- Financial Plan
- Current month actuals
- Recent trends
- Savings goals
- Investment contribution gaps

Recommendations should be deterministic before any LLM wording.

Recommendation fields:
- title
- reason
- estimated impact
- priority
- source facts
- action type

Potential actions:
- reduce_category
- increase_savings_goal
- maintain_contribution
- increase_investment_contribution
- review_merchant
- review_subscription
- adjust_plan

Do not always try to make up every historical shortfall next month.
Document sensible planning rules.

LLM may rewrite a structured recommendation, but must not invent the math.

Expose to:
- Overview -> Next Month Plan
- Banking -> insights/actions
- Investments -> contribution plan

Add tests.

Create docs/NEXT_MONTH_PLANNER.md.
