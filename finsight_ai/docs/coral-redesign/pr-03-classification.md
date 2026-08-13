# PR 03 — Transaction Classification Architecture

Build the transaction classification layer required for Coral's Needs/Wants/Savings/Investments redesign.

Do not redesign the pages yet.
Do not let the LLM become responsible for financial arithmetic.
Do not classify transfers as spending.
Keep SQLite.

## Objective

Every relevant financial record should be classifiable into:

### Cash Flow Type
- income
- expense
- transfer
- savings_contribution
- investment_contribution
- investment_activity
- refund
- other

### Master Bucket
- needs
- wants
- savings
- investments
- unclassified

### Categories

Needs:
- Housing
- Utilities
- Connectivity
- Groceries
- Transportation
- Insurance
- Healthcare
- Minimum Debt

Wants:
- Dining
- Entertainment
- Travel
- Shopping
- Personal Care
- Fitness/Hobbies
- Home Decor
- Gifts/Celebrations

Savings:
- Emergency Fund
- House / Goals
- Child Savings

Investments:
- 401(k)
- Roth IRA
- ESPP
- Taxable Brokerage

Support classification_source:
- deterministic_rule
- existing_category
- user
- llm
- heuristic
- unknown

Support classification_confidence and ideally needs_review.

Some merchants cannot reliably be classified solely from statement data:
Amazon, Target, Walmart, Costco, CVS.

Do not pretend these are always known.

## User Overrides

User classification always wins.

Support rule scope conceptually:
- transaction only
- merchant future
- merchant + account future
- category mapping

Suggested precedence:
1. explicit user transaction override
2. explicit user merchant rule
3. deterministic known transfer/investment rules
4. trusted existing category mapping
5. heuristic/merchant classifier
6. LLM fallback
7. unclassified

Preserve original imported category information.
Never destructively overwrite raw transaction data.

Build or extend a TransactionClassificationService responsible for:
- classifying transactions
- batch classification
- resolving final classification
- source/confidence
- user overrides
- merchant rules
- uncertain transactions

If classification logic already exists, extend/refactor instead of duplicating it.

Tests:
- rent -> Needs/Housing
- restaurant -> Wants/Dining
- internal transfer -> Transfer, not spending
- HYSA transfer can be Savings when appropriate
- investment contribution -> Investments
- user override beats model
- merchant rule beats LLM
- ambiguous Amazon can be flagged for review
- refunds do not inflate spending
- credit-card payments are not counted again as expenses

Create docs/TRANSACTION_CLASSIFICATION.md.
Do not build UI yet.
