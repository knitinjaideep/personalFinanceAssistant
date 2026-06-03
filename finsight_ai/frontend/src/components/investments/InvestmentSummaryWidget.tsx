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
    <div className="rounded-2xl p-5 animate-pulse" style={{ background: "rgba(3,17,31,0.60)", border: "1px solid rgba(34,211,238,0.10)" }}>
      <div className="w-24 h-2.5 rounded mb-4" style={{ background: "rgba(34,211,238,0.10)" }} />
      <div className="w-32 h-7 rounded mb-3" style={{ background: "rgba(34,211,238,0.10)" }} />
      <div className="space-y-2">
        <div className="w-full h-2 rounded" style={{ background: "rgba(34,211,238,0.07)" }} />
        <div className="w-3/4 h-2 rounded" style={{ background: "rgba(34,211,238,0.07)" }} />
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
        background: "rgba(3,17,31,0.60)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        border: "1px solid rgba(34,211,238,0.12)",
        boxShadow: "0 8px 32px rgba(3,17,31,0.40)",
      }}
    >
      <div className="flex items-start justify-between mb-3">
        <span className="text-[10px] font-semibold uppercase tracking-widest" style={{ color: "rgba(255,255,255,0.35)" }}>
          Total Invested
        </span>
        <div className="p-2 rounded-xl" style={{ background: "rgba(34,211,238,0.10)", color: "#22d3ee" }}>
          <TrendingUp size={14} />
        </div>
      </div>

      {!hasData ? (
        <div className="flex flex-col items-center gap-2 py-3 text-center">
          <AlertCircle size={16} style={{ color: "rgba(255,255,255,0.18)" }} />
          <p className="text-[12px]" style={{ color: "rgba(255,255,255,0.38)" }}>Not available</p>
          <button
            type="button"
            onClick={() => setActivePage("documents")}
            className="flex items-center gap-1 text-[11px] font-semibold"
            style={{ color: "#22d3ee" }}
          >
            <RefreshCw size={10} />
            Reprocess statements
          </button>
        </div>
      ) : (
        <>
          <p className="text-[26px] font-bold tracking-tight tabular text-white">
            {fmtUSD(totals.combined)}
          </p>
          {totals.asOf && (
            <p className="text-[10px] mt-1" style={{ color: "rgba(255,255,255,0.30)" }}>As of {fmtDate(totals.asOf)}</p>
          )}

          <div className="mt-3 space-y-1.5">
            {totals.institutions.map((inst) => (
              <div key={inst.institutionKey} className="flex items-center justify-between text-[12px]">
                <span className="font-medium" style={{ color: "rgba(255,255,255,0.50)" }}>{inst.displayName}</span>
                <span className="font-bold tabular text-white/80">
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
