import { Receipt } from "lucide-react";
import { SectionCard } from "../dashboard/SectionCard";
import { DashboardEmptyState } from "../dashboard/DashboardEmptyState";
import type { BankingDashboard } from "../../api/dashboard";
import { safeArray, formatCurrency } from "../../lib/dashboardData";

interface Props {
  raw: BankingDashboard | null;
  onDocuments?: () => void;
}

export function BankingTransactionsTab({ raw, onDocuments }: Props) {
  const merchants = safeArray(raw?.top_merchants);
  const spendByCategory = safeArray(raw?.spend_by_category);

  if (!raw || (merchants.length === 0 && spendByCategory.length === 0)) {
    return (
      <DashboardEmptyState
        icon={<Receipt size={22} />}
        title="Transactions not extracted"
        description="Transactions have not been extracted from statements yet. Reprocess statements or check Needs Attention."
        primaryAction={onDocuments ? { label: "View Documents", onClick: onDocuments } : undefined}
      />
    );
  }

  return (
    <div className="space-y-4">
      {/* Top merchants */}
      {merchants.length > 0 && (
        <SectionCard title="Top Merchants" subtitle="Highest spending merchants this period">
          <div className="space-y-2">
            {merchants.map((m, i) => (
              <div key={i} className="flex items-center justify-between py-1.5">
                <div className="flex items-center gap-3 min-w-0">
                  <span
                    className="shrink-0 w-5 h-5 rounded-lg flex items-center justify-center text-[10px] font-bold"
                    style={{ background: "rgba(34,211,238,0.12)", color: "#22d3ee" }}
                  >
                    {i + 1}
                  </span>
                  <span className="text-[13px] font-medium truncate" style={{ color: "var(--text-primary)" }}>
                    {m.merchant}
                  </span>
                </div>
                <div className="text-right shrink-0 ml-3">
                  <p className="text-[13px] font-semibold tabular" style={{ color: "var(--text-secondary)" }}>
                    {formatCurrency(m.total)}
                  </p>
                  <p className="text-[10px]" style={{ color: "var(--text-dim)" }}>
                    {m.transaction_count} transactions
                  </p>
                </div>
              </div>
            ))}
          </div>
        </SectionCard>
      )}

      {/* Spend by category */}
      {spendByCategory.length > 0 && (
        <SectionCard title="Spend by Category">
          <div className="space-y-2.5">
            {spendByCategory.slice(0, 10).map((cat, i) => {
              const maxSpend = spendByCategory[0]?.total ?? 1;
              const pct = (cat.total / maxSpend) * 100;
              return (
                <div key={i}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[12px] font-medium" style={{ color: "var(--text-secondary)" }}>
                      {cat.category}
                    </span>
                    <span className="text-[12px] font-semibold tabular" style={{ color: "var(--text-primary)" }}>
                      {formatCurrency(cat.total)}
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "var(--insight-bg)" }}>
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${pct}%`, background: "#FF7A5A" }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </SectionCard>
      )}

      <p className="text-[11px] text-center" style={{ color: "var(--text-dim)" }}>
        Showing aggregate data. Individual transaction history requires statement re-extraction.
      </p>
    </div>
  );
}
