/**
 * MetricsOverview — summary stat cards for the most recent month.
 *
 * Shows:
 * - Total portfolio value
 * - Total fees this month
 * - Net cash flow
 * - Number of accounts tracked
 */

import React from "react";
import { TrendingUp, TrendingDown, DollarSign, Layers } from "lucide-react";
import { clsx } from "clsx";
import type { MonthlySummary } from "../../types";

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function formatCurrency(value: string | null | undefined): string {
  if (!value) return "—";
  const num = parseFloat(value);
  if (isNaN(num)) return value;
  if (Math.abs(num) >= 1_000_000)
    return `$${(num / 1_000_000).toFixed(2)}M`;
  if (Math.abs(num) >= 1_000)
    return `$${(num / 1_000).toFixed(1)}K`;
  return `$${num.toFixed(2)}`;
}

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
  color?: string;
}

function StatCard({ icon, label, value, sub, color = "text-gray-800" }: StatCardProps) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 flex items-start gap-3">
      <div className="p-2 bg-gray-50 rounded-lg">{icon}</div>
      <div>
        <p className="text-xs text-gray-500 font-medium">{label}</p>
        <p className={clsx("text-xl font-bold mt-0.5 tabular-nums", color)}>{value}</p>
        {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

interface MetricsOverviewProps {
  summary: MonthlySummary;
}

export function MetricsOverview({ summary }: MetricsOverviewProps) {
  const netCashFlow = summary.accounts.reduce((acc, a) => {
    return acc + parseFloat(a.net_cash_flow || "0");
  }, 0);
  const isPositiveCashFlow = netCashFlow >= 0;

  return (
    <div>
      <p className="text-xs text-gray-500 mb-3">
        {MONTH_NAMES[summary.month - 1]} {summary.year} · {summary.account_count} account{summary.account_count !== 1 ? "s" : ""}
      </p>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          icon={<DollarSign size={16} className="text-blue-500" />}
          label="Portfolio Value"
          value={formatCurrency(summary.total_value)}
          color="text-blue-700"
        />
        <StatCard
          icon={<TrendingDown size={16} className="text-red-500" />}
          label="Fees This Month"
          value={formatCurrency(summary.total_fees)}
          color="text-red-700"
        />
        <StatCard
          icon={
            isPositiveCashFlow
              ? <TrendingUp size={16} className="text-green-500" />
              : <TrendingDown size={16} className="text-amber-500" />
          }
          label="Net Cash Flow"
          value={formatCurrency(String(netCashFlow.toFixed(2)))}
          color={isPositiveCashFlow ? "text-green-700" : "text-amber-700"}
        />
        <StatCard
          icon={<Layers size={16} className="text-gray-500" />}
          label="Accounts"
          value={String(summary.account_count)}
          sub="tracked this month"
        />
      </div>

      {/* Per-account table */}
      {summary.accounts.length > 0 && (
        <div className="mt-4 bg-white border border-gray-200 rounded-xl overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100">
                <th className="px-4 py-2 text-left font-medium text-gray-600">Account</th>
                <th className="px-4 py-2 text-right font-medium text-gray-600">Value</th>
                <th className="px-4 py-2 text-right font-medium text-gray-600">Deposits</th>
                <th className="px-4 py-2 text-right font-medium text-gray-600">Withdrawals</th>
                <th className="px-4 py-2 text-right font-medium text-gray-600">Fees</th>
                <th className="px-4 py-2 text-right font-medium text-gray-600">Net Flow</th>
              </tr>
            </thead>
            <tbody>
              {summary.accounts.map((a, i) => (
                <tr
                  key={a.account_id}
                  className={clsx(
                    "border-t border-gray-50",
                    i % 2 === 0 ? "bg-white" : "bg-gray-50/40"
                  )}
                >
                  <td className="px-4 py-2.5">
                    <p className="font-medium text-gray-800 capitalize">
                      {a.institution_type?.replace("_", " ")}
                    </p>
                    <p className="text-gray-400">{a.account_label}</p>
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-gray-700">
                    {formatCurrency(a.total_value)}
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-green-700">
                    {formatCurrency(a.total_deposits)}
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-amber-700">
                    {formatCurrency(a.total_withdrawals)}
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-red-700">
                    {formatCurrency(a.total_fees)}
                  </td>
                  <td className={clsx(
                    "px-4 py-2.5 text-right font-mono",
                    parseFloat(a.net_cash_flow || "0") >= 0 ? "text-green-700" : "text-amber-700"
                  )}>
                    {formatCurrency(a.net_cash_flow)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
