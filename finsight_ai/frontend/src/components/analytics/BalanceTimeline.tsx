import React, { useEffect, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { analyticsApi } from "../../api/analytics";
import type { BalancePoint } from "../../types";
import { Loader2 } from "lucide-react";
import { format, parseISO } from "date-fns";

export function BalanceTimeline() {
  const [data, setData] = useState<BalancePoint[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    analyticsApi
      .getBalances({ limit: 24 })
      .then((d) => setData(d.reverse())) // chronological order
      .finally(() => setIsLoading(false));
  }, []);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-48">
        <Loader2 className="animate-spin text-gray-400" />
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="text-sm text-gray-400 text-center py-8">
        No balance history yet.
      </div>
    );
  }

  const chartData = data.map((b) => ({
    date: format(parseISO(b.date), "MMM yy"),
    balance: parseFloat(b.total_value),
    account: b.account,
  }));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={chartData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey="date" tick={{ fontSize: 11 }} />
        <YAxis
          tick={{ fontSize: 11 }}
          tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
        />
        <Tooltip
          formatter={(value: number) => [
            `$${value.toLocaleString("en-US", { minimumFractionDigits: 2 })}`,
            "Balance",
          ]}
        />
        <Line
          type="monotone"
          dataKey="balance"
          stroke="#10b981"
          strokeWidth={2}
          dot={{ r: 3 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
