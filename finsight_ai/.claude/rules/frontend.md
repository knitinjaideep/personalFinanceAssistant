---
paths:
  - "frontend/**"
  - "app/**"
  - "components/**"
  - "src/**/*.tsx"
  - "src/**/*.ts"
---

# Coral Frontend Rules

Follow existing Next.js architecture and naming conventions.

Prefer reusable components over page-specific duplication.

Do not put financial calculations inside React components.

Frontend receives authoritative computed financial values from backend APIs.

## UI principles

Coral financial pages follow:

PLAN → ACTUAL → DRIFT → ACTION

The UI should prioritize:

1. what was expected
2. what happened
3. where the user is off plan
4. what action is worth considering

Do not create dashboards containing many unrelated KPI cards.

Use strong visual hierarchy and whitespace.

Use existing design tokens before adding new ones.

Support:

- light mode
- dark mode
- 1440px laptop
- 1920px desktop
- 2560px desktop
- tablet

Avoid tiny typography on large monitors.

Prefer responsive sizing and `clamp()` where appropriate.

## Charts

Charts must receive normalized data.

Do not perform hidden financial reconciliation inside visualization components.

Charts must have:

- loading state
- empty state
- error state
- accessible textual labels or summaries where practical

## Animation

Motion should communicate change.

Good:
- period transitions
- flow changes
- bar interpolation
- subtle hover feedback

Avoid:
- infinite decorative animation
- excessive parallax
- distracting shimmer