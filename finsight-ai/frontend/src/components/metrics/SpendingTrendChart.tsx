/**
 * SpendingTrendChart — grouped bar chart of monthly fees, deposits, and withdrawals.
 */

import React, { useMemo } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import type { SpendingDataPoint } from "../../types";

const MONTH_NAMES = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function formatCurrency(value: number): string {
  if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  return `$${value.toFixed(0)}`;
}

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { name: string; value: number; color: string }[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-lg p-3 text-xs min-w-[160px]">
      <p className="font-semibold text-gray-800 mb-2">{label}</p>
      {payload.map((p) => (
        <div key={p.name} className="flex justify-between gap-4">
          <span style={{ color: p.color }}>{p.name}</span>
          <span className="font-mono text-gray-700">{formatCurrency(p.value)}</span>
        </div>
      ))}
    </div>
  );
}

interface SpendingTrendChartProps {
  data: SpendingDataPoint[];
}

export function SpendingTrendChart({ data }: SpendingTrendChartProps) {
  const chartData = useMemo(
    () =>
      data.map((d) => ({
        label: `${MONTH_NAMES[d.month - 1]} '${String(d.year).slice(2)}`,
        Deposits: parseFloat(d.total_deposits || "0"),
        Withdrawals: parseFloat(d.total_withdrawals || "0"),
        Fees: parseFloat(d.total_fees || "0"),
        Dividends: parseFloat(d.total_dividends || "0"),
      })),
    [data]
  );

  if (!data.length) {
    return (
      <div className="flex items-center justify-center h-48 text-sm text-gray-400">
        No spending data yet. Upload statements to see your cash flow trend.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={chartData} margin={{ top: 4, right: 8, left: 8, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis
          dataKey="label"
          tick={{ fontSize: 11, fill: "#9ca3af" }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          tickFormatter={formatCurrency}
          tick={{ fontSize: 11, fill: "#9ca3af" }}
          axisLine={false}
          tickLine={false}
          width={60}
        />
        <Tooltip content={<CustomTooltip />} />
        <Legend
          wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
          iconSize={10}
          iconType="circle"
        />
        <Bar dataKey="Deposits" fill="#10b981" radius={[2, 2, 0, 0]} maxBarSize={32} />
        <Bar dataKey="Withdrawals" fill="#f59e0b" radius={[2, 2, 0, 0]} maxBarSize={32} />
        <Bar dataKey="Fees" fill="#ef4444" radius={[2, 2, 0, 0]} maxBarSize={32} />
        <Bar dataKey="Dividends" fill="#6366f1" radius={[2, 2, 0, 0]} maxBarSize={32} />
      </BarChart>
    </ResponsiveContainer>
  );
}
