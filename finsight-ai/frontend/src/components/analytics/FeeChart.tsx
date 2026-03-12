import React, { useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";
import { analyticsApi } from "../../api/analytics";
import type { FeeAnalyticsResponse } from "../../types";
import { Loader2, DollarSign } from "lucide-react";

export function FeeChart() {
  const [data, setData] = useState<FeeAnalyticsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    analyticsApi
      .getFees()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setIsLoading(false));
  }, []);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-48">
        <Loader2 className="animate-spin text-gray-400" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-sm text-red-500 text-center py-8">{error}</div>
    );
  }

  if (!data || data.summaries.length === 0) {
    return (
      <div className="text-sm text-gray-400 text-center py-8">
        No fee data yet. Upload statements to see fee analysis.
      </div>
    );
  }

  const chartData = data.summaries.map((s) => ({
    name: `${s.institution.replace("Morgan Stanley", "MS")} ${s.account}`,
    fees: parseFloat(s.total_fees),
    count: s.fee_count,
  }));

  return (
    <div className="space-y-4">
      {/* Total callout */}
      <div className="flex items-center gap-2 p-3 bg-orange-50 rounded-lg border border-orange-100">
        <DollarSign size={18} className="text-orange-500" />
        <div>
          <div className="text-xs text-orange-600">Total fees (last 6 months)</div>
          <div className="text-lg font-bold text-orange-700">
            ${parseFloat(data.total_fees).toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </div>
        </div>
      </div>

      {/* Bar chart */}
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={chartData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="name" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `$${v}`} />
          <Tooltip
            formatter={(value: number) =>
              [`$${value.toLocaleString("en-US", { minimumFractionDigits: 2 })}`, "Fees"]
            }
          />
          <Bar dataKey="fees" fill="#3b82f6" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b text-left text-gray-500">
              <th className="pb-2 pr-4">Institution</th>
              <th className="pb-2 pr-4">Account</th>
              <th className="pb-2 pr-4 text-right">Total Fees</th>
              <th className="pb-2 text-right"># Fees</th>
            </tr>
          </thead>
          <tbody>
            {data.summaries.map((s, i) => (
              <tr key={i} className="border-b border-gray-50">
                <td className="py-1.5 pr-4 text-gray-700">{s.institution}</td>
                <td className="py-1.5 pr-4 text-gray-500">{s.account}</td>
                <td className="py-1.5 pr-4 text-right font-medium">
                  ${parseFloat(s.total_fees).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                </td>
                <td className="py-1.5 text-right text-gray-500">{s.fee_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
