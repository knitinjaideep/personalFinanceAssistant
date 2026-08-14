"use client";

/**
 * Section 3 (pr-06-overview.md): Income vs Spent vs Saved/Invested grouped
 * bar chart. Receives already-normalized, backend-computed numbers
 * (`MonthlyFlowSummary`, backend/app/domain/overview_insights.py) — this
 * component only parses decimal strings to `number` for the chart library
 * and formats labels; it never sums or derives a financial figure itself
 * (.claude/rules/frontend.md: "Do not perform hidden financial
 * reconciliation inside visualization components").
 *
 * Single-month vs multi-month: the backend already returns one row per
 * calendar month (Period.split_by_calendar_month) — a single-month period
 * selection naturally yields a single-element array, which recharts renders
 * as one grouped-bar cluster; a multi-month selection yields multiple
 * clusters. No branching is needed here for that distinction.
 */

import { useMemo } from "react";
import {
  Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { BarChart3 } from "lucide-react";
import EmptyState from "@/components/coral-ds/EmptyState";
import ErrorState from "@/components/coral-ds/ErrorState";
import SkeletonState from "@/components/coral-ds/SkeletonState";
import { formatCurrency } from "@/lib/utils";
import type { MonthlyFlowSummary } from "@/features/overview/api";

interface IncomeSpentSavedChartProps {
  rows: MonthlyFlowSummary[] | null;
  loading: boolean;
  error: boolean;
  onRetry?: () => void;
}

function monthLabel(periodLabel: string, multi: boolean): string {
  const [y, m] = periodLabel.split("-").map(Number);
  if (!y || !m) return periodLabel;
  const asDate = new Date(y, m - 1, 1);
  return multi
    ? asDate.toLocaleDateString("en-US", { month: "short" })
    : asDate.toLocaleDateString("en-US", { month: "long", year: "numeric" });
}

export default function IncomeSpentSavedChart({ rows, loading, error, onRetry }: IncomeSpentSavedChartProps) {
  const multi = (rows?.length ?? 0) > 1;

  const chartData = useMemo(() => {
    if (!rows) return [];
    return rows.map((r) => ({
      name: monthLabel(r.period_label, multi),
      Income: Number(r.income),
      Spent: Number(r.spent),
      "Saved / Invested": Number(r.saved_invested),
      incomeObserved: r.income_observed,
    }));
  }, [rows, multi]);

  if (loading) {
    return <SkeletonState variant="card" height="300px" />;
  }
  if (error) {
    return (
      <ErrorState
        compact
        message="Couldn't load income and spending data for this period."
        onRetry={onRetry}
      />
    );
  }

  const hasAnyActivity = chartData.some(
    (d) => d.incomeObserved || d.Spent > 0 || d["Saved / Invested"] > 0,
  );
  if (!rows || rows.length === 0 || !hasAnyActivity) {
    return (
      <EmptyState
        compact
        icon={<BarChart3 size={22} />}
        title="No activity for this period"
        description="Coral hasn't found any income, spending, or saving in the selected period yet."
      />
    );
  }

  const axisColor = "var(--text-muted)";
  const summarySentence = chartData
    .map(
      (d) =>
        `${d.name}: income ${formatCurrency(d.Income)}, spent ${formatCurrency(d.Spent)}, ` +
        `saved and invested ${formatCurrency(d["Saved / Invested"])}.`,
    )
    .join(" ");

  return (
    <div>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={chartData} margin={{ left: 4, right: 8, top: 8, bottom: 4 }} barGap={4}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
          <XAxis
            dataKey="name"
            tick={{ fontSize: 12, fill: axisColor }}
            axisLine={{ stroke: "var(--border-subtle)" }}
            tickLine={false}
          />
          <YAxis
            tickFormatter={(v: number) => formatCurrency(v)}
            tick={{ fontSize: 11, fill: axisColor }}
            axisLine={false}
            tickLine={false}
            width={68}
          />
          <Tooltip
            formatter={(v) => formatCurrency(Number(v))}
            contentStyle={{
              background: "var(--card-bg)",
              border: "1px solid var(--border-subtle)",
              borderRadius: 12,
              fontSize: 12,
            }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="Income" fill="var(--financial-needs)" radius={[6, 6, 0, 0]} />
          <Bar dataKey="Spent" fill="var(--financial-wants)" radius={[6, 6, 0, 0]} />
          <Bar dataKey="Saved / Invested" fill="var(--financial-savings)" radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
      {/* Accessible textual summary — .claude/rules/frontend.md: charts need
       * "accessible textual labels or summaries where practical". */}
      <span className="sr-only">{summarySentence}</span>
    </div>
  );
}
