import { BarChart2 } from "lucide-react";
import { SectionCard } from "../dashboard/SectionCard";
import { DashboardEmptyState } from "../dashboard/DashboardEmptyState";
import type { Holding } from "../../api/dashboard";
import { safeArray, formatCurrency } from "../../lib/dashboardData";

interface Props {
  holdings: Holding[];
  onDocuments?: () => void;
}

export function InvestmentHoldingsTab({ holdings, onDocuments }: Props) {
  const items = safeArray(holdings);

  if (items.length === 0) {
    return (
      <DashboardEmptyState
        icon={<BarChart2 size={22} />}
        title="Holdings not extracted"
        description="Holdings have not been extracted yet. Reprocess Morgan Stanley or E*TRADE statements."
        primaryAction={onDocuments ? { label: "View Documents", onClick: onDocuments } : undefined}
      />
    );
  }

  return (
    <SectionCard title="Holdings" subtitle={`${items.length} positions across all accounts`}>
      <div className="overflow-x-auto">
        <table className="w-full coral-table-text">
          <thead>
            <tr
              className="border-b"
              style={{ borderColor: "var(--row-border-strong)", color: "var(--table-head)" }}
            >
              <th className="text-left py-3 pr-3 font-semibold">Symbol / Name</th>
              <th className="text-left py-3 px-2 font-semibold hidden md:table-cell">Account</th>
              <th className="text-right py-3 px-2 font-semibold hidden sm:table-cell">Qty</th>
              <th className="text-right py-3 px-2 font-semibold">Value</th>
              <th className="text-right py-3 px-2 font-semibold hidden md:table-cell">G/L</th>
              <th className="text-right py-3 pl-2 font-semibold hidden sm:table-cell">Wt%</th>
            </tr>
          </thead>
          <tbody>
            {items.map((h, i) => {
              const glPos = (h.unrealized_gain_loss ?? 0) >= 0;
              return (
                <tr
                  key={i}
                  className="border-b last:border-0 transition-colors hover:bg-white/[0.02]"
                  style={{ borderColor: "var(--row-border)" }}
                >
                  <td className="py-3 pr-3">
                    <span className="font-semibold" style={{ color: "var(--text-primary)" }}>
                      {h.symbol ?? "—"}
                    </span>
                    {h.description && (
                      <span
                        className="block coral-badge-text truncate max-w-[140px]"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {h.description.slice(0, 24)}
                      </span>
                    )}
                  </td>
                  <td className="py-3 px-2 hidden md:table-cell">
                    <span className="coral-badge-text truncate max-w-[100px] block" style={{ color: "var(--text-muted)" }}>
                      {h.account_name ?? "—"}
                    </span>
                  </td>
                  <td className="py-2.5 px-2 text-right tabular hidden sm:table-cell" style={{ color: "var(--text-muted)" }}>
                    {h.quantity !== null ? h.quantity.toFixed(2) : "—"}
                  </td>
                  <td className="py-2.5 px-2 text-right font-semibold tabular" style={{ color: "var(--text-secondary)" }}>
                    {formatCurrency(h.market_value)}
                  </td>
                  <td
                    className={`py-2.5 px-2 text-right font-semibold tabular hidden md:table-cell`}
                    style={{ color: glPos ? "#4CAF93" : "#E45757" }}
                  >
                    {glPos ? "+" : ""}{formatCurrency(h.unrealized_gain_loss)}
                  </td>
                  <td className="py-2.5 pl-2 text-right tabular hidden sm:table-cell" style={{ color: "var(--text-muted)" }}>
                    {h.portfolio_weight !== null ? `${h.portfolio_weight}%` : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </SectionCard>
  );
}
