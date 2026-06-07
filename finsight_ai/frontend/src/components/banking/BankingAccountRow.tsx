import { motion } from "framer-motion";
import { ChevronRight, CheckCircle, AlertCircle, XCircle } from "lucide-react";
import type { BankingAccountRow } from "../../lib/bankingDashboard";
import { formatCurrency } from "../../lib/dashboardData";

interface Props {
  row: BankingAccountRow;
  showSpend?: boolean;
  showCashFlow?: boolean;
  onClick?: () => void;
}

const INSTITUTION_ACCENTS: Record<string, string> = {
  chase: "#1F6F8B",
  amex: "#0B3C5D",
  macys: "#FF7A5A",
  bank_of_america: "#D4163C",
  marcus: "#4CAF93",
  goldman_sachs: "#4CAF93",
};

function StatusBadge({ status, label }: { status: BankingAccountRow["status"]; label: string }) {
  if (status === "ok") {
    return (
      <div className="flex items-center gap-1 coral-badge-text" style={{ color: "#4CAF93" }}>
        <CheckCircle size={11} />
        <span className="hidden sm:inline">{label}</span>
      </div>
    );
  }
  if (status === "warn") {
    return (
      <div className="flex items-center gap-1 coral-badge-text" style={{ color: "#FFD166" }}>
        <AlertCircle size={11} />
        <span className="hidden sm:inline">{label}</span>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-1 coral-badge-text" style={{ color: "#E45757" }}>
      <XCircle size={11} />
      <span className="hidden sm:inline">No data</span>
    </div>
  );
}

export function BankingAccountRowItem({ row, showSpend = true, showCashFlow = false, onClick }: Props) {
  const accent = INSTITUTION_ACCENTS[row.config.institutionKey] ?? "#5FA8D3";

  return (
    <motion.div
      whileHover={onClick ? { y: -1, scale: 1.005 } : undefined}
      transition={{ duration: 0.18, ease: "easeOut" }}
      onClick={onClick}
      className={`flex items-center gap-3 px-4 py-3 rounded-2xl transition-colors ${onClick ? "cursor-pointer" : ""}`}
      style={{
        background: "var(--row-bg)",
        border: "1px solid var(--row-border)",
      }}
    >
      {/* Institution badge */}
      <div
        className="shrink-0 w-8 h-8 rounded-lg flex items-center justify-center text-xs font-extrabold text-white uppercase tracking-wide"
        style={{ background: accent }}
      >
        {row.config.institution.slice(0, 2).toUpperCase()}
      </div>

      {/* Name + institution */}
      <div className="flex-1 min-w-0">
        <p className="coral-table-text font-semibold truncate" style={{ color: "var(--text-primary)" }}>
          {row.config.displayName}
        </p>
        <p className="coral-badge-text truncate mt-0.5" style={{ color: "var(--text-muted)" }}>
          {row.config.institution}
          {row.latestStatement && ` · ${row.latestStatement}`}
        </p>
      </div>

      {/* Spend */}
      {showSpend && (
        <div className="hidden sm:block text-right shrink-0">
          <p className="coral-table-text font-semibold tabular" style={{ color: "var(--text-secondary)" }}>
            {row.latestSpend > 0 ? formatCurrency(row.latestSpend) : "—"}
          </p>
          <p className="coral-badge-text mt-0.5" style={{ color: "var(--text-dim)" }}>latest spend</p>
        </div>
      )}

      {/* Cash flow */}
      {showCashFlow && row.cashFlow.length > 0 && (() => {
        const sorted = [...row.cashFlow].sort((a, b) => b.month.localeCompare(a.month));
        const latest = sorted[0];
        const net = latest?.net ?? 0;
        return (
          <div className="hidden sm:block text-right shrink-0">
            <p
              className="coral-table-text font-semibold tabular"
              style={{ color: net >= 0 ? "#4CAF93" : "#E45757" }}
            >
              {net >= 0 ? "+" : ""}{formatCurrency(net)}
            </p>
            <p className="coral-badge-text mt-0.5" style={{ color: "var(--text-dim)" }}>net flow</p>
          </div>
        );
      })()}

      {/* Status */}
      <StatusBadge status={row.status} label={row.statusLabel} />

      {/* Arrow */}
      {onClick && <ChevronRight size={14} style={{ color: "var(--text-dim)", flexShrink: 0 }} />}
    </motion.div>
  );
}
