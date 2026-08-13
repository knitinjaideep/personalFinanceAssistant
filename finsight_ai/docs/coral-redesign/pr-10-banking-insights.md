# PR 10 — Coral Banking Insights

Add deterministic Coral Banking Insights.

Do not generate generic AI commentary first.

Potential insight types:
- merchant_overspend
- category_overspend
- persistent_wants_overspend
- unusual_spending_spike
- savings_shortfall
- recurring_charge_increase
- merchant_concentration
- classification_uncertainty
- positive_improvement

Insight should conceptually include:
- type
- severity
- title
- summary
- impact_amount
- confidence
- action
- supporting facts

Rank roughly by:
financial impact × deviation × confidence × actionability

Show only the best 3.

LLM may rewrite deterministic facts into natural language.
LLM must not calculate values, invent causes, or invent unsupported advice.

If LLM is unavailable, template-based insights must still work.

Add tests.
