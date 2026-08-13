# Coral Redesign Milestones

## M1 — Transaction Intelligence

Tasks:

- PR03 Transaction Classification
- PR04 Plan vs Actual Engine

Definition of done:

- transaction classifications support master buckets
- user overrides supported
- transfer double counting prevented
- Plan vs Actual works deterministically
- financial invariant tests pass

## M2 — Period Model

Tasks:

- PR05 Global Period Filter

Definition of done:

- Overview, Banking, Investments share one period model
- URL/navigation state works
- backend date-range querying works

## M3 — Overview

Tasks:

- PR06 Overview Redesign

Definition of done:

- page answers "How am I doing?"
- Income vs Spent vs Saved/Invested works
- Plan vs Actual works
- max 3 insights
- no document-dashboard dominance
- responsive states work

## M4 — Banking

Tasks:

- PR07 Banking Flow
- PR08 Banking Drift
- PR09 Classification Review
- PR10 Banking Insights

Definition of done:

- Banking answers "Where did my cash go?"
- flow visualization uses normalized backend data
- drift table works
- merchant drivers work
- uncertain classification can be corrected
- insights are deterministic
- internal transfers excluded

## M5 — Investments

Tasks:

- PR11 Investment Contribution Model
- PR12 Investments UI

Definition of done:

- contribution allocation is separated from portfolio allocation
- Investment contribution tree works
- Plan vs Actual contributions work
- next-month contribution guidance works
- incomplete payroll data is represented honestly

## M6 — Goals & Advisor

Tasks:

- PR13 Savings Goals
- PR14 Next Month Planner
- PR15 Monthly Close

Definition of done:

- Savings goals support 5/5/5 structure
- completed goals do not auto-reallocate without user approval
- deterministic next-month recommendations exist
- monthly financial close works

## M7 — UI Completion

Tasks:

- PR16 Cleanup
- PR17 Dark Mode
- PR18 Responsive
- PR19 Motion

Definition of done:

- old dashboard clutter removed
- light/dark coherent
- all target resolutions tested
- motion is subtle and reduced-motion aware

## M8 — Final Audit

Tasks:

- PR20 Final Audit

Definition of done:

- full verification passes
- no known financial-correctness regressions
- final audit document produced