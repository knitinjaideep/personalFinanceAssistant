import { motion } from "framer-motion";
import { ChevronRight, CheckCircle, AlertCircle, XCircle, Shield } from "lucide-react";
import type { InvestmentAccountCard } from "../../lib/investmentsDashboard";
import { formatCurrency, formatDate } from "../../lib/dashboardData";

interface Props {
  card: InvestmentAccountCard;
  onClick?: () => void;
}

const INSTITUTION_ACCENTS: Record<string, string> = {
  morgan_stanley: "#1F6F8B",
  etrade: "#00A651",
};

function StatusBadge({ status }: { status: "fresh" | "stale" | "missing" }) {
  if (status === "fresh") return <CheckCircle size={12} color="#4CAF93" />;
  if (status === "stale") return <AlertCircle size={12} color="#FFD166" />;
  return <XCircle size={12} color="#E45757" />;
}

function getAccent(institutionType: string): string {
  const key = institutionType.toLowerCase().replace(/[\s*-]/g, "");
  if (key.includes("morgan")) return INSTITUTION_ACCENTS.morgan_stanley;
  if (key.includes("etrade") || key.includes("trade")) return INSTITUTION_ACCENTS.etrade;
  return "#22d3ee";
}

export function InvestmentAccountCardItem({ card, onClick }: Props) {
  const accent = getAccent(card.institutionType);
  const glPos = card.unrealizedGainLoss >= 0;

  return (
    <motion.div
      whileHover={onClick ? { y: -3, scale: 1.01 } : undefined}
      transition={{ duration: 0.2, ease: "easeOut" }}
      onClick={onClick}
      className={`rounded-[22px] p-5 ${onClick ? "cursor-pointer" : ""}`}
      style={{
        background: "var(--panel-bg)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        border: `1px solid ${accent}25`,
        boxShadow: "var(--panel-shadow)",
        transition: "box-shadow 0.25s ease, border-color 0.25s ease",
      }}
    >
      {/* Header row */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <div
            className="shrink-0 w-8 h-8 rounded-xl flex items-center justify-center"
            style={{ background: `${accent}18` }}
          >
            {card.isIRA ? (
              <Shield size={15} color={accent} />
            ) : (
              <span className="text-[11px] font-extrabold" style={{ color: accent }}>
                {card.institutionType.slice(0, 2).toUpperCase()}
              </span>
            )}
          </div>
          <div className="min-w-0">
            <p className="text-[13px] font-bold truncate" style={{ color: "var(--text-primary)" }}>
              {card.accountName}
            </p>
            <p className="text-[10px] capitalize" style={{ color: "var(--text-muted)" }}>
              {card.accountType}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5 shrink-0 ml-2">
          <StatusBadge status={card.status} />
          {onClick && <ChevronRight size={13} style={{ color: "var(--text-dim)" }} />}
        </div>
      </div>

      {/* Value */}
      <p className="text-[22px] font-extrabold leading-none mb-1" style={{ color: "var(--text-primary)" }}>
        {card.totalValue > 0 ? formatCurrency(card.totalValue) : "—"}
      </p>

      {/* G/L and date */}
      <div className="flex items-center justify-between mt-2">
        {card.unrealizedGainLoss !== 0 ? (
          <span
            className="text-[11px] font-semibold"
            style={{ color: glPos ? "#4CAF93" : "#E45757" }}
          >
            {glPos ? "+" : ""}{formatCurrency(card.unrealizedGainLoss)} G/L
            {card.gainLossPct !== null && (
              <span className="ml-1 opacity-70">
                ({card.gainLossPct > 0 ? "+" : ""}{card.gainLossPct}%)
              </span>
            )}
          </span>
        ) : (
          <span className="text-[11px]" style={{ color: "var(--text-dim)" }}>No G/L data</span>
        )}
        {card.latestStatementDate && (
          <span className="text-[10px]" style={{ color: "var(--text-dim)" }}>
            {formatDate(card.latestStatementDate)}
          </span>
        )}
      </div>
    </motion.div>
  );
}
