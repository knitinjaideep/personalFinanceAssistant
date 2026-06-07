import { RepeatIcon } from "lucide-react";
import { SectionCard } from "../dashboard/SectionCard";
import { DashboardEmptyState } from "../dashboard/DashboardEmptyState";
import type { Subscription } from "../../api/dashboard";
import { safeArray } from "../../lib/dashboardData";

interface Props {
  subscriptions: Subscription[];
  onDocuments?: () => void;
}

const CONFIDENCE_COLORS = {
  high: "#4CAF93",
  medium: "#FFD166",
};

export function BankingRecurringTab({ subscriptions, onDocuments }: Props) {
  const items = safeArray(subscriptions);

  return (
    <SectionCard title="Recurring Charges" subtitle="Detected subscription and recurring payments">
      {items.length === 0 ? (
        <DashboardEmptyState
          icon={<RepeatIcon size={22} />}
          title="No recurring charges detected"
          description="Recurring charges will appear after Coral sees the same merchant across multiple statements."
          primaryAction={onDocuments ? { label: "Upload Statements", onClick: onDocuments } : undefined}
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead>
              <tr
                className="border-b"
                style={{ borderColor: "var(--row-border-strong)", color: "var(--table-head)" }}
              >
                <th className="text-left py-2.5 pr-3 font-semibold">Merchant</th>
                <th className="text-left py-2.5 px-2 font-semibold hidden sm:table-cell">Category</th>
                <th className="text-right py-2.5 px-2 font-semibold">Avg / Month</th>
                <th className="text-left py-2.5 px-2 font-semibold hidden md:table-cell">Frequency</th>
                <th className="text-left py-2.5 pl-2 font-semibold hidden sm:table-cell">Last Seen</th>
                <th className="text-right py-2.5 pl-2 font-semibold">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {items.map((sub, i) => (
                <tr
                  key={i}
                  className="border-b last:border-0"
                  style={{ borderColor: "var(--row-border)" }}
                >
                  <td className="py-2.5 pr-3">
                    <span className="font-semibold" style={{ color: "var(--text-primary)" }}>
                      {sub.merchant}
                    </span>
                  </td>
                  <td className="py-2.5 px-2 hidden sm:table-cell" style={{ color: "var(--text-muted)" }}>
                    {sub.category ?? "—"}
                  </td>
                  <td className="py-2.5 px-2 text-right font-semibold tabular" style={{ color: "var(--text-secondary)" }}>
                    ${sub.avg_monthly_amount_fmt}
                  </td>
                  <td className="py-2.5 px-2 hidden md:table-cell" style={{ color: "var(--text-muted)" }}>
                    {sub.occurrences}× seen
                  </td>
                  <td className="py-2.5 px-2 hidden sm:table-cell" style={{ color: "var(--text-muted)" }}>
                    {sub.last_seen ? sub.last_seen.slice(0, 7) : "—"}
                  </td>
                  <td className="py-2.5 pl-2 text-right">
                    <span
                      className="text-[10px] font-semibold px-2 py-0.5 rounded-full"
                      style={{
                        background: `${CONFIDENCE_COLORS[sub.confidence] ?? "#22d3ee"}15`,
                        color: CONFIDENCE_COLORS[sub.confidence] ?? "#22d3ee",
                      }}
                    >
                      {sub.confidence}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </SectionCard>
  );
}
