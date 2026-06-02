import type { TopTransaction } from "../../lib/financeDataAdapters";

interface Props {
  transactions: TopTransaction[];
  limit?: number;
}

function fmtDate(d: string | null): string {
  if (!d) return "—";
  try {
    return new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric" });
  } catch {
    return d;
  }
}

function fmtCategory(cat: string | null): string {
  if (!cat) return "—";
  return cat.charAt(0).toUpperCase() + cat.slice(1).replace(/_/g, " ");
}

export function TopTransactionsTable({ transactions, limit = 5 }: Props) {
  const rows = transactions.slice(0, limit);

  if (rows.length === 0) {
    return (
      <p className="text-[11px] text-ocean/35 italic py-3 text-center">
        No transaction data available.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr
            className="border-b"
            style={{ borderColor: "rgba(205,237,246,0.60)", color: "rgba(11,60,93,0.38)" }}
          >
            <th className="text-left py-2 pr-3 font-semibold">Date</th>
            <th className="text-left py-2 px-2 font-semibold">Description</th>
            <th className="text-left py-2 px-2 font-semibold hidden sm:table-cell">Category</th>
            <th className="text-right py-2 pl-2 font-semibold">Amount</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((tx, i) => (
            <tr
              key={i}
              className="border-b last:border-0 transition-colors"
              style={{ borderColor: "rgba(205,237,246,0.35)" }}
            >
              <td className="py-2 pr-3 text-ocean/45 whitespace-nowrap">{fmtDate(tx.date)}</td>
              <td className="py-2 px-2 font-medium text-ocean-deep max-w-[140px] truncate">
                {tx.description}
              </td>
              <td className="py-2 px-2 text-ocean/40 hidden sm:table-cell">
                {fmtCategory(tx.category)}
              </td>
              <td className="py-2 pl-2 text-right font-semibold tabular" style={{ color: "#CC5A40" }}>
                ${tx.amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
