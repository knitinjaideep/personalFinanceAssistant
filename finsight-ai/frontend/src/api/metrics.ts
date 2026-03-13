/**
 * Metrics API client — Phase 2.8 longitudinal derived metrics.
 */

import { api } from "./client";
import type {
  AvailableMonth,
  MonthlySummary,
  NetWorthDataPoint,
  SpendingDataPoint,
} from "../types";

export const metricsApi = {
  /** Monthly net worth time series. */
  getNetWorthTrend(params?: {
    account_id?: string;
    institution_id?: string;
    months?: number;
  }): Promise<NetWorthDataPoint[]> {
    return api.get<NetWorthDataPoint[]>(
      "/metrics/net-worth-trend",
      params as Record<string, string | number | undefined>
    );
  },

  /** Monthly spending and cash flow trend. */
  getSpendingTrend(params?: {
    account_id?: string;
    institution_id?: string;
    months?: number;
  }): Promise<SpendingDataPoint[]> {
    return api.get<SpendingDataPoint[]>(
      "/metrics/spending-trend",
      params as Record<string, string | number | undefined>
    );
  },

  /** Single-month cross-account snapshot. */
  getMonthlySummary(year: number, month: number): Promise<MonthlySummary> {
    return api.get<MonthlySummary>(`/metrics/summary/${year}/${month}`);
  },

  /** List months that have derived metric data. */
  getAvailableMonths(): Promise<AvailableMonth[]> {
    return api.get<AvailableMonth[]>("/metrics/available-months");
  },

  /** Trigger metric generation for a specific statement. */
  generateForStatement(statementId: string): Promise<{ months_written: number }> {
    return api.post<{ months_written: number }>(`/metrics/generate/${statementId}`, {});
  },

  /** Full recompute of all derived metrics. */
  recomputeAll(): Promise<{ total_rows_written: number }> {
    return api.post<{ total_rows_written: number }>("/metrics/recompute", {});
  },
};
