import { ShieldCheck, AlertCircle } from "lucide-react";
import type { AccountBalance } from "../../api/dashboard";
import { fmtUSD, fmtDate } from "../../lib/financeDataAdapters";

interface Props {
  iraAccounts: AccountBalance[];
  loading?: boolean;
}

function Skeleton() {
  return (
    <div className="rounded-2xl p-5 animate-pulse" style={{ background: "rgba(255,255,255,0.88)", border: "1px solid rgba(205,237,246,0.65)" }}>
      <div className="w-20 h-2.5 rounded bg-ocean/10 mb-4" />
      <div className="w-28 h-7 rounded bg-ocean/10 mb-3" />
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
        background: "rgba(255,255,255,0.88)",
        border: "1px solid rgba(205,237,246,0.65)",
        boxShadow: "0 4px 24px rgba(11,60,93,0.07), inset 0 1px 0 rgba(255,255,255,0.90)",
      }}
    >
      <div className="flex items-start justify-between mb-3">
        <span className="text-[10px] font-semibold text-ocean/38 uppercase tracking-widest">
          IRA Accounts
        </span>
        <div className="p-2 rounded-xl" style={{ background: "rgba(76,175,147,0.12)", color: "#4CAF93" }}>
          <ShieldCheck size={14} />
        </div>
      </div>

      {!hasData ? (
        <div className="flex flex-col items-center gap-2 py-3 text-center">
          <AlertCircle size={16} className="text-ocean/20" />
          <p className="text-[12px] text-ocean/40">No IRA accounts found</p>
          <p className="text-[10px] text-ocean/30 leading-relaxed">
            Accounts with IRA, Roth, or Rollover in the name will appear here.
          </p>
        </div>
      ) : (
        <>
          <p className="text-[26px] font-bold tracking-tight tabular" style={{ color: "#3a9c7a" }}>
            {fmtUSD(total)}
          </p>
          {latestDate && (
            <p className="text-[10px] text-ocean/35 mt-1">As of {fmtDate(latestDate)}</p>
          )}
          <div className="mt-3 space-y-1.5">
            {iraAccounts.map((a, i) => (
              <div key={i} className="flex items-center justify-between text-[12px]">
                <span className="text-ocean/55 font-medium truncate max-w-[140px]">
                  {a.account_name}
                </span>
                <span className="font-bold tabular" style={{ color: "#3a9c7a" }}>
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
