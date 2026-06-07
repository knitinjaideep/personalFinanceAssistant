import { CheckCircle, XCircle, AlertCircle } from "lucide-react";
import { SectionCard } from "../dashboard/SectionCard";
import { DashboardEmptyState } from "../dashboard/DashboardEmptyState";
import type { InvestmentCoverageRow } from "../../lib/investmentsDashboard";
import { formatDate } from "../../lib/dashboardData";

interface Props {
  rows: InvestmentCoverageRow[];
  onDocuments?: () => void;
}

function StatusIcon({ status }: { status: "fresh" | "stale" | "missing" }) {
  if (status === "fresh") return <CheckCircle size={14} color="#4CAF93" />;
  if (status === "stale") return <AlertCircle size={14} color="#FFD166" />;
  return <XCircle size={14} color="#E45757" />;
}

export function InvestmentStatementsTab({ rows, onDocuments }: Props) {
  if (rows.length === 0) {
    return (
      <DashboardEmptyState
        title="No statement data"
        description="Upload investment statements to see coverage."
        primaryAction={onDocuments ? { label: "Upload Statements", onClick: onDocuments } : undefined}
      />
    );
  }

  return (
    <SectionCard
      title="Statement Coverage"
      subtitle="Latest parsed statement per investment account"
    >
      <div className="space-y-3">
        {rows.map((row) => (
          <div
            key={row.accountKey}
            className="flex items-center justify-between py-3 px-4 rounded-xl"
            style={{
              background: "var(--row-bg)",
              border: "1px solid var(--row-border)",
            }}
          >
            <div className="flex items-center gap-3 min-w-0">
              <StatusIcon status={row.status} />
              <div className="min-w-0">
                <p className="text-[13px] font-semibold" style={{ color: "var(--text-primary)" }}>
                  {row.accountName}
                </p>
                <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>
                  {row.docCount > 0 ? `${row.docCount} statement${row.docCount > 1 ? "s" : ""} parsed` : "No statements found"}
                </p>
              </div>
            </div>

            <div className="text-right shrink-0 ml-4">
              {row.latestStatement ? (
                <p className="text-[12px] font-semibold" style={{ color: "var(--text-secondary)" }}>
                  {formatDate(row.latestStatement)}
                </p>
              ) : (
                <p className="text-[12px]" style={{ color: "#E45757" }}>
                  Missing
                </p>
              )}
              <p
                className="text-[10px] capitalize mt-0.5"
                style={{
                  color:
                    row.status === "fresh" ? "#4CAF93"
                    : row.status === "stale" ? "#FFD166"
                    : "#E45757",
                }}
              >
                {row.status}
              </p>
            </div>
          </div>
        ))}
      </div>

      {rows.some((r) => r.status === "missing") && (
        <div className="mt-4 pt-4" style={{ borderTop: "1px solid var(--panel-border)" }}>
          <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
            Missing statements affect portfolio value accuracy. Upload or reprocess statements to refresh.
          </p>
          {onDocuments && (
            <button
              type="button"
              onClick={onDocuments}
              className="mt-2 text-[12px] font-semibold transition-colors hover:opacity-80"
              style={{ color: "#22d3ee" }}
            >
              Go to Documents →
            </button>
          )}
        </div>
      )}
    </SectionCard>
  );
}
