# Coral Redesign UI Rules

## Overall direction

Coral should feel:

- calm
- premium
- readable
- modern
- lightly playful
- unmistakably Coral

Keep the underwater identity but reduce visual interference with financial data.

Decorative ocean artwork should mostly live around outer edges and low-information regions.

## Page hierarchy

Each major page should have one dominant question.

### Overview

How am I doing?

Primary components:

1. period selector
2. financial status summary
3. Income vs Spent vs Saved/Invested
4. Plan vs Actual
5. Coral Insights
6. Next Month Plan

### Banking

Where did my cash go?

Primary components:

1. period selector
2. Banking Flow Tree
3. Where You're Off Plan
4. Top Drivers
5. Classification Review
6. Banking Insights

### Investments

Am I investing according to plan?

Primary components:

1. period selector
2. Investment Contribution Tree
3. Plan vs Actual Contributions
4. Next Month Contribution Plan
5. Portfolio Health
6. Investment Insights
7. account details lower in hierarchy

## Information density

Do not create grids of unrelated cards simply because data exists.

Raw balances and transaction tables are drill-down information.

Do not make them the main visual hierarchy.

## Variance

Prefer comparisons:

Expected → Actual → Gap

instead of isolated values.

## Insights

Maximum three prominent insights per primary surface.

## Typography

Use strong hierarchy.

Do not allow typography to become tiny on large screens.

Support fluid scaling with `clamp()` where appropriate.

## Layout targets

Explicitly inspect:

1366x768
1440x900
1512x982
1920x1080
2560x1440
iPad landscape
iPad portrait

## Motion

Motion communicates state change.

Examples:

- month changes
- bar updates
- flow width changes
- page navigation

Avoid decorative motion competing with financial content.

Respect reduced-motion preferences.

## Dark mode

Dark mode should be intentionally designed.

Prefer deep underwater/navy surfaces instead of naive color inversion.

Maintain semantic status readability.