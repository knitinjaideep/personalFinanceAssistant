import type { RecurringTransaction } from "../../lib/financeDataAdapters";
import type { Subscription } from "../../api/dashboard";

interface Props {
  /** Prefer recurring from API if available; fallback to detected */
  apiSubscriptions?: Subscription[];
  detected?: RecurringTransaction[];
}

function fmtDate(d: string | null): string {
  if (!d) return "—";
  try {
    return new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "2-digit" });
  } catch {
    return d;
  }
}

function fmtAmt(n: number): string {
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function RecurringTransactionsTable({ apiSubscriptions, detected }: Props) {
  // Prefer API subscriptions; fall back to frontend-detected
  const useApi = apiSubscriptions && apiSubscriptions.length > 0;

  if (useApi) {
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr
              className="border-b"
              style={{ borderColor: "rgba(205,237,246,0.60)", color: "rgba(11,60,93,0.38)" }}
            >
              <th className="text-left py-2 pr-3 font-semibold">Merchant</th>
              <th className="text-right py-2 px-2 font-semibold">Avg/mo</th>
              <th className="text-left py-2 px-2 font-semibold hidden sm:table-cell">Frequency</th>
              <th className="text-right py-2 pl-2 font-semibold hidden sm:table-cell">Last seen</th>
            </tr>
          </thead>
          <tbody>
            {apiSubscriptions!.map((sub, i) => (
              <tr
                key={i}
                className="border-b last:border-0"
                style={{ borderColor: "rgba(205,237,246,0.35)" }}
              >
                <td className="py-2 pr-3 font-medium text-ocean-deep max-w-[130px] truncate">
                  {sub.merchant}
                </td>
                <td className="py-2 px-2 text-right font-semibold tabular" style={{ color: "#1F6F8B" }}>
                  {fmtAmt(sub.avg_monthly_amount)}
                </td>
                <td className="py-2 px-2 text-ocean/40 capitalize hidden sm:table-cell">Monthly</td>
                <td className="py-2 pl-2 text-right text-ocean/40 hidden sm:table-cell">
                  {fmtDate(sub.last_seen)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (!detected || detected.length === 0) {
    return (
      <p className="text-[11px] text-ocean/35 italic py-3 text-center">
        No recurring transactions detected.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <div className="mb-2 flex items-center gap-1.5">
        <span
          className="text-[9px] font-semibold px-1.5 py-0.5 rounded-full"
          style={{ background: "rgba(255,209,102,0.18)", color: "#a07800" }}
        >
          Frontend-detected
        </span>
        <span className="text-[10px] text-ocean/35">based on transaction history</span>
      </div>
      <table className="w-full text-xs">
        <thead>
          <tr
            className="border-b"
            style={{ borderColor: "rgba(205,237,246,0.60)", color: "rgba(11,60,93,0.38)" }}
          >
            <th className="text-left py-2 pr-3 font-semibold">Merchant</th>
            <th className="text-right py-2 px-2 font-semibold">Avg amt</th>
            <th className="text-left py-2 px-2 font-semibold hidden sm:table-cell">Frequency</th>
            <th className="text-right py-2 pl-2 font-semibold hidden sm:table-cell">Last seen</th>
          </tr>
        </thead>
        <tbody>
          {detected.map((rx, i) => (
            <tr
              key={i}
              className="border-b last:border-0"
              style={{ borderColor: "rgba(205,237,246,0.35)" }}
            >
              <td className="py-2 pr-3 font-medium text-ocean-deep max-w-[130px] truncate">
                {rx.merchant}
              </td>
              <td className="py-2 px-2 text-right font-semibold tabular" style={{ color: "#1F6F8B" }}>
                {fmtAmt(rx.avgAmount)}
              </td>
              <td className="py-2 px-2 text-ocean/40 hidden sm:table-cell">{rx.frequency}</td>
              <td className="py-2 pl-2 text-right text-ocean/40 hidden sm:table-cell">
                {fmtDate(rx.lastSeen)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
