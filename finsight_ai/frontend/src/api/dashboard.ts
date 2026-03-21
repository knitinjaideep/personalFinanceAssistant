import { api } from "./client";

// ── Summary ──────────────────────────────────────────────────────────────────

export interface DashboardSummary {
  total_documents: number;
  total_statements: number;
  total_transactions: number;
  total_fees: number;
  total_holdings: number;
  total_accounts: number;
  total_institutions: number;
  earliest_statement: string | null;
  latest_statement: string | null;
}

// ── Investments ───────────────────────────────────────────────────────────────

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
  snapshot_date: string;
}

export interface PortfolioSummary {
  total_portfolio_value: number;
  total_portfolio_value_fmt: string;
  total_unrealized_gain_loss: number;
  total_unrealized_gain_loss_fmt: string;
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
}

export interface BalanceHistoryPoint {
  date: string;
  total_value: number;
  account_name: string;
  institution_type: string;
}

export interface FeesSummary {
  total_fees: number;
  total_fees_fmt: string;
  by_category: Array<{ category: string; count: number; total: number; total_fmt: string }>;
}

export interface InstitutionCoverage {
  institution: string;
  institution_type: string;
  doc_count: number;
  earliest_statement: string | null;
  latest_statement: string | null;
}

export interface InvestmentsDashboard {
  portfolio_summary: PortfolioSummary;
  allocation: Array<AccountBalance & { pct_of_portfolio: number }>;
  top_holdings: Holding[];
  top_gainers: Holding[];
  top_losers: Holding[];
  fees: FeesSummary;
  balance_history: BalanceHistoryPoint[];
  coverage: InstitutionCoverage[];
}

// ── Banking ───────────────────────────────────────────────────────────────────

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

// ── Coverage ──────────────────────────────────────────────────────────────────

export interface ProductCoverage {
  product: string;
  institution_type: string;
  source_id: string;
  doc_count: number;
  parsed: number;
  latest_statement: string | null;
}

export interface CoverageDashboard {
  by_institution: InstitutionCoverage[];
  by_product: ProductCoverage[];
  latest_statement_dates: Array<{ institution_type: string; latest_statement: string | null }>;
}

// ── API calls ─────────────────────────────────────────────────────────────────

export const dashboardApi = {
  summary: (): Promise<DashboardSummary> =>
    api.get<DashboardSummary>("/dashboard/summary"),

  investments: (): Promise<InvestmentsDashboard> =>
    api.get<InvestmentsDashboard>("/dashboard/investments"),

  banking: (months = 12): Promise<BankingDashboard> =>
    api.get<BankingDashboard>("/dashboard/banking", { months }),

  coverage: (): Promise<CoverageDashboard> =>
    api.get<CoverageDashboard>("/dashboard/coverage"),
};
