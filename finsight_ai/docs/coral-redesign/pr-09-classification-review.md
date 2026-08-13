# PR 09 — Needs/Wants Classification Review UX

Implement a compact Banking section:

Needs vs Wants Review
or
Transactions to Review

Do not show every transaction.

Prioritize:
- low-confidence transactions
- ambiguous merchants
- high financial impact
- transactions that materially affect plan results

Each row:
- Merchant
- Date
- Amount
- Current classification
- Review/confidence status when useful

Actions:
- Looks right
- Change

Change options:
- Needs
- Wants
- Savings
- Investments
- Transfer
- Other / Unclassified

Then category.

Then scope:
- Only this transaction
- Future transactions from this merchant
- optionally all matching transactions this month

Never silently rewrite all historical transactions.
User decision overrides automation.
Do not call the LLM for every edit.

Persist through the classification service.

After save:
- update classification
- recompute affected Plan vs Actual
- update Banking
- keep Overview/insights consistent on next fetch

Add tests for:
- transaction-only correction
- merchant rule creation
- error/undo path
- plan recomputation
