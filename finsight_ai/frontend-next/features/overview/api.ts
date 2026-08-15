import { api } from "@/lib/api-client";

/**
 * Overview page API client (PR 06). Mirrors the backend Pydantic shapes in
 * backend/app/domain/plan_vs_actual.py and backend/app/domain/overview_insights.py
 * as closely as possible so no reshaping happens on the client — the
 * backend is the sole source of truth for every number here (dollar
 * amounts stay as decimal strings, exactly as the API returns them, and are
 * only parsed to `number` at render time for chart libraries).
 */

export type MasterBucket = "needs" | "wants" | "savings" | "investments" | "unclassified";
export type DriftStatus = "on_track" | "watch" | "off_track" | "unknown";
export type StatusTone = "good" | "warning" | "danger" | "neutral";

export interface DashboardPeriodParams {
  startDate?: string; // "YYYY-MM-DD"
  endDate?: string; // "YYYY-MM-DD"
}

// ── Plan vs Actual (GET /api/v1/plan-vs-actual) — PR 04, reused as-is ──────

export interface BucketDrift {
  bucket: MasterBucket;
  target_percentage: string | null;
  actual_percentage: string | null;
  target_amount: string | null;
  actual_amount: string;
  variance_amount: string | null;
  variance_percentage_points: string | null;
  status: DriftStatus;
  transaction_count: number;
}

export interface CompletenessMetadata {
  plan_available: boolean;
  plan_version_changed_mid_period: boolean;
  income_observed: boolean;
  unclassified_transaction_count: number;
  unclassified_amount: string;
  needs_review_count: number;
  origin_only_transfer_legs_count: number;
  origin_only_transfer_legs_amount: string;
  payroll_deduction_signal_detected: boolean;
  notes: string[];
  is_complete?: boolean;
}

export interface Period {
  start: string;
  end: string;
  label: string;
}

export interface PlanVsActualResult {
  period: Period;
  plan_version_id: string | null;
  plan_version_number: number | null;
  plan_effective_from: string | null;
  plannable_income: string;
  buckets: BucketDrift[];
  completeness: CompletenessMetadata;
}

// ── Overview insights (GET /api/v1/overview/insights) — PR 06 ─────────────

export interface FinancialStatus {
  headline: string;
  body: string;
  tone: StatusTone;
  data_available: boolean;
}

export interface CoralInsight {
  title: string;
  description: string;
  tone: StatusTone;
  bucket: MasterBucket | null;
  category: string | null;
  variance_amount: string | null;
  target_amount: string | null;
  /** null for the synthesized "everything is on track" summary insight,
   * which isn't about one bucket and has no actual $ of its own. */
  actual_amount: string | null;
}

export type NextMonthActionType =
  | "reduce_category"
  | "increase_savings_goal"
  | "increase_investment_contribution"
  | "maintain_contribution";

export interface NextMonthPlanItem {
  title: string;
  description: string;
  estimated_impact: string;
  action_type: NextMonthActionType;
  bucket: MasterBucket;
  category: string | null;
  priority: number;
}

export interface OverviewInsightsResult {
  period: Period;
  status: FinancialStatus;
  insights: CoralInsight[];
  next_month_plan: NextMonthPlanItem[];
  completeness: CompletenessMetadata;
}

// ── Next Month Planner (GET /api/v1/next-month-plan) — PR 14 ───────────────
//
// Mirrors backend/app/domain/next_month_planner.py 1:1 — no reshaping.
// Supersedes the lightweight `NextMonthPlanItem` preview above
// (`overview_insights.build_next_month_plan`), which that module's own
// docstring documents as a stand-in for this richer, multi-source planner.
// See docs/NEXT_MONTH_PLANNER.md.

export type RecommendationActionType =
  | "reduce_category"
  | "increase_savings_goal"
  | "maintain_contribution"
  | "increase_investment_contribution"
  | "review_merchant"
  | "review_subscription"
  | "adjust_plan";

export interface RecommendationSourceFact {
  label: string;
  value: string;
}

export interface Recommendation {
  title: string;
  reason: string;
  estimated_impact: string;
  priority: number;
  action_type: RecommendationActionType;
  source_facts: RecommendationSourceFact[];
  bucket: MasterBucket | null;
  category: string | null;
  incomplete_source: boolean;
}

export interface NextMonthPlanResult {
  period: Period;
  recommendations: Recommendation[];
}

// ── Monthly Close (GET /api/v1/monthly-close) — PR 15 ──────────────────────

export type MonthlyCloseStatus = "good" | "warning" | "danger" | "neutral";

export interface MonthlyCloseLineItem {
  label: string;
  bucket: MasterBucket | null;
  target_amount: string | null;
  actual_amount: string;
  variance_amount: string | null;
  status: MonthlyCloseStatus;
  note: string | null;
}

export interface MonthlyCloseDriver {
  merchant: string;
  bucket: MasterBucket;
  category: string | null;
  amount: string;
  transaction_count: number;
}

export interface MonthlyCloseGoalProgress {
  name: string;
  category_name: string;
  current_amount: string;
  target_amount_effective: string | null;
  variance_amount: string | null;
  status: string;
  incomplete_source: boolean;
}

export interface MonthlyCloseResult {
  period: Period;
  generated_on: string;
  is_completed_month: boolean;
  summary: string;
  line_items: MonthlyCloseLineItem[];
  went_well: CoralInsight[];
  needs_attention: CoralInsight[];
  biggest_drivers: MonthlyCloseDriver[];
  goal_progress: MonthlyCloseGoalProgress[];
  next_month_plan: Recommendation[];
  completeness_notes: string[];
}

// ── Monthly flow (GET /api/v1/overview/monthly-flow) — PR 06 ───────────────

export interface MonthlyFlowSummary {
  period_label: string;
  start: string;
  end: string;
  income: string;
  spent: string;
  saved_invested: string;
  income_observed: boolean;
}

function periodQuery(period?: DashboardPeriodParams) {
  return { start_date: period?.startDate, end_date: period?.endDate };
}

export const overviewApi = {
  planVsActual: (period?: DashboardPeriodParams): Promise<PlanVsActualResult> =>
    api.get<PlanVsActualResult>("/plan-vs-actual", periodQuery(period)),

  insights: (period?: DashboardPeriodParams): Promise<OverviewInsightsResult> =>
    api.get<OverviewInsightsResult>("/overview/insights", periodQuery(period)),

  monthlyFlow: (period?: DashboardPeriodParams): Promise<MonthlyFlowSummary[]> =>
    api.get<MonthlyFlowSummary[]>("/overview/monthly-flow", periodQuery(period)),

  nextMonthPlan: (period?: DashboardPeriodParams): Promise<NextMonthPlanResult> =>
    api.get<NextMonthPlanResult>("/next-month-plan", periodQuery(period)),

  monthlyClose: (period?: DashboardPeriodParams): Promise<MonthlyCloseResult> =>
    api.get<MonthlyCloseResult>("/monthly-close", periodQuery(period)),
};
