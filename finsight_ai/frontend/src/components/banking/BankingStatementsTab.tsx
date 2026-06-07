import { CheckCircle, XCircle } from "lucide-react";
import { SectionCard } from "../dashboard/SectionCard";
import { DashboardEmptyState } from "../dashboard/DashboardEmptyState";
import type { StatementCoverageRow } from "../../lib/bankingDashboard";
import { monthLabel } from "../../lib/dashboardData";

interface Props {
  months: string[];
  rows: StatementCoverageRow[];
  onDocuments?: () => void;
}

export function BankingStatementsTab({ months, rows, onDocuments }: Props) {
  if (rows.length === 0) {
    return (
      <DashboardEmptyState
        title="No statement data"
        description="Upload banking statements to see coverage."
        primaryAction={onDocuments ? { label: "Upload Statements", onClick: onDocuments } : undefined}
      />
    );
  }

  return (
    <SectionCard
      title="Statement Coverage"
      subtitle="Shows which months have been parsed for each account"
    >
      <div className="overflow-x-auto">
        <table className="w-full text-[11px]" style={{ minWidth: 520 }}>
          <thead>
            <tr>
              <th className="text-left py-2 pr-4 font-semibold w-40" style={{ color: "var(--table-head)" }}>
                Account
              </th>
              {months.map((m) => (
                <th key={m} className="text-center px-1 font-semibold" style={{ color: "var(--table-head)" }}>
                  {monthLabel(m)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.accountKey} className="border-t" style={{ borderColor: "var(--row-border)" }}>
                <td className="py-2 pr-4">
                  <p className="font-semibold truncate" style={{ color: "var(--text-primary)", maxWidth: 140 }}>
                    {row.accountName}
                  </p>
                  <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>
                    {row.institution}
                  </p>
                </td>
                {months.map((m) => {
                  const status = row.months[m];
                  return (
                    <td key={m} className="text-center px-1 py-2">
                      {status === "parsed" ? (
                        <CheckCircle size={13} color="#4CAF93" className="mx-auto" />
                      ) : (
                        <XCircle size={13} color="rgba(220,242,250,0.2)" className="mx-auto" />
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center gap-4 mt-4 pt-4" style={{ borderTop: "1px solid var(--panel-border)" }}>
        <div className="flex items-center gap-1.5 text-[11px]" style={{ color: "var(--text-muted)" }}>
          <CheckCircle size={12} color="#4CAF93" />
          Parsed
        </div>
        <div className="flex items-center gap-1.5 text-[11px]" style={{ color: "var(--text-muted)" }}>
          <XCircle size={12} color="rgba(220,242,250,0.2)" />
          Missing / not uploaded
        </div>
      </div>
    </SectionCard>
  );
}
