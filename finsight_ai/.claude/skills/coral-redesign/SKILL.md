---
name: coral-redesign
description: Domain and workflow guidance for implementing Coral's Plan → Actual → Drift → Action redesign across Overview, Banking, Investments, financial classification, planning, and insights.
---

# Coral Redesign

Use this skill whenever implementing or reviewing the Coral financial-dashboard redesign.

Before making architectural decisions, read the relevant references in this skill.

References:

- `references/financial-model.md`
- `references/accounting-invariants.md`
- `references/design-rules.md`
- `references/workflow.md`

## Product principle

Coral must move away from:

"show the user lots of financial numbers"

toward:

PLAN → ACTUAL → DRIFT → ACTION

Every primary page should answer one user question.

### Overview

How am I doing?

### Banking

Where did my cash go?

### Investments

Am I investing according to plan?

## Primary allocation model

Master targets:

- Needs: 50%
- Wants: 20%
- Savings: 15%
- Investments: 15%

Savings targets:

- Emergency Fund: 5%
- House / Goals: 5%
- Child Savings: 5%

Investment contribution targets:

- 401(k): 6%
- Roth IRA: 4%
- ESPP: 3%
- Taxable Brokerage: 2%

These are configurable financial-plan values and must not become permanent hard-coded presentation constants where a stored plan exists.

## Core UX principle

Standalone values are secondary.

Prefer:

Target
Actual
Variance
Meaning

For example:

House Savings

Target: $600
Actual: $420
Gap: -$180

instead of merely:

House Savings: $420

## Dollar-first communication

When explaining a financial deviation:

prefer:

"$240 above plan"

over:

"2.1 percentage points above target"

Percentages can remain supporting information.

## Coral Insights

Insights must originate from deterministic facts.

Maximum three high-value insights should normally appear on overview surfaces.

Rank for:

- impact
- deviation
- confidence
- actionability

An LLM can explain facts but must not manufacture the facts.

## Existing functionality

The redesign must coexist with:

- Chat
- Documents
- existing upload flows
- existing parsers

These are not redesign targets unless explicitly stated in a phase specification.

## Workflow

Each redesign phase must follow the workflow described in:

`references/workflow.md`

Do not declare a phase complete before independent review and verification.