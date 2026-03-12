import { api } from "./client";
import type { FeeAnalyticsResponse, BalancePoint, MissingStatement } from "../types";

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

  getMissing: (year?: number): Promise<{ year: number; missing: MissingStatement[] }> =>
    api.get("/analytics/missing", year ? { year } : undefined),

  getInstitutions: (): Promise<
    Array<{ id: string; name: string; institution_type: string }>
  > => api.get("/analytics/institutions"),
};
