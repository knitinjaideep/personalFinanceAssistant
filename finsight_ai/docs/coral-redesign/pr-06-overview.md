# PR 06 — Redesign Overview

Completely redesign Coral's Overview/Home financial content using the redesign mockup under /docs/design/ as the visual north star.

Do not copy mockup values.
Use actual API data.
Use demo fixtures only in development/test modes.
Do not change the chatbot.
Do not log raw user financial values.

Primary question:

"How am I doing financially?"

The user should understand the month in about 10 seconds.

Remove the document-centric dashboard as the dominant Home experience.
Document processing belongs on Documents.

## Structure

1. Financial status header
Example: "You're slightly off plan this month."
Short deterministic explanation.

2. Shared FinancialPeriodSelector.

3. Large grouped bar chart:
Income vs Spent vs Saved/Invested.
For multi-month selections show monthly groups.

4. Plan vs Actual:
Needs, Wants, Savings, Investments.
Each row shows target %, actual %, target $, actual $, variance $.
Dollar drift should be visually prominent.

5. Coral Insights:
Maximum three actionable insights.

6. Next Month Plan:
Small focused section driven by deterministic engine output.

## Visual Direction

- premium
- lots of whitespace
- subtle underwater artwork at edges
- readable central zone
- larger typography
- minimal KPI clutter
- soft cards
- restrained mascot
- clear semantic status colors

Demote/remove from Home as dominant content:
- Total Documents
- Processed
- Processing
- Failed
- Banking Docs
- Investment Docs
- Recent Uploads

Do not delete upload functionality.

Create polished loading, empty, partial-data, error, and first-time states.

Test at:
- 1440x900
- 1920x1080
- 2560x1440
- tablet

Do not modify Banking or Investments in this PR.
