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
}

export const bankingApi = {
  banking: (months = 12): Promise<BankingDashboard> =>
    api.get<BankingDashboard>("/dashboard/banking", { months }),
};
