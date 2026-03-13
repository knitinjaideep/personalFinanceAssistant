/**
 * NetWorthChart — area chart of total portfolio value over time.
 *
 * Uses Recharts AreaChart with a responsive container.
 * Each data point can be expanded to show per-account breakdown via tooltip.
 */

import React, { useMemo } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { NetWorthDataPoint } from "../../types";

interface NetWorthChartProps {
  data: NetWorthDataPoint[];
}

const MONTH_NAMES = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function formatCurrency(value: number): string {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  return `$${value.toFixed(0)}`;
}

interface TooltipPayload {
  payload: {
    month_start: string;
    year: number;
    month: number;
    total_value_num: number;
    accounts: NetWorthDataPoint["accounts"];
  };
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: TooltipPayload[] }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-lg p-3 text-xs min-w-[180px]">
      <p className="font-semibold text-gray-800 mb-2">
        {MONTH_NAMES[d.month - 1]} {d.year}
      </p>
      <p className="text-base font-bold text-blue-600 mb-2">
        {formatCurrency(d.total_value_num)}
      </p>
      {d.accounts.length > 0 && (
        <div className="space-y-1 border-t border-gray-100 pt-1">
          {d.accounts.map((a, i) => (
            <div key={i} className="flex justify-between gap-4 text-gray-600">
              <span className="truncate" title={a.account_label}>
                {a.institution_type?.replace("_", " ")} {a.account_label}
              </span>
              <span className="shrink-0">
                {formatCurrency(parseFloat(a.total_value || "0"))}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function NetWorthChart({ data }: NetWorthChartProps) {
  const chartData = useMemo(
    () =>
      data.map((d) => ({
        ...d,
        label: `${MONTH_NAMES[d.month - 1]} '${String(d.year).slice(2)}`,
        total_value_num: parseFloat(d.total_value || "0"),
      })),
    [data]
  );

  if (!data.length) {
    return (
      <div className="flex items-center justify-center h-48 text-sm text-gray-400">
        No net worth data yet. Upload statements to see your trend.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={240}>
      <AreaChart data={chartData} margin={{ top: 4, right: 8, left: 8, bottom: 0 }}>
        <defs>
          <linearGradient id="netWorthGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.15} />
            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
          </linearGradient>
        </defs>
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
        <Area
          type="monotone"
          dataKey="total_value_num"
          stroke="#3b82f6"
          strokeWidth={2}
          fill="url(#netWorthGrad)"
          dot={false}
          activeDot={{ r: 4, strokeWidth: 0, fill: "#3b82f6" }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
