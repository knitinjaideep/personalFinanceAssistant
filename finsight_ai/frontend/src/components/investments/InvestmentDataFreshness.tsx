import { CheckCircle, AlertCircle, Database, Clock } from "lucide-react";
import { DataFreshnessBadge } from "../dashboard/DataFreshnessBadge";
import type { InvestmentFreshnessItem } from "../../lib/investmentsDashboard";

interface Props {
  items: InvestmentFreshnessItem[];
  accountsDetected: number;
}

export function InvestmentDataFreshness({ items, accountsDetected }: Props) {
  const missing = items.filter((i) => i.status === "missing").length;
  const hasIssues = missing > 0;

  return (
    <div
      className="rounded-[20px] px-5 py-4"
      style={{
        background: hasIssues ? "rgba(255,209,102,0.05)" : "rgba(76,175,147,0.05)",
        border: `1px solid ${hasIssues ? "rgba(255,209,102,0.15)" : "rgba(76,175,147,0.15)"}`,
      }}
    >
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-1.5 mb-2">
            {hasIssues ? (
              <AlertCircle size={12} color="#FFD166" />
            ) : (
              <CheckCircle size={12} color="#4CAF93" />
            )}
            <span
              className="text-[11px] font-semibold uppercase tracking-wide"
              style={{ color: hasIssues ? "#FFD166" : "#4CAF93" }}
            >
              {hasIssues ? "Missing investment statements" : "Portfolio data is fresh"}
            </span>
          </div>
          <div className="flex flex-wrap gap-x-5 gap-y-1">
            {items.map((item) => (
              <DataFreshnessBadge
                key={item.institutionKey}
                label={item.label}
                latestDate={item.latestDate}
              />
            ))}
          </div>
        </div>

        <div className="flex items-center gap-4 shrink-0">
          <div className="flex items-center gap-1.5">
            <Database size={11} style={{ color: "var(--text-dim)" }} />
            <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
              <span className="font-semibold" style={{ color: "var(--text-secondary)" }}>{accountsDetected}</span> accounts
            </span>
          </div>
          {hasIssues && (
            <div className="flex items-center gap-1.5">
              <Clock size={11} color="#FFD166" />
              <span className="text-[11px]" style={{ color: "#FFD166" }}>
                Upload to refresh
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
