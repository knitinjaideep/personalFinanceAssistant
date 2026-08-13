import { api } from "@/lib/api-client";

export interface SpendByMonth {
  month: string;
  total_spend: number;
  total_spend_fmt: string;
  transaction_count: number;
}

export interface SpendByCategory {
  category: string;
  total: number;
  total_fmt: string;
  transaction_count: number;
}

export interface TopMerchant {
  merchant: string;
  total: number;
  total_fmt: string;
  transaction_count: number;
}

export interface CardSpend {
  account_name: string;
  account_type: string;
  institution_type: string;
  product_label: string;
  total_spend: number;
  total_spend_fmt: string;
  transaction_count: number;
  latest_statement: string | null;
}

export interface CashFlowMonth {
  month: string;
  inflow: number;
  outflow: number;
  net: number;
}

export interface Subscription {
  merchant: string;
  category: string | null;
  avg_monthly_amount: number;
  avg_monthly_amount_fmt: string;
  occurrences: number;
  last_seen: string | null;
  confidence: "high" | "medium";
}

export interface InstitutionCoverage {
  institution: string;
  institution_type: string;
  doc_count: number;
  earliest_statement: string | null;
  latest_statement: string | null;
  missing_recent_data?: boolean;
}

export interface BankingDashboard {
  spend_by_month: SpendByMonth[];
  spend_by_category: SpendByCategory[];
  top_merchants: TopMerchant[];
  card_summary: CardSpend[];
  cash_flow: CashFlowMonth[];
  subscriptions: Subscription[];
  coverage: InstitutionCoverage[];
  /** The resolved {start_date, end_date} the backend actually applied, or
   * null when no range was requested (PR 05 unified period contract). */
  period: { start_date: string; end_date: string } | null;
}

export interface DashboardPeriodParams {
  startDate?: string; // "YYYY-MM-DD"
  endDate?: string;   // "YYYY-MM-DD"
}

export const bankingApi = {
  /**
   * `startDate`/`endDate` (PR 05 unified period contract, see
   * lib/period.ts) take precedence over the legacy `months` rolling window
   * when provided — the backend always queries by the resolved range, never
   * fetches everything and filters client-side.
   */
  banking: (months = 12, period?: DashboardPeriodParams): Promise<BankingDashboard> =>
    api.get<BankingDashboard>("/dashboard/banking", {
      months,
      start_date: period?.startDate,
      end_date: period?.endDate,
    }),
};
