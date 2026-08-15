# Monthly Coral Close

PR 15 adds a read-only monthly close report. It is a summary experience, not
an accounting lock or persisted snapshot.

## Data sources

The close composes existing deterministic surfaces:

- Plan vs Actual for Income, Needs, Wants, Savings, and Investments line
  items.
- Overview insights for "what went well" and "needs attention".
- Plan vs Actual merchant drivers for biggest drivers.
- Savings Goals for goal progress.
- Next Month Planner for follow-up actions.

No LLM calculates or changes totals, targets, variances, statuses, drivers,
or next-month impacts. No duplicate derived financial values are persisted.

## API

`GET /api/v1/monthly-close`

Query params match the shared period contract:

- `year` + `month`, or
- `start_date` + `end_date`
- optional `account_id`

The response includes:

- `line_items`: Income and the four plan buckets with target, actual,
  variance, and status.
- `went_well`
- `needs_attention`
- `biggest_drivers`
- `goal_progress`
- `next_month_plan`
- `is_completed_month`, so the UI can be honest when the selected period is
  still in progress.

## Frontend

Overview links to `/monthly-close` with the current selected period. The
Monthly Close page keeps the shared period selector so historical closes can
be reviewed without a modal or blocking popup.
