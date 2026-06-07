import { TrendingUp, TrendingDown, MessageSquare, FileText } from "lucide-react";
import { DetailDrawer } from "../dashboard/DetailDrawer";
import { SectionCard } from "../dashboard/SectionCard";
import { DashboardEmptyState } from "../dashboard/DashboardEmptyState";
import type { InvestmentAccountCard } from "../../lib/investmentsDashboard";
import type { Holding } from "../../api/dashboard";
import { formatCurrency, formatDate } from "../../lib/dashboardData";
import { safeArray } from "../../lib/dashboardData";

interface Props {
  card: InvestmentAccountCard | null;
  holdings: Holding[];
  open: boolean;
  onClose: () => void;
  onAskCoral?: () => void;
  onViewDocuments?: () => void;
}

export function InvestmentAccountDetailDrawer({ card, holdings, open, onClose, onAskCoral, onViewDocuments }: Props) {
  if (!card) return null;

  const accountHoldings = safeArray(holdings).filter(
    (h) => (h.account_name ?? "").toLowerCase().includes(card.accountName.toLowerCase().slice(0, 8)),
  );

  return (
    <DetailDrawer
      open={open}
      onClose={onClose}
      title={card.accountName}
      subtitle={`${card.institutionType} · ${card.accountType}`}
    >
      {/* Value summary */}
      <SectionCard title="Account Value">
        <div className="space-y-2.5">
          <div className="flex items-center justify-between">
            <span className="text-[12px]" style={{ color: "var(--text-muted)" }}>Total value</span>
            <span className="text-[15px] font-bold" style={{ color: "var(--text-primary)" }}>
              {card.totalValue > 0 ? formatCurrency(card.totalValue) : "Not extracted"}
            </span>
          </div>
          {card.unrealizedGainLoss !== 0 && (
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-[12px]" style={{ color: "var(--text-muted)" }}>
                {card.unrealizedGainLoss >= 0 ? (
                  <TrendingUp size={11} color="#4CAF93" />
                ) : (
                  <TrendingDown size={11} color="#E45757" />
                )}
                Unrealized G/L
              </div>
              <span
                className="text-[12px] font-semibold tabular"
                style={{ color: card.unrealizedGainLoss >= 0 ? "#4CAF93" : "#E45757" }}
              >
                {card.unrealizedGainLoss >= 0 ? "+" : ""}
                {formatCurrency(card.unrealizedGainLoss)}
                {card.gainLossPct !== null && ` (${card.gainLossPct > 0 ? "+" : ""}${card.gainLossPct}%)`}
              </span>
            </div>
          )}
          <div className="flex items-center justify-between">
            <span className="text-[12px]" style={{ color: "var(--text-muted)" }}>Latest statement</span>
            <span className="text-[12px] font-semibold" style={{ color: "var(--text-secondary)" }}>
              {formatDate(card.latestStatementDate)}
            </span>
          </div>
        </div>
      </SectionCard>

      {/* Holdings */}
      <SectionCard title="Holdings" subtitle={`${accountHoldings.length} positions`}>
        {accountHoldings.length === 0 ? (
          <DashboardEmptyState
            compact
            title="No holdings data"
            description="Reprocess statements to extract holdings for this account."
          />
        ) : (
          <div className="space-y-2">
            {accountHoldings.slice(0, 8).map((h, i) => {
              const glPos = (h.unrealized_gain_loss ?? 0) >= 0;
              return (
                <div key={i} className="flex items-center justify-between">
                  <div className="min-w-0">
                    <p className="text-[12px] font-semibold" style={{ color: "var(--text-primary)" }}>
                      {h.symbol ?? h.description?.slice(0, 20) ?? "—"}
                    </p>
                    {h.symbol && h.description && (
                      <p className="text-[10px] truncate max-w-[160px]" style={{ color: "var(--text-muted)" }}>
                        {h.description.slice(0, 24)}
                      </p>
                    )}
                  </div>
                  <div className="text-right shrink-0 ml-2">
                    <p className="text-[12px] font-semibold" style={{ color: "var(--text-secondary)" }}>
                      {formatCurrency(h.market_value)}
                    </p>
                    {h.unrealized_gain_loss !== 0 && (
                      <p className="text-[10px]" style={{ color: glPos ? "#4CAF93" : "#E45757" }}>
                        {glPos ? "+" : ""}{formatCurrency(h.unrealized_gain_loss)}
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </SectionCard>

      {/* Data health */}
      <SectionCard title="Data Health">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[12px]" style={{ color: "var(--text-muted)" }}>Statement found</span>
            <span className="text-[12px] font-semibold" style={{ color: card.latestStatementDate ? "#4CAF93" : "#E45757" }}>
              {card.latestStatementDate ? "Yes" : "No"}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[12px]" style={{ color: "var(--text-muted)" }}>Holdings extracted</span>
            <span className="text-[12px] font-semibold" style={{ color: accountHoldings.length > 0 ? "#4CAF93" : "#E45757" }}>
              {accountHoldings.length > 0 ? `${accountHoldings.length} positions` : "Not extracted"}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[12px]" style={{ color: "var(--text-muted)" }}>Freshness</span>
            <span
              className="text-[12px] font-semibold capitalize"
              style={{
                color:
                  (card.status as string) === "fresh" ? "#4CAF93"
                  : (card.status as string) === "stale" ? "#FFD166"
                  : "#E45757",
              }}
            >
              {card.status}
            </span>
          </div>
        </div>
      </SectionCard>

      {/* Actions */}
      <div className="flex flex-col gap-2">
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
            Ask Coral about {card.accountName}
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
