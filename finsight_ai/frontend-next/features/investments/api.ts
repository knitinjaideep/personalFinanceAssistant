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
}

export const investmentsApi = {
  investments: (): Promise<InvestmentsDashboard> =>
    api.get<InvestmentsDashboard>("/dashboard/investments"),
};
