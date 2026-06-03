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
    <div className="rounded-2xl p-5 animate-pulse" style={{ background: "rgba(3,17,31,0.60)", border: "1px solid rgba(34,211,238,0.10)" }}>
      <div className="w-28 h-2.5 rounded mb-4" style={{ background: "rgba(34,211,238,0.10)" }} />
      <div className="w-24 h-7 rounded" style={{ background: "rgba(34,211,238,0.10)" }} />
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
        background: "rgba(3,17,31,0.60)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        border: "1px solid rgba(34,211,238,0.12)",
        boxShadow: "0 8px 32px rgba(3,17,31,0.40)",
      }}
    >
      <div className="flex items-start justify-between mb-3">
        <span className="text-[10px] font-semibold uppercase tracking-widest" style={{ color: "rgba(255,255,255,0.35)" }}>
          Down Payment
        </span>
        <div className="p-2 rounded-xl" style={{ background: "rgba(255,209,102,0.14)", color: "#FFD166" }}>
          <Home size={14} />
        </div>
      </div>

      {savedAmount <= 0 ? (
        <div className="flex flex-col items-center gap-2 py-3 text-center">
          <AlertCircle size={16} style={{ color: "rgba(255,255,255,0.18)" }} />
          <p className="text-[12px]" style={{ color: "rgba(255,255,255,0.38)" }}>No down payment data found</p>
          <p className="text-[10px] max-w-[160px] leading-relaxed" style={{ color: "rgba(255,255,255,0.25)" }}>
            Upload Marcus savings statements to track progress.
          </p>
        </div>
      ) : (
        <>
          <p className="text-[26px] font-bold tracking-tight tabular" style={{ color: "#FFD166" }}>
            {fmtUSD(savedAmount)}
          </p>
          {asOf && (
            <p className="text-[10px] mt-1" style={{ color: "rgba(255,255,255,0.30)" }}>As of {asOf}</p>
          )}

          {pct !== null && goalAmount ? (
            <div className="mt-3">
              <div className="flex items-center justify-between text-[10px] mb-1" style={{ color: "rgba(255,255,255,0.40)" }}>
                <span>{pct.toFixed(0)}% of goal</span>
                <span>{fmtUSD(goalAmount)}</span>
              </div>
              <div className="h-2 rounded-full overflow-hidden" style={{ background: "rgba(34,211,238,0.10)" }}>
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${pct}%`,
                    background: "linear-gradient(90deg, #FFD166, #FFA38F)",
                  }}
                />
              </div>
            </div>
          ) : (
            <p className="text-[10px] mt-2" style={{ color: "rgba(255,255,255,0.28)" }}>
              No goal set — tracking savings total from linked accounts.
            </p>
          )}
        </>
      )}
    </div>
  );
}
