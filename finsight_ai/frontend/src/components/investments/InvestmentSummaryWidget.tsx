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
    <div className="rounded-2xl p-5 animate-pulse" style={{ background: "rgba(255,255,255,0.88)", border: "1px solid rgba(205,237,246,0.65)" }}>
      <div className="w-24 h-2.5 rounded bg-ocean/10 mb-4" />
      <div className="w-32 h-7 rounded bg-ocean/10 mb-3" />
      <div className="space-y-2">
        <div className="w-full h-2 rounded bg-ocean/08" />
        <div className="w-3/4 h-2 rounded bg-ocean/08" />
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
        background: "rgba(255,255,255,0.88)",
        border: "1px solid rgba(205,237,246,0.65)",
        boxShadow: "0 4px 24px rgba(11,60,93,0.07), inset 0 1px 0 rgba(255,255,255,0.90)",
      }}
    >
      <div className="flex items-start justify-between mb-3">
        <span className="text-[10px] font-semibold text-ocean/38 uppercase tracking-widest">
          Total Invested
        </span>
        <div className="p-2 rounded-xl" style={{ background: "rgba(31,111,139,0.10)", color: "#1F6F8B" }}>
          <TrendingUp size={14} />
        </div>
      </div>

      {!hasData ? (
        <div className="flex flex-col items-center gap-2 py-3 text-center">
          <AlertCircle size={16} className="text-ocean/20" />
          <p className="text-[12px] text-ocean/40">Not available</p>
          <button
            type="button"
            onClick={() => setActivePage("documents")}
            className="flex items-center gap-1 text-[11px] font-semibold"
            style={{ color: "#1F6F8B" }}
          >
            <RefreshCw size={10} />
            Reprocess statements
          </button>
        </div>
      ) : (
        <>
          <p className="text-[26px] font-bold tracking-tight tabular" style={{ color: "#0B3C5D" }}>
            {fmtUSD(totals.combined)}
          </p>
          {totals.asOf && (
            <p className="text-[10px] text-ocean/35 mt-1">As of {fmtDate(totals.asOf)}</p>
          )}

          {/* Institution breakdown */}
          <div className="mt-3 space-y-1.5">
            {totals.institutions.map((inst) => (
              <div key={inst.institutionKey} className="flex items-center justify-between text-[12px]">
                <span className="text-ocean/55 font-medium">{inst.displayName}</span>
                <span className="font-bold tabular" style={{ color: "#0B3C5D" }}>
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
