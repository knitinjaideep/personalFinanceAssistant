import { Calendar, MessageSquare, FileText, TrendingUp, TrendingDown } from "lucide-react";
import { DetailDrawer } from "../dashboard/DetailDrawer";
import { SectionCard } from "../dashboard/SectionCard";
import { DashboardEmptyState } from "../dashboard/DashboardEmptyState";
import type { BankingAccountRow } from "../../lib/bankingDashboard";
import { formatCurrency, formatDate } from "../../lib/dashboardData";

interface Props {
  row: BankingAccountRow | null;
  open: boolean;
  onClose: () => void;
  onAskCoral?: () => void;
  onViewDocuments?: () => void;
}

export function BankingAccountDetailDrawer({ row, open, onClose, onAskCoral, onViewDocuments }: Props) {
  if (!row) return null;

  const { config, cardSummary, cashFlow, latestStatement, latestSpend, status } = row;
  const isCreditCard = config.bucket === "credit_card";
  const isChecking = config.bucket === "checking";
  const isSavings = config.bucket === "savings";

  const sortedCF = [...cashFlow].sort((a, b) => b.month.localeCompare(a.month));
  const latestCF = sortedCF[0];

  return (
    <DetailDrawer
      open={open}
      onClose={onClose}
      title={config.displayName}
      subtitle={config.institution}
    >
      {/* Status banner */}
      {status !== "ok" && (
        <div
          className="rounded-xl px-4 py-3"
          style={{
            background: status === "warn" ? "rgba(255,209,102,0.08)" : "rgba(228,87,87,0.08)",
            border: `1px solid ${status === "warn" ? "rgba(255,209,102,0.25)" : "rgba(228,87,87,0.25)"}`,
          }}
        >
          <p className="text-[12px]" style={{ color: status === "warn" ? "#FFD166" : "#E45757" }}>
            {status === "warn"
              ? "Statement found but may be stale."
              : "No data found. Upload or reprocess statements for this account."}
          </p>
        </div>
      )}

      {/* Statement info */}
      <SectionCard title="Statement Info">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[12px]" style={{ color: "var(--text-muted)" }}>Latest statement</span>
            <span className="text-[12px] font-semibold" style={{ color: "var(--text-secondary)" }}>
              {latestStatement ? formatDate(latestStatement) : "Not available"}
            </span>
          </div>
          {isCreditCard && (
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-[12px]" style={{ color: "var(--text-muted)" }}>
                <Calendar size={11} />
                Payment due
              </div>
              <span className="text-[12px] font-semibold" style={{ color: "var(--text-secondary)" }}>
                {cardSummary?.latest_statement ?? "Not extracted"}
              </span>
            </div>
          )}
          {isCreditCard && (
            <div className="flex items-center justify-between">
              <span className="text-[12px]" style={{ color: "var(--text-muted)" }}>Total spend</span>
              <span className="text-[12px] font-bold" style={{ color: "var(--text-primary)" }}>
                {latestSpend > 0 ? formatCurrency(latestSpend) : "Not extracted"}
              </span>
            </div>
          )}
          {isCreditCard && cardSummary && (
            <div className="flex items-center justify-between">
              <span className="text-[12px]" style={{ color: "var(--text-muted)" }}>Transactions</span>
              <span className="text-[12px] font-semibold" style={{ color: "var(--text-secondary)" }}>
                {cardSummary.transaction_count ?? "—"}
              </span>
            </div>
          )}
        </div>
      </SectionCard>

      {/* Cash flow (checking/savings) */}
      {(isChecking || isSavings) && (
        <SectionCard title="Latest Cash Flow" subtitle="Most recent available month">
          {latestCF ? (
            <div className="grid grid-cols-3 gap-3">
              {[
                { label: "In", value: latestCF.inflow, color: "#4CAF93", Icon: TrendingUp },
                { label: "Out", value: latestCF.outflow, color: "#E45757", Icon: TrendingDown },
                { label: "Net", value: latestCF.net, color: latestCF.net >= 0 ? "#4CAF93" : "#E45757", Icon: TrendingUp },
              ].map(({ label, value, color, Icon }) => (
                <div key={label} className="text-center">
                  <Icon size={14} color={color} className="mx-auto mb-1" />
                  <p className="text-[15px] font-bold" style={{ color }}>
                    {formatCurrency(Math.abs(value))}
                  </p>
                  <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>{label}</p>
                </div>
              ))}
            </div>
          ) : (
            <DashboardEmptyState
              compact
              title="No cash flow data"
              description="Upload checking statements to see cash flow."
            />
          )}
        </SectionCard>
      )}

      {/* Data health */}
      <SectionCard title="Data Health">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[12px]" style={{ color: "var(--text-muted)" }}>Statement found</span>
            <span className="text-[12px] font-semibold" style={{ color: cardSummary ? "#4CAF93" : "#E45757" }}>
              {cardSummary ? "Yes" : "No"}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[12px]" style={{ color: "var(--text-muted)" }}>Transactions extracted</span>
            <span className="text-[12px] font-semibold" style={{ color: (cardSummary?.transaction_count ?? 0) > 0 ? "#4CAF93" : "#E45757" }}>
              {(cardSummary?.transaction_count ?? 0) > 0 ? `${cardSummary?.transaction_count} found` : "Not extracted"}
            </span>
          </div>
        </div>
      </SectionCard>

      {/* Actions */}
      <div className="flex flex-col gap-2 pt-1">
        {onAskCoral && (
          <button
            type="button"
            onClick={onAskCoral}
            className="flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-[13px] font-semibold w-full transition-all hover:-translate-y-0.5"
            style={{
              background: "rgba(34,211,238,0.12)",
              border: "1px solid rgba(34,211,238,0.30)",
              color: "#22d3ee",
            }}
          >
            <MessageSquare size={14} />
            Ask Coral about {config.displayName}
          </button>
        )}
        {onViewDocuments && (
          <button
            type="button"
            onClick={onViewDocuments}
            className="flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-[13px] font-medium w-full transition-all hover:-translate-y-0.5"
            style={{
              background: "rgba(220,242,250,0.05)",
              border: "1px solid var(--panel-border)",
              color: "var(--text-muted)",
            }}
          >
            <FileText size={14} />
            View Documents
          </button>
        )}
      </div>
    </DetailDrawer>
  );
}
