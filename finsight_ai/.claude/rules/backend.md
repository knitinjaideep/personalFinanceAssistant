---
paths:
  - "backend/**"
  - "app/**/*.py"
  - "services/**/*.py"
  - "repositories/**/*.py"
  - "tests/**/*.py"
---

# Coral Backend Rules

Financial values must be deterministic.

Separate:

API layer
→ application/service layer
→ repository/data layer

Do not mix SQL/data-access logic into route handlers unless the existing architecture explicitly does so.

## Financial records

Always distinguish:

- income
- expense
- transfer
- savings contribution
- investment contribution
- investment activity
- refund

Transfers are not ordinary consumption.

Credit-card payments must not duplicate card purchase spending.

Investment rollovers must not count as new monthly investing.

Refunds must reverse or adjust appropriate economic activity.

## Classification precedence

Final classification precedence:

1. explicit user transaction override
2. explicit user merchant rule
3. deterministic transfer/investment rule
4. trusted imported category
5. heuristic
6. LLM
7. unknown

LLM classifications must contain confidence/source metadata where supported.

Do not invent precision for ambiguous merchants.

## Testing

Any change to financial calculations should include invariant tests.

Prefer synthetic fixtures representing realistic account flows.