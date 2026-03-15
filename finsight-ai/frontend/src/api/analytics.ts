/**
 * Analytics API client — Phase 3 bucket-aware endpoints + legacy endpoints.
 */

import { api } from "./client";
import type {
  AnalyticsEnvelope,
  BankingOverview,
  FeeAnalyticsResponse,
  BalancePoint,
  InvestmentsOverview,
  InvBalancePoint,
  MissingStatement,
  Subscription,
} from "../types";

// ── Phase 3: Investments ──────────────────────────────────────────────────────

export const investmentsApi = {
  getOverview: (params?: {
    account_ids?: string;
    start_date?: string;
    end_date?: string;
  }): Promise<AnalyticsEnvelope<InvestmentsOverview>> =>
    api.get<AnalyticsEnvelope<InvestmentsOverview>>(
      "/analytics/investments",
      params
    ),

  getPortfolioTrend: (params?: {
    account_ids?: string;
    start_date?: string;
    end_date?: string;
  }): Promise<AnalyticsEnvelope<InvBalancePoint[]>> =>
    api.get<AnalyticsEnvelope<InvBalancePoint[]>>(
      "/analytics/investments/portfolio",
      params
    ),
};

// ── Phase 3: Banking ──────────────────────────────────────────────────────────

export const bankingApi = {
  getOverview: (params?: {
    institution_ids?: string;
    account_ids?: string;
    start_date?: string;
    end_date?: string;
  }): Promise<AnalyticsEnvelope<BankingOverview>> =>
    api.get<AnalyticsEnvelope<BankingOverview>>("/analytics/banking", params),

  getSpendBreakdown: (params?: {
    institution_ids?: string;
    account_ids?: string;
    start_date?: string;
    end_date?: string;
  }): Promise<AnalyticsEnvelope<{ by_category: Record<string, string>; by_merchant: unknown[] }>> =>
    api.get("/analytics/banking/spend", params),

  getSubscriptions: (params?: {
    institution_ids?: string;
    account_ids?: string;
    lookback_days?: number;
  }): Promise<AnalyticsEnvelope<Subscription[]>> =>
    api.get<AnalyticsEnvelope<Subscription[]>>(
      "/analytics/banking/subscriptions",
      params
    ),
};

// ── Legacy endpoints (unchanged) ─────────────────────────────────────────────

export const analyticsApi = {
  getFees: (params?: {
    start_date?: string;
    end_date?: string;
    institution_type?: string;
  }): Promise<FeeAnalyticsResponse> =>
    api.get<FeeAnalyticsResponse>("/analytics/fees", params),

  getBalances: (params?: {
    account_id?: string;
    institution_type?: string;
    limit?: number;
  }): Promise<BalancePoint[]> =>
    api.get<BalancePoint[]>("/analytics/balances", params),

  getMissing: (
    year?: number
  ): Promise<{ year: number; missing: MissingStatement[] }> =>
    api.get("/analytics/missing", year ? { year } : undefined),

  getInstitutions: (): Promise<
    Array<{ id: string; name: string; institution_type: string }>
  > => api.get("/analytics/institutions"),
};
