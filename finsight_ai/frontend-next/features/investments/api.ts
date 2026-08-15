import { api } from "@/lib/api-client";

export interface AccountBalance {
  account_name: string;
  account_type: string;
  institution_type: string;
  total_value: number;
  total_value_fmt: string;
  invested_value: number;
  cash_value: number;
  unrealized_gain_loss: number;
  unrealized_gain_loss_fmt: string;
  gain_loss_pct: number | null;
  snapshot_date: string | null;
  latest_statement_date: string | null;
}

export interface PortfolioSummary {
  total_portfolio_value: number;
  total_portfolio_value_fmt: string;
  total_unrealized_gain_loss: number;
  total_unrealized_gain_loss_fmt: string;
  last_updated: string | null;
  accounts: AccountBalance[];
}

export interface Holding {
  symbol: string | null;
  description: string;
  market_value: number;
  market_value_fmt: string;
  unrealized_gain_loss: number;
  unrealized_gain_loss_fmt: string;
  cost_basis: number;
  quantity: number | null;
  asset_class: string | null;
  account_name: string;
  institution_type: string;
  portfolio_weight: number | null;
}

export interface InvestmentsDashboard {
  portfolio_summary: PortfolioSummary;
  allocation: Array<AccountBalance & { pct_of_portfolio: number }>;
  top_holdings: Holding[];
  top_gainers: Holding[];
  top_losers: Holding[];
  balance_history: Array<{
    date: string;
    total_value: number;
    account_name: string;
    institution_type: string;
  }>;
  coverage: Array<{
    institution: string;
    institution_type: string;
    doc_count: number;
    earliest_statement: string | null;
    latest_statement: string | null;
  }>;
  /** The resolved {start_date, end_date} the backend actually applied, or
   * null when no range was requested (PR 05 unified period contract). */
  period: { start_date: string; end_date: string } | null;
}

export interface DashboardPeriodParams {
  startDate?: string; // "YYYY-MM-DD"
  endDate?: string;   // "YYYY-MM-DD"
}

export type InvestmentDriftStatus = "on_track" | "watch" | "off_track" | "unknown";

export interface InvestmentContributionCompleteness {
  status: "complete" | "incomplete";
  is_complete: boolean;
  income_observed: boolean;
  plan_available: boolean;
  payroll_data_complete: boolean;
  notes: string[];
}

export interface InvestmentContributionVehicle {
  vehicle: string;
  target_pct: string | null;
  actual_pct: string | null;
  target_amount: string | null;
  actual_amount: string;
  variance_amount: string | null;
  variance_pct_points: string | null;
  status: InvestmentDriftStatus;
  data_completeness: InvestmentContributionCompleteness;
  recommended_next_month_delta: string | null;
  transaction_count: number;
}

export interface InvestmentContributionPlanResult {
  period: {
    start: string;
    end: string;
    label: string;
  };
  plannable_income: string;
  vehicles: InvestmentContributionVehicle[];
  total_target_pct: string | null;
  total_actual_amount: string;
  total_actual_pct: string | null;
  completeness: {
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
  };
}

function periodQuery(period?: DashboardPeriodParams) {
  return { start_date: period?.startDate, end_date: period?.endDate };
}

export const investmentsApi = {
  /**
   * `startDate`/`endDate` (PR 05 unified period contract, see
   * lib/period.ts) narrow `fees`/`balance_history` to that range. Current
   * portfolio/holdings state is always the latest snapshot regardless of
   * period — see GET /dashboard/investments docstring.
   */
  investments: (period?: DashboardPeriodParams): Promise<InvestmentsDashboard> =>
    api.get<InvestmentsDashboard>("/dashboard/investments", periodQuery(period)),

  contributionPlan: (period?: DashboardPeriodParams): Promise<InvestmentContributionPlanResult> =>
    api.get<InvestmentContributionPlanResult>("/investment-plan/contributions", periodQuery(period)),
};
