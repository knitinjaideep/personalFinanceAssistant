import { TrendingUp, AlertCircle, RefreshCw } from "lucide-react";
import type { InvestmentTotals } from "../../lib/financeDataAdapters";
import { fmtUSD, fmtDate } from "../../lib/financeDataAdapters";
import { useAppStore } from "../../store/appStore";

interface Props {
  totals: InvestmentTotals;
  loading?: boolean;
}

function Skeleton() {
  return (
    <div className="rounded-2xl p-5 animate-pulse" style={{ background: "var(--panel-bg-alt)", border: "1px solid var(--panel-border)" }}>
      <div className="w-24 h-2.5 rounded mb-4" style={{ background: "var(--empty-bg)" }} />
      <div className="w-32 h-7 rounded mb-3" style={{ background: "var(--empty-bg)" }} />
      <div className="space-y-2">
        <div className="w-full h-2 rounded" style={{ background: "var(--row-bg)" }} />
        <div className="w-3/4 h-2 rounded" style={{ background: "var(--row-bg)" }} />
      </div>
    </div>
  );
}

export function InvestmentSummaryWidget({ totals, loading }: Props) {
  const setActivePage = useAppStore((s) => s.setActivePage);

  if (loading) return <Skeleton />;

  const hasData = totals.combined > 0;

  return (
    <div
      className="rounded-2xl p-5"
      style={{
        background: "var(--panel-bg-alt)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        border: "1px solid var(--panel-border-accent)",
        boxShadow: "var(--panel-shadow)",
      }}
    >
      <div className="flex items-start justify-between mb-3">
        <span className="coral-label" style={{ color: "var(--text-muted)" }}>
          Total Invested
        </span>
        <div className="p-2 rounded-xl" style={{ background: "rgba(34,211,238,0.10)", color: "#22d3ee" }}>
          <TrendingUp size={14} />
        </div>
      </div>

      {!hasData ? (
        <div className="flex flex-col items-center gap-2 py-3 text-center">
          <AlertCircle size={16} style={{ color: "var(--empty-icon)" }} />
          <p className="coral-muted" style={{ color: "var(--text-muted)" }}>Not available</p>
          <button
            type="button"
            onClick={() => setActivePage("documents")}
            className="flex items-center gap-1 coral-badge-text font-semibold"
            style={{ color: "#22d3ee" }}
          >
            <RefreshCw size={10} />
            Reprocess statements
          </button>
        </div>
      ) : (
        <>
          <p className="metric-value" style={{ color: "var(--text-primary)" }}>
            {fmtUSD(totals.combined)}
          </p>
          {totals.asOf && (
            <p className="coral-badge-text mt-1" style={{ color: "var(--text-dim)" }}>As of {fmtDate(totals.asOf)}</p>
          )}

          <div className="mt-3 space-y-1.5">
            {totals.institutions.map((inst) => (
              <div key={inst.institutionKey} className="flex items-center justify-between coral-table-text">
                <span className="font-medium" style={{ color: "var(--text-secondary)" }}>{inst.displayName}</span>
                <span className="font-bold tabular" style={{ color: "var(--text-primary)" }}>
                  {fmtUSD(inst.totalValue)}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
