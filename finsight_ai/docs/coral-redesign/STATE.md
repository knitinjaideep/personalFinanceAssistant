# Coral Redesign State

Branch: feature/coral-plan-vs-actual-redesign

Status: COMPLETE

## Completed foundational work

- [x] Repository redesign audit
- [x] Coral design system

## Milestones

### M1 — Transaction Intelligence

- [x] PR03 Transaction Classification
- [x] PR04 Plan vs Actual Engine (blocked mid-review on transfer-leg double-counting policy; resolved via user decision — Option C, coverage-aware hybrid — documented in BLOCKED.md; repaired and re-verified)

Commit: 5476236

### M2 — Period Model

- [x] PR05 Global Period Filter

Commit: b894266

### M3 — Overview

- [x] PR06 Overview Redesign

Commit: b2e019a

### M4 — Banking

- [x] PR07 Banking Flow
- [x] PR08 Banking Drift (blocked mid-review on Top Drivers' category-level drift baseline for Needs/Wants — plan has no per-category targets; resolved via user decision — Option B, bucket-level anchor — documented in BLOCKED.md; repaired and re-verified)
- [x] PR09 Classification Review
- [x] PR10 Banking Insights

Commit: 32dab94

### M5 — Investments

- [x] PR11 Investment Contribution Model
- [x] PR12 Investments UI

Commit: 1c7d604

### M6 — Goals & Advisor

- [x] PR13 Savings Goals
- [x] PR14 Next Month Planner
- [x] PR15 Monthly Close

Commit: 731aa5d

### M7 — UI Completion

- [x] PR16 Cleanup
- [x] PR17 Dark Mode
- [x] PR18 Responsive
- [x] PR19 Motion

Commit: dc50e05

### M8 — Final Audit

- [x] PR20 Final Audit

Commit: 21476d0

## Current blocker

None.

## Account Value Refinement

### Prompt 1 — Shared account-value foundation

- [x] Opened and inspected approved Banking and Investments mockups.
- [x] Added read-only Banking account-value history from existing balance snapshots.
- [x] Added shared frontend account-value normalization and reusable UI primitives.
- [x] Verified account-value deltas use latest snapshot minus previous available monthly snapshot.

Commit: included in Prompt 1 commit

### Prompt 2 — Banking account-value page

- [x] Banking page now leads with the approved account-value hierarchy.
- [x] Added data-driven account summary cards with inline selected-account detail.
- [x] Added Account Value Trends line/table view using the shared monthly snapshot dataset.
- [x] Preserved existing cash-flow, drift, review, insight, and planner sections below.

Commit: included in Prompt 2 commit

## Notes

Update this file only after verification passes.

Each completed milestone should include its resulting commit SHA.
