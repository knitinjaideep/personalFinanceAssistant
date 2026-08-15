# Coral Redesign Final Audit

Date: 2026-08-15
Branch: feature/coral-plan-vs-actual-redesign

## PASS

- Financial correctness: backend financial invariant suite passed. Coverage includes checking/savings transfer legs, brokerage/investment transfers, credit-card payments, refunds, rollovers, savings goals, investment contributions, Plan vs Actual, Banking Insights, and Next Month Planner.
- Plan correctness: default plan is 50% Needs, 20% Wants, 15% Savings, and 15% Investments. Historical Plan vs Actual resolves the plan effective at the period start and marks mid-period plan changes as completeness metadata instead of silently blending versions.
- Classification precedence: transaction classification preserves user override > merchant rule > deterministic rules/existing categories/heuristics > optional LLM fallback > unknown. Plan vs Actual backfill only classifies previously unclassified rows, so existing user decisions are not recomputed.
- LLM boundaries: dashboard math, Plan vs Actual, Savings Goals, Investment Contributions, Banking Insights, Next Month Planner, and Monthly Close use deterministic domain/service code. Chat LLM paths receive precomputed fact bundles or narrative context and are covered by grounding/verifier tests; tests passed.
- UI integrity: Overview, Banking, Investments, Documents, Chat, Upload, and Monthly Close compile in production. Frontend unit tests for redesigned dashboard flows passed. M7 also added first-paint theme selection, responsive PageShell widths/tokens, opt-in hover elevation, and reduced-motion-aware Framer Motion paths.
- Privacy: production frontend logging of route timing is development-gated. Backend logs reviewed in changed redesign paths; they log IDs/counts/status, not raw statement contents or raw financial rows. Script/debug/eval logging remains command-line only.
- Performance: final audit fixed an unnecessary full-history auto-classification pass in Plan vs Actual. Period-scoped Plan vs Actual requests now backfill only transactions inside the requested period.
- Accessibility: M7 reduced-motion behavior avoids stripping static transforms globally, theme respects stored/system preference before hydration, key dashboard components retain semantic headings/state text, and progress/chart primitives include text alternatives where implemented.
- Existing functionality: full backend suite and frontend suite passed, covering Chat, Documents, Upload/reprocess, parsers, endpoint parity, financial APIs, dashboard period filters, and redesign APIs.
- SQLite: migrations remain idempotent/backwards-compatible via checked add-column and nullable-rebuild paths. Full backend tests create fresh SQLite databases successfully.

## ISSUES FIXED

- Fixed Plan vs Actual auto-classification backfill scope.
  - Before: every period request classified all unclassified transactions in history.
  - After: backfill is bounded by `period.start` and `period.end`.
  - Regression coverage: `test_auto_classification_backfill_is_bounded_to_requested_period`.

## KNOWN LIMITATIONS

- No separate browser-automation harness is installed in `frontend-next`; Playwright was unavailable, so final viewport screenshots at target resolutions were not captured. Production build route generation and component tests did pass.
- Full-repo Ruff currently reports pre-existing unrelated issues across legacy backend files. Scoped Ruff on M8-changed backend files passed.
- Next Month Planner intentionally does not emit `review_subscription` trend recommendations yet because the codebase does not have a reusable recent-trend primitive.
- Frontend lint has 13 pre-existing warnings in Chat/Documents/Upload components; no lint errors remain.
- Backend tests emit existing `datetime.utcnow()` deprecation warnings from model/test paths.

## FUTURE WORK

- Add Playwright or an equivalent browser smoke harness for `/`, `/banking`, `/investments`, `/monthly-close`, `/documents`, `/chat`, and upload modal at 1440px, 1920px, 2560px, tablet, and mobile widths.
- Clean the legacy Ruff backlog so full-repo lint can become a required gate.
- Add a deterministic subscription/trend detector that Next Month Planner can reuse without LLM arithmetic.
- Replace remaining `datetime.utcnow()` usage with timezone-aware UTC datetimes.

## Verification

- Backend focused: `PYTHONPATH=. .venv/bin/pytest tests/test_plan_vs_actual.py tests/financial_invariants/test_plan_vs_actual_invariants.py tests/test_next_month_planner_api.py tests/test_monthly_close.py` — 54 passed.
- Backend full: `PYTHONPATH=. .venv/bin/pytest tests` — 610 passed.
- Backend scoped Ruff: `.venv/bin/ruff check app/services/plan_vs_actual.py tests/test_plan_vs_actual.py` — passed.
- Frontend tests: `npm test` — 9 files, 78 tests passed.
- Frontend lint: `npm run lint` — 0 errors, 13 pre-existing warnings.
- Frontend production build: `npm run build` — passed.
- Frontend typecheck: `npm run typecheck` — passed after build-generated `.next/types`.
- Whitespace: `git diff --check` — passed.
