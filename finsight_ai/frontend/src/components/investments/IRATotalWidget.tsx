import { ShieldCheck, AlertCircle } from "lucide-react";
import type { AccountBalance } from "../../api/dashboard";
import { fmtUSD, fmtDate } from "../../lib/financeDataAdapters";

interface Props {
  iraAccounts: AccountBalance[];
  loading?: boolean;
}

function Skeleton() {
  return (
    <div className="rounded-2xl p-5 animate-pulse" style={{ background: "rgba(3,17,31,0.60)", border: "1px solid rgba(34,211,238,0.10)" }}>
      <div className="w-20 h-2.5 rounded mb-4" style={{ background: "rgba(34,211,238,0.10)" }} />
      <div className="w-28 h-7 rounded mb-3" style={{ background: "rgba(34,211,238,0.10)" }} />
    </div>
  );
}

export function IRATotalWidget({ iraAccounts, loading }: Props) {
  if (loading) return <Skeleton />;

  const total = iraAccounts.reduce((s, a) => s + (a.total_value ?? 0), 0);
  const hasData = total > 0;
  const dates = iraAccounts
    .map((a) => a.snapshot_date ?? a.latest_statement_date)
    .filter((d): d is string => !!d)
    .sort();
  const latestDate = dates.length > 0 ? dates[dates.length - 1] : null;

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
          IRA Accounts
        </span>
        <div className="p-2 rounded-xl" style={{ background: "rgba(76,175,147,0.15)", color: "#4CAF93" }}>
          <ShieldCheck size={14} />
        </div>
      </div>

      {!hasData ? (
        <div className="flex flex-col items-center gap-2 py-3 text-center">
          <AlertCircle size={16} style={{ color: "rgba(255,255,255,0.18)" }} />
          <p className="text-[12px]" style={{ color: "rgba(255,255,255,0.38)" }}>No IRA accounts found</p>
          <p className="text-[10px] leading-relaxed" style={{ color: "rgba(255,255,255,0.25)" }}>
            Accounts with IRA, Roth, or Rollover in the name will appear here.
          </p>
        </div>
      ) : (
        <>
          <p className="text-[26px] font-bold tracking-tight tabular" style={{ color: "#4CAF93" }}>
            {fmtUSD(total)}
          </p>
          {latestDate && (
            <p className="text-[10px] mt-1" style={{ color: "rgba(255,255,255,0.30)" }}>As of {fmtDate(latestDate)}</p>
          )}
          <div className="mt-3 space-y-1.5">
            {iraAccounts.map((a, i) => (
              <div key={i} className="flex items-center justify-between text-[12px]">
                <span className="font-medium truncate max-w-[140px]" style={{ color: "rgba(255,255,255,0.50)" }}>
                  {a.account_name}
                </span>
                <span className="font-bold tabular" style={{ color: "#4CAF93" }}>
                  {fmtUSD(a.total_value ?? 0)}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
