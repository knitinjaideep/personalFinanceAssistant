import { useState, useMemo } from "react";
import { CheckCircle2, Loader2, XCircle, Clock, Minus } from "lucide-react";
import type { DocumentSummary } from "../../types";
import { buildStatementCoverage, inferYear } from "../../lib/documentLibrary";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

interface Props {
  docs: DocumentSummary[];
}

const CELL_CONFIG = {
  parsed:     { icon: <CheckCircle2 size={11} />, color: "#3db886", bg: "rgba(61,184,134,0.14)", label: "Parsed" },
  processing: { icon: <Loader2 size={11} className="animate-spin" />, color: "#22d3ee", bg: "rgba(34,211,238,0.12)", label: "Processing" },
  failed:     { icon: <XCircle size={11} />, color: "#E45757", bg: "rgba(228,87,87,0.12)", label: "Failed" },
  uploaded:   { icon: <Clock size={11} />, color: "#5FA8D3", bg: "rgba(95,168,211,0.12)", label: "Uploaded" },
  missing:    { icon: <Minus size={11} />, color: "rgba(148,163,184,0.35)", bg: "transparent", label: "Missing" },
};

export function StatementCoverageGrid({ docs }: Props) {
  const years = useMemo(() => {
    const ys = new Set<number>();
    for (const d of docs) {
      const y = inferYear(d);
      if (y) ys.add(y);
    }
    return [...ys].sort((a, b) => b - a);
  }, [docs]);

  const [selectedYear, setSelectedYear] = useState<number | null>(years[0] ?? null);
  const currentYear = selectedYear ?? years[0];

  const rows = useMemo(() => {
    if (!currentYear) return [];
    return buildStatementCoverage(docs, currentYear);
  }, [docs, currentYear]);

  if (docs.length === 0 || years.length === 0) {
    return (
      <div
        className="rounded-2xl px-6 py-8 text-center"
        style={{
          background: "var(--empty-bg)",
          border: "1px dashed var(--empty-border)",
        }}
      >
        <p className="text-[12.5px]" style={{ color: "var(--text-muted)" }}>
          Coverage will appear once Coral can identify statement months.
        </p>
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div
        className="rounded-2xl px-6 py-8 text-center"
        style={{
          background: "var(--empty-bg)",
          border: "1px dashed var(--empty-border)",
        }}
      >
        <p className="text-[12.5px]" style={{ color: "var(--text-muted)" }}>
          No account coverage detected for {currentYear}.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Year selector */}
      {years.length > 1 && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[11px] font-medium" style={{ color: "var(--text-muted)" }}>Year:</span>
          {years.map((y) => (
            <button
              key={y}
              onClick={() => setSelectedYear(y)}
              className="px-2.5 py-1 rounded-lg text-[11px] font-semibold transition-all"
              style={{
                background: currentYear === y ? "rgba(34,211,238,0.15)" : "var(--btn-glass-bg)",
                border: `1px solid ${currentYear === y ? "rgba(34,211,238,0.35)" : "var(--btn-glass-border)"}`,
                color: currentYear === y ? "rgba(34,211,238,0.90)" : "var(--btn-glass-color)",
              }}
            >
              {y}
            </button>
          ))}
        </div>
      )}

      {/* Grid */}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px]" style={{ borderCollapse: "separate", borderSpacing: 0 }}>
          <thead>
            <tr>
              <th
                className="text-left text-[10.5px] font-semibold px-3 py-2 whitespace-nowrap sticky left-0 z-10"
                style={{
                  color: "var(--text-muted)",
                  background: "var(--panel-bg)",
                  borderBottom: "1px solid var(--row-border)",
                  minWidth: 140,
                }}
              >
                Account
              </th>
              {MONTHS.map((m) => (
                <th
                  key={m}
                  className="text-center text-[10px] font-semibold px-1 py-2"
                  style={{
                    color: "var(--text-muted)",
                    borderBottom: "1px solid var(--row-border)",
                    minWidth: 44,
                  }}
                >
                  {m}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.institution}:${row.account}`}>
                <td
                  className="text-[11px] font-medium px-3 py-2 whitespace-nowrap sticky left-0 z-10"
                  style={{
                    color: "var(--text-primary)",
                    background: "var(--panel-bg)",
                    borderBottom: "1px solid var(--row-border)",
                  }}
                >
                  <div>{row.account}</div>
                  <div className="text-[9.5px] mt-0.5" style={{ color: "var(--text-dim)" }}>{row.institution}</div>
                </td>
                {Array.from({ length: 12 }, (_, i) => i + 1).map((month) => {
                  const cell = row.cells[month];
                  const cfg = CELL_CONFIG[cell?.status ?? "missing"];
                  return (
                    <td
                      key={month}
                      className="text-center px-1 py-2"
                      style={{ borderBottom: "1px solid var(--row-border)" }}
                      title={`${row.account} · ${MONTHS[month - 1]} ${currentYear} · ${cfg.label}${cell?.count > 1 ? ` (${cell.count})` : ""}`}
                    >
                      <div
                        className="inline-flex items-center justify-center w-7 h-7 rounded-lg mx-auto"
                        style={{ background: cfg.bg, color: cfg.color }}
                      >
                        {cfg.icon}
                      </div>
                      {cell?.count > 1 && (
                        <div className="text-[8px] mt-0.5" style={{ color: "var(--text-dim)" }}>×{cell.count}</div>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 flex-wrap pt-1">
        {(["parsed", "uploaded", "processing", "failed", "missing"] as const).map((status) => {
          const cfg = CELL_CONFIG[status];
          return (
            <div key={status} className="flex items-center gap-1.5">
              <span className="inline-flex items-center justify-center w-5 h-5 rounded-md" style={{ background: cfg.bg, color: cfg.color }}>
                {cfg.icon}
              </span>
              <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>{cfg.label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
