"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, FileText, ArrowRight, Code2, BarChart3 } from "lucide-react";
import { clsx } from "clsx";
import { motion, AnimatePresence } from "framer-motion";
import {
  BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, Tooltip,
  ResponsiveContainer, Legend,
} from "recharts";
import type { StructuredAnswer, ChartPayload } from "@/types/index";
import { DebugPanel } from "./DebugPanel";
import { useAppStore } from "@/store/appStore";
import { formatTime } from "@/lib/utils";

const FRIENDLY_LABELS: Record<string, string> = {
  fee_category: "Category", institution: "Institution", fee_count: "Count",
  total_amount: "Amount", transaction_type: "Type", merchant_name: "Merchant",
  transaction_date: "Date", description: "Description", amount: "Amount",
  symbol: "Symbol", market_value: "Value", percent_of_portfolio: "% Portfolio",
  category: "Category", count: "Count", total: "Total",
  account_type: "Account", institution_type: "Institution",
};

function friendlyLabel(col: string): string {
  return FRIENDLY_LABELS[col] || col.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function fmtUSD(v: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(v);
}

const CHART_COLORS = [
  "#22d3ee", "#FF7A5A", "#4CAF93", "#F2C94C", "#9B59B6",
  "#E67E22", "#2ECC71", "#E74C3C", "#3498DB", "#1ABC9C",
];

function useTooltipStyle() {
  const isLight = useAppStore((s) => s.theme === "light");
  return {
    borderRadius: 10, fontSize: 12,
    background: isLight ? "rgba(255,255,255,0.97)" : "rgba(3,17,31,0.92)",
    border: isLight ? "1px solid rgba(31,111,139,0.20)" : "1px solid rgba(34,211,238,0.22)",
    boxShadow: isLight ? "0 4px 16px rgba(11,60,93,0.15)" : "0 4px 16px rgba(3,17,31,0.50)",
    color: isLight ? "rgba(11,40,65,0.85)" : "rgba(255,255,255,0.85)",
  };
}

function useAxisColor() {
  const isLight = useAppStore((s) => s.theme === "light");
  return isLight ? "rgba(11,40,65,0.45)" : "rgba(255,255,255,0.38)";
}

function AnswerChart({ payload }: { payload: ChartPayload }) {
  const { type, title, labels, datasets, currency } = payload;
  const fmt = currency ? fmtUSD : (v: number) => String(v);
  const tooltipStyle = useTooltipStyle();
  const axisColor = useAxisColor();

  if (type === "pie") {
    const data = labels.map((name, i) => ({ name, value: datasets[0]?.data[i] ?? 0 }));
    return (
      <div className="px-5 py-4" style={{ borderTop: "1px solid var(--answer-divider)" }}>
        <p className="text-xs font-semibold mb-3 flex items-center gap-1.5" style={{ color: "var(--text-muted)" }}>
          <BarChart3 size={11} /> {title}
        </p>
        <ResponsiveContainer width="100%" height={200}>
          <PieChart>
            <Pie data={data} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80}
              labelLine={false}
            >
              {data.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
            </Pie>
            <Tooltip formatter={(v) => fmt(Number(v))} contentStyle={tooltipStyle} />
          </PieChart>
          {/* label function removed from Pie to avoid recharts type issue */}
        </ResponsiveContainer>
      </div>
    );
  }

  if (type === "horizontal_bar") {
    const data = labels.map((name, i) => ({
      name: name.length > 20 ? name.slice(0, 20) + "…" : name,
      value: datasets[0]?.data[i] ?? 0,
    }));
    return (
      <div className="px-5 py-4" style={{ borderTop: "1px solid var(--answer-divider)" }}>
        <p className="text-xs font-semibold mb-3 flex items-center gap-1.5" style={{ color: "var(--text-muted)" }}>
          <BarChart3 size={11} /> {title}
        </p>
        <ResponsiveContainer width="100%" height={Math.max(180, data.length * 32)}>
          <BarChart layout="vertical" data={data} margin={{ left: 8, right: 24, top: 4, bottom: 4 }}>
            <XAxis type="number" tickFormatter={fmt} tick={{ fontSize: 10, fill: axisColor }} />
            <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 10, fill: axisColor }} />
            <Tooltip formatter={(v) => fmt(Number(v))} contentStyle={tooltipStyle} />
            <Bar dataKey="value" radius={[0, 4, 4, 0]}>
              {data.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  }

  const data = labels.map((name, i) => {
    const entry: Record<string, unknown> = { name };
    datasets.forEach((ds) => { entry[ds.label] = ds.data[i] ?? 0; });
    return entry;
  });
  return (
    <div className="px-5 py-4" style={{ borderTop: "1px solid var(--answer-divider)" }}>
      <p className="text-xs font-semibold mb-3 flex items-center gap-1.5" style={{ color: "var(--text-muted)" }}>
        <BarChart3 size={11} /> {title}
      </p>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data} margin={{ left: 8, right: 8, top: 4, bottom: 4 }}>
          <XAxis dataKey="name" tick={{ fontSize: 10, fill: axisColor }} />
          <YAxis tickFormatter={fmt} tick={{ fontSize: 10, fill: axisColor }} />
          <Tooltip formatter={(v) => fmt(Number(v))} contentStyle={tooltipStyle} />
          {datasets.length > 1 && <Legend wrapperStyle={{ fontSize: 10, color: "var(--text-secondary)" }} />}
          {datasets.map((ds, i) => (
            <Bar key={ds.label} dataKey={ds.label} fill={CHART_COLORS[i % CHART_COLORS.length]} radius={[4, 4, 0, 0]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function SqlDisclosure({ sql, rowCount }: { sql: string[]; rowCount: number }) {
  const [open, setOpen] = useState(false);
  if (!sql.length) return null;
  return (
    <div style={{ borderTop: "1px solid var(--answer-divider)" }}>
      <button onClick={() => setOpen(!open)} className="w-full px-5 py-2 flex items-center justify-between text-[10px] transition-colors" style={{ color: "var(--text-dim)" }}>
        <span className="flex items-center gap-1.5"><Code2 size={9} /> SQL · {rowCount} row{rowCount !== 1 ? "s" : ""}</span>
        {open ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }} className="overflow-hidden">
            <pre className="mx-5 mb-4 px-3 py-2.5 rounded-xl text-[10px] leading-relaxed overflow-x-auto"
              style={{ background: "var(--answer-sql-bg)", border: "1px solid var(--panel-border-accent)", color: "rgba(34,211,238,0.65)", fontFamily: "ui-monospace, SFMono-Regular, monospace", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
              {sql[0]}
            </pre>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function SourcesDrawer({ citations }: { citations: StructuredAnswer["citations"] }) {
  const [open, setOpen] = useState(false);
  if (citations.length === 0) return null;
  return (
    <div style={{ borderTop: "1px solid var(--answer-divider)" }}>
      <button onClick={() => setOpen(!open)} className="w-full px-5 py-2.5 flex items-center justify-between text-xs transition-colors" style={{ color: "var(--text-dim)" }}>
        <span className="flex items-center gap-1.5"><FileText size={10} /> {citations.length} source{citations.length !== 1 ? "s" : ""}</span>
        {open ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.25 }} className="overflow-hidden">
            <div className="px-5 pb-4 space-y-2">
              {citations.map((c, i) => (
                <div key={i} className="p-3 rounded-2xl text-xs" style={{ background: "var(--row-bg)", border: "1px solid var(--panel-border-accent)" }}>
                  <p className="font-semibold" style={{ color: "rgba(34,211,238,0.75)" }}>{c.source}</p>
                  <p className="mt-1 leading-relaxed" style={{ color: "var(--text-secondary)" }}>{c.text.length > 200 ? `${c.text.slice(0, 200)}…` : c.text}</p>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function FollowUps({ questions, onSelect }: { questions: string[]; onSelect: (q: string) => void }) {
  if (questions.length === 0) return null;
  return (
    <div className="px-5 py-3.5 flex flex-wrap gap-2" style={{ borderTop: "1px solid var(--answer-divider)" }}>
      {questions.map((q) => (
        <motion.button key={q} whileHover={{ scale: 1.03, y: -1 }} whileTap={{ scale: 0.97 }} onClick={() => onSelect(q)}
          className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-full transition-colors duration-150"
          style={{ background: "var(--answer-followup-bg)", border: "1px solid var(--answer-followup-border)", color: "var(--answer-followup-color)" }}>
          {q} <ArrowRight size={9} />
        </motion.button>
      ))}
    </div>
  );
}

function CaveatBar({ caveats }: { caveats: string[] }) {
  if (caveats.length === 0) return null;
  return (
    <div className="px-5 py-2.5" style={{ borderTop: "1px solid var(--warn-border)", background: "var(--warn-bg)" }}>
      {caveats.map((c, i) => <p key={i} className="text-xs" style={{ color: "var(--warn-text)" }}>⚠ {c}</p>)}
    </div>
  );
}

function BasedOnBar({ basedOn, rowsUsed }: { basedOn?: string; rowsUsed?: number }) {
  if (!basedOn && !rowsUsed) return null;
  const label = basedOn || (rowsUsed ? `${rowsUsed} rows` : "");
  if (!label) return null;
  return (
    <div
      className="px-5 py-2 flex items-center gap-1.5 text-[10px] font-medium"
      style={{ borderTop: "1px solid var(--answer-divider)", color: "var(--text-dim)" }}
    >
      <span style={{ color: "rgba(34,211,238,0.45)" }}>Based on</span>
      <span style={{ color: "var(--text-muted)" }}>{label}</span>
    </div>
  );
}

interface CardShellProps {
  children: React.ReactNode;
  className?: string;
  chartPayload?: ChartPayload | null;
  sqlUsed?: string[];
  rowsUsed?: number;
  basedOn?: string;
}

function CardShell({ children, className, chartPayload, sqlUsed, rowsUsed, basedOn }: CardShellProps) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.22 }}
      className={clsx("max-w-2xl rounded-3xl overflow-hidden", className)}
      style={{ background: "var(--answer-bg)", backdropFilter: "blur(14px)", WebkitBackdropFilter: "blur(14px)", border: "1px solid var(--answer-border)", boxShadow: "var(--answer-shadow)" }}
    >
      {children}
      {chartPayload && <AnswerChart payload={chartPayload} />}
      <BasedOnBar basedOn={basedOn} rowsUsed={rowsUsed} />
      {sqlUsed && sqlUsed.length > 0 && <SqlDisclosure sql={sqlUsed} rowCount={rowsUsed ?? 0} />}
    </motion.div>
  );
}

interface CardExtraProps {
  answer: StructuredAnswer;
  onFollowup: (q: string) => void;
}

function MetricAnswer({ answer, onFollowup }: CardExtraProps) {
  const bullets = answer.highlights.slice(0, 4);
  return (
    <CardShell chartPayload={answer.chart_payload} sqlUsed={answer.sql_used} rowsUsed={answer.rows_used} basedOn={answer.based_on}>
      <div className="px-5 py-4" style={{ borderBottom: "1px solid var(--answer-divider)" }}>
        <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>{answer.title}</h3>
      </div>
      {answer.primary_value && (
        <div className="px-5 py-5" style={{ borderBottom: "1px solid var(--answer-divider)", background: "var(--answer-metric-bg)" }}>
          <p className="text-3xl font-bold tracking-tight tabular" style={{ color: "var(--text-primary)" }}>{answer.primary_value}</p>
          {answer.summary && <p className="text-sm mt-1.5 leading-relaxed" style={{ color: "var(--text-secondary)" }}>{answer.summary}</p>}
        </div>
      )}
      {bullets.length > 0 && (
        <div className="px-5 py-4 space-y-2" style={{ borderBottom: "1px solid var(--answer-divider)" }}>
          {bullets.map((h, i) => (
            <div key={i} className="flex items-baseline gap-2 text-sm">
              <span className="w-1.5 h-1.5 rounded-full shrink-0 mt-[5px]" style={{ background: "#22d3ee" }} />
              <span style={{ color: "var(--text-muted)" }}>{h.label}:</span>
              <span className="font-semibold" style={{ color: "var(--text-primary)" }}>{h.value}</span>
            </div>
          ))}
        </div>
      )}
      <CaveatBar caveats={answer.caveats} />
      <SourcesDrawer citations={answer.citations} />
      <FollowUps questions={answer.suggested_followups} onSelect={onFollowup} />
    </CardShell>
  );
}

function SummaryAnswer({ answer, onFollowup }: CardExtraProps) {
  return (
    <CardShell chartPayload={answer.chart_payload} sqlUsed={answer.sql_used} rowsUsed={answer.rows_used} basedOn={answer.based_on}>
      <div className="px-5 py-4" style={{ borderBottom: "1px solid var(--answer-divider)" }}>
        <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>{answer.title}</h3>
      </div>
      <div className="px-5 py-4">
        <p className="text-sm leading-relaxed whitespace-pre-wrap" style={{ color: "var(--text-secondary)" }}>{answer.summary}</p>
      </div>
      {answer.highlights.length > 0 && (
        <div className="px-5 pb-4 pt-3 space-y-1.5" style={{ borderTop: "1px solid var(--answer-divider)" }}>
          {answer.highlights.slice(0, 4).map((h, i) => (
            <div key={i} className="flex items-baseline gap-2 text-sm">
              <span className="w-1.5 h-1.5 rounded-full shrink-0 mt-[5px]" style={{ background: "#FF7A5A" }} />
              <span style={{ color: "var(--text-muted)" }}>{h.label}:</span>
              <span className="font-semibold" style={{ color: "var(--text-primary)" }}>{h.value}</span>
            </div>
          ))}
        </div>
      )}
      <CaveatBar caveats={answer.caveats} />
      <SourcesDrawer citations={answer.citations} />
      <FollowUps questions={answer.suggested_followups} onSelect={onFollowup} />
    </CardShell>
  );
}

function RankedListAnswer({ answer, onFollowup }: CardExtraProps) {
  const section = answer.sections.find((s) => s.type === "table" && s.rows && s.columns);
  const renderRows = () => {
    if (section && section.rows && section.columns) {
      const cols = section.columns as string[];
      const rows = (section.rows as Record<string, unknown>[]).slice(0, 10);
      const valueCol = cols.find((c) => c.includes("amount") || c.includes("total") || c.includes("value"));
      return rows.map((row, i) => {
        const label = String(row[cols[0]] ?? "—");
        const value = valueCol ? String(row[valueCol] ?? "") : null;
        return (
          <div key={i} className="flex items-center justify-between py-2.5 last:border-0" style={{ borderBottom: "1px solid var(--row-border)" }}>
            <div className="flex items-center gap-3">
              <span className="w-5 text-xs font-bold text-right shrink-0" style={{ color: "var(--text-dim)" }}>{i + 1}</span>
              <span className="text-sm" style={{ color: "var(--text-secondary)" }}>{label}</span>
            </div>
            {value && <span className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>{value}</span>}
          </div>
        );
      });
    }
    return answer.highlights.map((h, i) => (
      <div key={i} className="flex items-center justify-between py-2.5 last:border-0" style={{ borderBottom: "1px solid var(--row-border)" }}>
        <div className="flex items-center gap-3">
          <span className="w-5 text-xs font-bold text-right shrink-0" style={{ color: "var(--text-dim)" }}>{i + 1}</span>
          <span className="text-sm" style={{ color: "var(--text-secondary)" }}>{h.label}</span>
        </div>
        <span className="text-sm font-bold" style={{ color: "var(--text-primary)" }}>{h.value}</span>
      </div>
    ));
  };
  const totalRows = section?.rows ? (section.rows as unknown[]).length : answer.highlights.length;
  return (
    <CardShell chartPayload={answer.chart_payload} sqlUsed={answer.sql_used} rowsUsed={answer.rows_used} basedOn={answer.based_on}>
      <div className="px-5 py-4" style={{ borderBottom: "1px solid var(--answer-divider)" }}>
        <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>{answer.title}</h3>
        {answer.summary && <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>{answer.summary}</p>}
      </div>
      <div className="px-5 py-3">{renderRows()}</div>
      {totalRows > 10 && <p className="px-5 pb-3 text-xs" style={{ color: "var(--text-dim)" }}>Showing top 10 of {totalRows}</p>}
      <CaveatBar caveats={answer.caveats} />
      <SourcesDrawer citations={answer.citations} />
      <FollowUps questions={answer.suggested_followups} onSelect={onFollowup} />
    </CardShell>
  );
}

function TableAnswer({ answer, onFollowup }: CardExtraProps) {
  const section = answer.sections.find((s) => s.type === "table" && s.rows && s.columns);
  return (
    <CardShell chartPayload={answer.chart_payload} sqlUsed={answer.sql_used} rowsUsed={answer.rows_used} basedOn={answer.based_on}>
      <div className="px-5 py-4" style={{ borderBottom: "1px solid var(--answer-divider)" }}>
        <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>{answer.title}</h3>
        {answer.summary && <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>{answer.summary}</p>}
      </div>
      {section && section.rows && section.columns ? (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr style={{ background: "var(--table-row-alt)", borderBottom: "1px solid var(--row-border-strong)" }}>
                {(section.columns as string[]).map((col) => (
                  <th key={col} className="px-4 py-2.5 text-left font-semibold uppercase tracking-wide text-[10px]" style={{ color: "rgba(34,211,238,0.65)" }}>
                    {friendlyLabel(col)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(section.rows as Record<string, unknown>[]).slice(0, 15).map((row, i) => (
                <tr key={i} className="transition-colors" style={{ borderBottom: "1px solid var(--row-border)" }}>
                  {(section.columns as string[]).map((col) => (
                    <td key={col} className="px-4 py-2.5" style={{ color: "var(--text-secondary)" }}>
                      {row[col] != null ? String(row[col]) : "—"}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {(section.rows as unknown[]).length > 15 && (
            <p className="px-4 py-2 text-xs" style={{ borderTop: "1px solid var(--row-border)", color: "var(--text-dim)" }}>
              Showing 15 of {(section.rows as unknown[]).length} rows
            </p>
          )}
        </div>
      ) : (
        <div className="px-5 py-4">
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>{answer.summary}</p>
        </div>
      )}
      <CaveatBar caveats={answer.caveats} />
      <SourcesDrawer citations={answer.citations} />
      <FollowUps questions={answer.suggested_followups} onSelect={onFollowup} />
    </CardShell>
  );
}

function ComparisonAnswer({ answer, onFollowup }: CardExtraProps) {
  return (
    <CardShell chartPayload={answer.chart_payload} sqlUsed={answer.sql_used} rowsUsed={answer.rows_used} basedOn={answer.based_on}>
      <div className="px-5 py-4" style={{ borderBottom: "1px solid var(--answer-divider)" }}>
        <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>{answer.title}</h3>
      </div>
      {answer.highlights.length > 0 && (
        <div className="px-5 py-4 grid grid-cols-2 gap-4" style={{ borderBottom: "1px solid var(--answer-divider)" }}>
          {answer.highlights.slice(0, 6).map((h, i) => (
            <div key={i} className="space-y-0.5">
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>{h.label}</p>
              <p className="text-base font-bold tabular" style={{ color: "var(--text-primary)" }}>{h.value}</p>
            </div>
          ))}
        </div>
      )}
      {answer.summary && (
        <div className="px-5 py-4">
          <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>{answer.summary}</p>
        </div>
      )}
      <CaveatBar caveats={answer.caveats} />
      <SourcesDrawer citations={answer.citations} />
      <FollowUps questions={answer.suggested_followups} onSelect={onFollowup} />
    </CardShell>
  );
}

function NoDataAnswer({ answer, onFollowup }: CardExtraProps) {
  return (
    <CardShell>
      <div className="px-5 py-8 text-center">
        <div className="text-3xl mb-4">🔍</div>
        <h3 className="text-sm font-semibold mb-1.5" style={{ color: "var(--text-primary)" }}>{answer.title}</h3>
        <p className="text-sm leading-relaxed max-w-xs mx-auto" style={{ color: "var(--text-secondary)" }}>
          {answer.summary || "No data found. Try uploading relevant statements first."}
        </p>
      </div>
      <FollowUps questions={answer.suggested_followups} onSelect={onFollowup} />
    </CardShell>
  );
}

export interface AnswerCardProps {
  answer: StructuredAnswer;
  onFollowup: (q: string) => void;
  timestamp?: string;
}

export function AnswerCard({ answer, onFollowup, timestamp }: AnswerCardProps) {
  let card: React.ReactNode;

  if (answer.answer_type === "no_data") {
    card = <NoDataAnswer answer={answer} onFollowup={onFollowup} />;
  } else if (answer.answer_type === "numeric") {
    card = <MetricAnswer answer={answer} onFollowup={onFollowup} />;
  } else if (answer.answer_type === "comparison") {
    card = <ComparisonAnswer answer={answer} onFollowup={onFollowup} />;
  } else if (answer.answer_type === "table") {
    const section = answer.sections.find((s) => s.type === "table" && s.columns && s.rows);
    const colCount = (section?.columns as string[] | undefined)?.length ?? 0;
    card = colCount <= 3
      ? <RankedListAnswer answer={answer} onFollowup={onFollowup} />
      : <TableAnswer answer={answer} onFollowup={onFollowup} />;
  } else {
    card = <SummaryAnswer answer={answer} onFollowup={onFollowup} />;
  }

  return (
    <div className="flex flex-col items-start gap-1 w-full">
      {card}
      <DebugPanel answer={answer} />
      {timestamp && (
        <span className="text-[10px] ml-1" style={{ color: "var(--text-dim)" }}>{formatTime(timestamp)}</span>
      )}
    </div>
  );
}
