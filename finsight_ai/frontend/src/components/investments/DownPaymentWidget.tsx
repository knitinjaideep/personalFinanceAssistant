import { Home, AlertCircle } from "lucide-react";
import { fmtUSD } from "../../lib/financeDataAdapters";

interface Props {
  savedAmount: number;
  goalAmount?: number;
  asOf?: string | null;
  loading?: boolean;
}

function Skeleton() {
  return (
    <div className="rounded-2xl p-5 animate-pulse" style={{ background: "rgba(255,255,255,0.88)", border: "1px solid rgba(205,237,246,0.65)" }}>
      <div className="w-28 h-2.5 rounded bg-ocean/10 mb-4" />
      <div className="w-24 h-7 rounded bg-ocean/10" />
    </div>
  );
}

export function DownPaymentWidget({ savedAmount, goalAmount, asOf, loading }: Props) {
  if (loading) return <Skeleton />;

  const pct = goalAmount && goalAmount > 0 ? Math.min(100, (savedAmount / goalAmount) * 100) : null;

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
          Down Payment
        </span>
        <div className="p-2 rounded-xl" style={{ background: "rgba(255,209,102,0.18)", color: "#c89a00" }}>
          <Home size={14} />
        </div>
      </div>

      {savedAmount <= 0 ? (
        <div className="flex flex-col items-center gap-2 py-3 text-center">
          <AlertCircle size={16} className="text-ocean/20" />
          <p className="text-[12px] text-ocean/40">No down payment data found</p>
          <p className="text-[10px] text-ocean/30 max-w-[160px] leading-relaxed">
            Upload Marcus savings statements to track progress.
          </p>
        </div>
      ) : (
        <>
          <p className="text-[26px] font-bold tracking-tight tabular" style={{ color: "#a07800" }}>
            {fmtUSD(savedAmount)}
          </p>
          {asOf && (
            <p className="text-[10px] text-ocean/35 mt-1">As of {asOf}</p>
          )}

          {/* Progress bar if goal is set */}
          {pct !== null && goalAmount ? (
            <div className="mt-3">
              <div className="flex items-center justify-between text-[10px] text-ocean/45 mb-1">
                <span>{pct.toFixed(0)}% of goal</span>
                <span>{fmtUSD(goalAmount)}</span>
              </div>
              <div className="h-2 rounded-full overflow-hidden" style={{ background: "rgba(205,237,246,0.50)" }}>
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${pct}%`,
                    background: "linear-gradient(90deg, #FFD166, #c89a00)",
                  }}
                />
              </div>
            </div>
          ) : (
            <p className="text-[10px] text-ocean/30 mt-2">
              No goal set — tracking savings total from linked accounts.
            </p>
          )}
        </>
      )}
    </div>
  );
}
