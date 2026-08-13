# PR 13 — Savings Goal Engine

Implement proper Savings Goal tracking.

Savings total target: 15%

Sub-targets:
- Emergency Fund: 5%
- House / Goals: 5%
- Child Savings: 5%

Goals should not be inferred only from account names.
One savings account may support multiple goals.

Support explicit goal mapping.

Goal model should support conceptually:
- name
- type
- target_amount
- current_amount
- target_percentage_of_income
- account mappings
- status
- priority
- effective date

Emergency fund may support target_months_of_expenses such as 3 or 6 months.

Do not automatically redirect money when a goal is complete.
Generate a recommendation and require user approval for plan changes.

Statuses:
- not_started
- behind
- on_track
- complete

Expose APIs needed by Overview and Banking.

Add tests.
