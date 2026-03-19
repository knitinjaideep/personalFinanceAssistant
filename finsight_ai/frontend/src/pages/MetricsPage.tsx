/**
 * MetricsPage — Phase 2.8 longitudinal financial metrics dashboard.
 *
 * Sections:
 * 1. Monthly overview (stat cards + per-account table) for selected month
 * 2. Net worth trend (area chart)
 * 3. Spending & cash flow trend (grouped bar chart)
 * 4. Recompute trigger (for maintenance)
 */

import React, { useEffect, useState, useCallback } from "react";
import { RefreshCw, Loader2, TrendingUp, BarChart3, Calendar } from "lucide-react";
import { clsx } from "clsx";
import toast from "react-hot-toast";

import { metricsApi } from "../api/metrics";
import { NetWorthChart } from "../components/metrics/NetWorthChart";
import { SpendingTrendChart } from "../components/metrics/SpendingTrendChart";
import { MetricsOverview } from "../components/metrics/MetricsOverview";
import type {
  AvailableMonth,
  MonthlySummary,
  NetWorthDataPoint,
  SpendingDataPoint,
} from "../types";

const MONTH_NAMES = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function SectionHeader({
  icon,
  title,
  subtitle,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle?: string;
}) {
  return (
    <div className="flex items-center gap-2 mb-4">
      <div className="p-1.5 bg-gray-100 rounded-lg">{icon}</div>
      <div>
        <h2 className="text-sm font-semibold text-gray-800">{title}</h2>
        {subtitle && <p className="text-xs text-gray-500">{subtitle}</p>}
      </div>
    </div>
  );
}

export function MetricsPage() {
  const [availableMonths, setAvailableMonths] = useState<AvailableMonth[]>([]);
  const [selectedMonthKey, setSelectedMonthKey] = useState<string | null>(null);

  const [netWorthData, setNetWorthData] = useState<NetWorthDataPoint[]>([]);
  const [spendingData, setSpendingData] = useState<SpendingDataPoint[]>([]);
  const [monthlySummary, setMonthlySummary] = useState<MonthlySummary | null>(null);

  const [, setLoadingMonths] = useState(false);
  const [loadingTrends, setLoadingTrends] = useState(false);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [recomputing, setRecomputing] = useState(false);

  // ── Load available months on mount ─────────────────────────────────────────

  const loadAvailableMonths = useCallback(async () => {
    setLoadingMonths(true);
    try {
      const months = await metricsApi.getAvailableMonths();
      setAvailableMonths(months);
      if (months.length > 0 && !selectedMonthKey) {
        setSelectedMonthKey(`${months[0].year}-${months[0].month}`);
      }
    } catch {
      // No months yet — normal for fresh install
    } finally {
      setLoadingMonths(false);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Load trend data ─────────────────────────────────────────────────────────

  const loadTrends = useCallback(async () => {
    setLoadingTrends(true);
    try {
      const [netWorth, spending] = await Promise.all([
        metricsApi.getNetWorthTrend({ months: 24 }),
        metricsApi.getSpendingTrend({ months: 12 }),
      ]);
      setNetWorthData(netWorth);
      setSpendingData(spending);
    } catch (err) {
      console.error("Failed to load trend data", err);
    } finally {
      setLoadingTrends(false);
    }
  }, []);

  // ── Load monthly summary when selection changes ────────────────────────────

  useEffect(() => {
    if (!selectedMonthKey) return;
    const [yearStr, monthStr] = selectedMonthKey.split("-");
    const year = parseInt(yearStr, 10);
    const month = parseInt(monthStr, 10);

    setLoadingSummary(true);
    metricsApi
      .getMonthlySummary(year, month)
      .then(setMonthlySummary)
      .catch(() => setMonthlySummary(null))
      .finally(() => setLoadingSummary(false));
  }, [selectedMonthKey]);

  // ── Initial load ────────────────────────────────────────────────────────────

  useEffect(() => {
    loadAvailableMonths();
    loadTrends();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Recompute ───────────────────────────────────────────────────────────────

  const handleRecompute = async () => {
    setRecomputing(true);
    try {
      const result = await metricsApi.recomputeAll();
      toast.success(`Recomputed ${result.total_rows_written} metric rows.`);
      await Promise.all([loadAvailableMonths(), loadTrends()]);
    } catch (err) {
      toast.error("Recompute failed. Check the backend logs.");
    } finally {
      setRecomputing(false);
    }
  };

  const hasData = netWorthData.length > 0 || spendingData.length > 0;

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-8">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Financial Metrics</h1>
          <p className="text-xs text-gray-500 mt-1">
            Longitudinal trends derived from your approved statements
          </p>
        </div>
        <button
          onClick={handleRecompute}
          disabled={recomputing}
          className={clsx(
            "flex items-center gap-2 px-3 py-2 text-xs rounded-lg border transition-colors",
            recomputing
              ? "border-gray-200 text-gray-400 cursor-not-allowed"
              : "border-gray-300 text-gray-600 hover:bg-gray-50"
          )}
        >
          {recomputing ? (
            <Loader2 size={13} className="animate-spin" />
          ) : (
            <RefreshCw size={13} />
          )}
          Recompute
        </button>
      </div>

      {/* Empty state */}
      {!hasData && !loadingTrends && (
        <div className="bg-white border border-gray-200 rounded-xl p-12 text-center">
          <TrendingUp size={36} className="text-gray-300 mx-auto mb-3" />
          <p className="text-sm font-medium text-gray-600">No metrics yet</p>
          <p className="text-xs text-gray-400 mt-1 max-w-xs mx-auto">
            Upload and process financial statements to start seeing your trends.
            Metrics are generated automatically after each successful ingestion.
          </p>
        </div>
      )}

      {/* Monthly snapshot */}
      {(availableMonths.length > 0 || monthlySummary) && (
        <section>
          <div className="flex items-center justify-between mb-4">
            <SectionHeader
              icon={<Calendar size={14} className="text-gray-600" />}
              title="Monthly Snapshot"
              subtitle="Cross-account summary for the selected month"
            />
            {availableMonths.length > 0 && (
              <select
                value={selectedMonthKey ?? ""}
                onChange={(e) => setSelectedMonthKey(e.target.value)}
                className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {availableMonths.map((m) => (
                  <option key={`${m.year}-${m.month}`} value={`${m.year}-${m.month}`}>
                    {MONTH_NAMES[m.month - 1]} {m.year}
                  </option>
                ))}
              </select>
            )}
          </div>

          {loadingSummary ? (
            <div className="flex items-center justify-center h-32">
              <Loader2 size={20} className="text-gray-400 animate-spin" />
            </div>
          ) : monthlySummary ? (
            <MetricsOverview summary={monthlySummary} />
          ) : null}
        </section>
      )}

      {/* Net worth trend */}
      <section>
        <SectionHeader
          icon={<TrendingUp size={14} className="text-blue-500" />}
          title="Net Worth Trend"
          subtitle="Total portfolio value across all accounts (last 24 months)"
        />
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          {loadingTrends ? (
            <div className="flex items-center justify-center h-48">
              <Loader2 size={20} className="text-gray-400 animate-spin" />
            </div>
          ) : (
            <NetWorthChart data={netWorthData} />
          )}
        </div>
      </section>

      {/* Spending trend */}
      <section>
        <SectionHeader
          icon={<BarChart3 size={14} className="text-gray-600" />}
          title="Cash Flow Trend"
          subtitle="Monthly deposits, withdrawals, fees, and dividends (last 12 months)"
        />
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          {loadingTrends ? (
            <div className="flex items-center justify-center h-48">
              <Loader2 size={20} className="text-gray-400 animate-spin" />
            </div>
          ) : (
            <SpendingTrendChart data={spendingData} />
          )}
        </div>
      </section>
    </div>
  );
}
