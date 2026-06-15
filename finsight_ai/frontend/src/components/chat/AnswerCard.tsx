/**
 * AnswerCard — premium spatial underwater glass answer system.
 */

import { useState } from "react";
import {
  ChevronDown, ChevronUp, FileText, ArrowRight, Code2, BarChart3,
  AlertTriangle, TrendingUp, TrendingDown, Minus, Search,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import {
  BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, Tooltip,
  ResponsiveContainer, Legend,
} from "recharts";
import { assistantBubbleVariants, staggerContainer, staggerChild } from "../../design/motion";
import type { StructuredAnswer, ChartPayload } from "../../types";
import { DebugPanel } from "./DebugPanel";
import { useAppStore } from "../../store/appStore";

// ── Utilities ────────────────────────────────────────────────────────────────

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
    borderRadius: 12, fontSize: 12,
    background: isLight ? "rgba(255,255,255,0.97)" : "rgba(4,18,34,0.95)",
    border: isLight ? "1px solid rgba(31,111,139,0.22)" : "1px solid rgba(34,211,238,0.22)",
    boxShadow: isLight ? "0 4px 20px rgba(11,60,93,0.14)" : "0 4px 20px rgba(3,17,31,0.55)",
    color: isLight ? "rgba(11,40,65,0.88)" : "rgba(220,242,250,0.88)",
  };
}

function useAxisColor() {
  const isLight = useAppStore((s) => s.theme === "light");
  return isLight ? "rgba(11,40,65,0.48)" : "rgba(190,220,232,0.48)";
}

// ── Divider ───────────────────────────────────────────────────────────────────

function Divider() {
  return <div style={{ borderTop: "1px solid var(--answer-divider)" }} />;
}

// ── AnswerChart ───────────────────────────────────────────────────────────────

function AnswerChart({ payload }: { payload: ChartPayload }) {
  const { type, title, labels, datasets, currency } = payload;
  if (!Array.isArray(labels) || !Array.isArray(datasets) || labels.length === 0) return null;

  const fmt = currency ? fmtUSD : (v: number) => String(v);
  const tooltipStyle = useTooltipStyle();
  const axisColor = useAxisColor();

  if (type === "pie") {
    const data = labels.map((name, i) => ({ name, value: datasets[0]?.data[i] ?? 0 }));
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.15 }}
        className="px-5 py-5"
        style={{ borderTop: "1px solid var(--answer-divider)" }}
      >
        <p className="text-xs font-semibold mb-4 flex items-center gap-1.5" style={{ color: "var(--text-muted)" }}>
          <BarChart3 size={11} />
          {title}
        </p>
        <ResponsiveContainer width="100%" height={210}>
          <PieChart>
            <Pie data={data} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={84}
              label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
              labelLine={false}
            >
              {data.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
            </Pie>
            <Tooltip formatter={(v: number) => fmt(v)} contentStyle={tooltipStyle} />
          </PieChart>
        </ResponsiveContainer>
      </motion.div>
    );
  }

  if (type === "horizontal_bar") {
    const data = labels.map((name, i) => ({
      name: name.length > 22 ? name.slice(0, 22) + "…" : name,
      value: datasets[0]?.data[i] ?? 0,
    }));
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.15 }}
        className="px-5 py-5"
        style={{ borderTop: "1px solid var(--answer-divider)" }}
      >
        <p className="text-xs font-semibold mb-4 flex items-center gap-1.5" style={{ color: "var(--text-muted)" }}>
          <BarChart3 size={11} />
          {title}
        </p>
        <ResponsiveContainer width="100%" height={Math.max(180, data.length * 34)}>
          <BarChart layout="vertical" data={data} margin={{ left: 8, right: 28, top: 4, bottom: 4 }}>
            <XAxis type="number" tickFormatter={fmt} tick={{ fontSize: 10, fill: axisColor }} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="name" width={126} tick={{ fontSize: 10, fill: axisColor }} axisLine={false} tickLine={false} />
            <Tooltip formatter={(v: number) => fmt(v)} contentStyle={tooltipStyle} cursor={{ fill: "rgba(34,211,238,0.04)" }} />
            <Bar dataKey="value" radius={[0, 6, 6, 0]}>
              {data.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </motion.div>
    );
  }

  // Vertical bar
  const data = labels.map((name, i) => {
    const entry: Record<string, unknown> = { name };
    datasets.forEach((ds) => { entry[ds.label] = ds.data[i] ?? 0; });
    return entry;
  });
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.15 }}
      className="px-5 py-5"
      style={{ borderTop: "1px solid var(--answer-divider)" }}
    >
      <p className="text-xs font-semibold mb-4 flex items-center gap-1.5" style={{ color: "var(--text-muted)" }}>
        <BarChart3 size={11} />
        {title}
      </p>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data} margin={{ left: 8, right: 8, top: 4, bottom: 4 }}>
          <XAxis dataKey="name" tick={{ fontSize: 10, fill: axisColor }} axisLine={false} tickLine={false} />
          <YAxis tickFormatter={fmt} tick={{ fontSize: 10, fill: axisColor }} axisLine={false} tickLine={false} />
          <Tooltip formatter={(v: number) => fmt(v)} contentStyle={tooltipStyle} cursor={{ fill: "rgba(34,211,238,0.04)" }} />
          {datasets.length > 1 && <Legend wrapperStyle={{ fontSize: 10, color: "var(--text-secondary)" }} />}
          {datasets.map((ds, i) => (
            <Bar key={ds.label} dataKey={ds.label} fill={CHART_COLORS[i % CHART_COLORS.length]} radius={[5, 5, 0, 0]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </motion.div>
  );
}

// ── SqlDisclosure ─────────────────────────────────────────────────────────────

function SqlDisclosure({ sql, rowCount }: { sql: string[]; rowCount: number }) {
  const [open, setOpen] = useState(false);
  if (!sql.length) return null;

  return (
    <div style={{ borderTop: "1px solid var(--answer-divider)" }}>
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="w-full px-5 py-2.5 flex items-center justify-between text-[10px] transition-colors hover:opacity-80"
        style={{ color: "var(--text-dim)" }}
      >
        <span className="flex items-center gap-1.5">
          <Code2 size={9} />
          <span className="uppercase tracking-wider font-semibold">SQL</span>
          <span className="opacity-60">· {rowCount} row{rowCount !== 1 ? "s" : ""}</span>
        </span>
        {open ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.4, 0, 0.2, 1] }}
            className="overflow-hidden"
          >
            <pre
              className="mx-5 mb-4 px-4 py-3 rounded-xl text-[10px] leading-relaxed overflow-x-auto"
              style={{
                background: "var(--answer-sql-bg)",
                border: "1px solid var(--panel-border-accent)",
                color: "rgba(34,211,238,0.65)",
                fontFamily: "ui-monospace, SFMono-Regular, monospace",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {sql[0]}
            </pre>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── SourcesDrawer ─────────────────────────────────────────────────────────────

function SourcesDrawer({ citations }: { citations: StructuredAnswer["citations"] }) {
  const [open, setOpen] = useState(false);
  if (citations.length === 0) return null;

  return (
    <div style={{ borderTop: "1px solid var(--answer-divider)" }}>
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="w-full px-5 py-3 flex items-center justify-between text-xs transition-colors hover:opacity-80"
        style={{ color: "var(--text-dim)" }}
      >
        <span className="flex items-center gap-1.5 font-medium">
          <FileText size={10} />
          {citations.length} source{citations.length !== 1 ? "s" : ""}
        </span>
        {open ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.28, ease: [0.4, 0, 0.2, 1] }}
            className="overflow-hidden"
          >
            <div className="px-5 pb-4 space-y-2">
              {citations.map((c, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.05 }}
                  className="chat-source-card"
                >
                  <p className="text-xs font-semibold mb-1" style={{ color: "var(--chat-source-label)" }}>
                    {c.source}
                  </p>
                  <p className="text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                    {c.text.length > 220 ? `${c.text.slice(0, 220)}…` : c.text}
                  </p>
                </motion.div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── FollowUps ─────────────────────────────────────────────────────────────────

function FollowUps({ questions, onSelect }: { questions: string[]; onSelect: (q: string) => void }) {
  if (questions.length === 0) return null;
  return (
    <div className="px-5 py-4 flex flex-wrap gap-2" style={{ borderTop: "1px solid var(--answer-divider)" }}>
      {questions.map((q) => (
        <motion.button
          key={q}
          whileHover={{ scale: 1.03, y: -2 }}
          whileTap={{ scale: 0.95 }}
          transition={{ type: "spring", stiffness: 480, damping: 28 }}
          onClick={() => onSelect(q)}
          className="chat-followup-chip"
          aria-label={`Ask: ${q}`}
        >
          {q}
          <ArrowRight size={10} style={{ opacity: 0.65 }} />
        </motion.button>
      ))}
    </div>
  );
}

// ── CaveatBar ─────────────────────────────────────────────────────────────────

function CaveatBar({ caveats }: { caveats: string[] }) {
  if (caveats.length === 0) return null;
  return (
    <div className="chat-caveat-bar">
      <AlertTriangle size={13} style={{ color: "var(--chat-caveat-icon)", flexShrink: 0, marginTop: 1 }} aria-hidden />
      <div className="space-y-0.5">
        {caveats.map((c, i) => (
          <p key={i} className="text-xs leading-snug" style={{ color: "var(--chat-caveat-text)" }}>
            {c}
          </p>
        ))}
      </div>
    </div>
  );
}

// ── CardShell ─────────────────────────────────────────────────────────────────

interface CardShellProps {
  children: React.ReactNode;
  className?: string;
  chartPayload?: ChartPayload | null;
  sqlUsed?: string[];
  rowsUsed?: number;
}

function CardShell({ children, className, chartPayload, sqlUsed, rowsUsed }: CardShellProps) {
  return (
    <motion.div
      variants={assistantBubbleVariants}
      initial="hidden"
      animate="visible"
      className={`chat-answer-card w-full max-w-2xl ${className ?? ""}`}
    >
      {children}
      {chartPayload && <AnswerChart payload={chartPayload} />}
      {sqlUsed && sqlUsed.length > 0 && (
        <SqlDisclosure sql={sqlUsed} rowCount={rowsUsed ?? 0} />
      )}
    </motion.div>
  );
}

interface CardExtraProps {
  answer: StructuredAnswer;
  onFollowup: (q: string) => void;
}

// ── MetricAnswer ──────────────────────────────────────────────────────────────

function MetricAnswer({ answer, onFollowup }: CardExtraProps) {
  const bullets = answer.highlights.slice(0, 4);
  return (
    <CardShell chartPayload={answer.chart_payload} sqlUsed={answer.sql_used} rowsUsed={answer.rows_used}>
      {/* Card header */}
      <div className="px-6 py-4">
        <p className="text-xs font-semibold uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>
          Result
        </p>
        <h3 className="text-sm font-semibold leading-snug" style={{ color: "var(--text-primary)" }}>
          {answer.title}
        </h3>
      </div>

      <Divider />

      {/* Primary metric hero */}
      {answer.primary_value && (
        <div
          className="px-6 py-6 relative overflow-hidden"
          style={{ background: "var(--chat-metric-bg)" }}
        >
          {/* Subtle caustic glow behind number */}
          <div
            className="absolute inset-0 pointer-events-none"
            style={{
              background: "radial-gradient(ellipse 60% 80% at 50% 100%, var(--chat-card-glow) 0%, transparent 70%)",
            }}
          />
          <motion.p
            initial={{ opacity: 0, scale: 0.88, y: 6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ delay: 0.08, duration: 0.45, ease: [0.34, 1.1, 0.64, 1] }}
            className="chat-metric-hero relative z-10"
          >
            {answer.primary_value}
          </motion.p>
          {answer.summary && (
            <p className="text-sm mt-2 leading-relaxed relative z-10" style={{ color: "var(--text-secondary)" }}>
              {answer.summary}
            </p>
          )}
        </div>
      )}

      {/* Highlight bullets */}
      {bullets.length > 0 && (
        <>
          <Divider />
          <motion.div
            variants={staggerContainer}
            initial="hidden"
            animate="visible"
            className="px-6 py-4 space-y-2.5"
          >
            {bullets.map((h, i) => (
              <motion.div key={i} variants={staggerChild} className="flex items-baseline gap-2.5 text-sm">
                <span
                  className="w-1.5 h-1.5 rounded-full shrink-0 mt-[5px]"
                  style={{ background: "rgba(34,211,238,0.70)" }}
                />
                <span style={{ color: "var(--text-muted)" }}>{h.label}:</span>
                <span className="font-semibold" style={{ color: "var(--text-primary)" }}>{h.value}</span>
              </motion.div>
            ))}
          </motion.div>
        </>
      )}

      <CaveatBar caveats={answer.caveats} />
      <SourcesDrawer citations={answer.citations} />
      <FollowUps questions={answer.suggested_followups} onSelect={onFollowup} />
    </CardShell>
  );
}

// ── SummaryAnswer ─────────────────────────────────────────────────────────────

function SummaryAnswer({ answer, onFollowup }: CardExtraProps) {
  return (
    <CardShell chartPayload={answer.chart_payload} sqlUsed={answer.sql_used} rowsUsed={answer.rows_used}>
      <div className="px-6 py-4">
        <p className="text-xs font-semibold uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>
          Summary
        </p>
        <h3 className="text-sm font-semibold leading-snug" style={{ color: "var(--text-primary)" }}>
          {answer.title}
        </h3>
      </div>

      <Divider />

      <div className="px-6 py-5">
        <p className="text-sm leading-[1.75] whitespace-pre-wrap" style={{ color: "var(--text-secondary)" }}>
          {answer.summary}
        </p>
      </div>

      {answer.highlights.length > 0 && (
        <>
          <Divider />
          <motion.div
            variants={staggerContainer}
            initial="hidden"
            animate="visible"
            className="px-6 py-4 grid grid-cols-2 gap-3"
          >
            {answer.highlights.slice(0, 4).map((h, i) => (
              <motion.div
                key={i}
                variants={staggerChild}
                className="rounded-xl px-3.5 py-3 space-y-0.5"
                style={{ background: "var(--chat-cmp-card-bg)", border: "1px solid var(--chat-cmp-card-border)" }}
              >
                <p className="text-[11px] font-medium" style={{ color: "var(--text-muted)" }}>{h.label}</p>
                <p className="text-sm font-bold tabular" style={{ color: "var(--text-primary)" }}>{h.value}</p>
              </motion.div>
            ))}
          </motion.div>
        </>
      )}

      <CaveatBar caveats={answer.caveats} />
      <SourcesDrawer citations={answer.citations} />
      <FollowUps questions={answer.suggested_followups} onSelect={onFollowup} />
    </CardShell>
  );
}

// ── RankedListAnswer ──────────────────────────────────────────────────────────

function RankedListAnswer({ answer, onFollowup }: CardExtraProps) {
  const section = answer.sections.find((s) => s.type === "table" && s.rows && s.columns);

  type RowItem = { label: string; value: string | null };

  const rows: RowItem[] = (() => {
    if (section && section.rows && section.columns) {
      const cols = section.columns as string[];
      const raw = (section.rows as Record<string, unknown>[]).slice(0, 10);
      const valueCol = cols.find((c) => c.includes("amount") || c.includes("total") || c.includes("value"));
      return raw.map((row) => ({
        label: String(row[cols[0]] ?? "—"),
        value: valueCol ? String(row[valueCol] ?? "") : null,
      }));
    }
    return answer.highlights.map((h) => ({ label: h.label, value: h.value }));
  })();

  // Find max for bar scaling
  const numericValues = rows.map((r) => {
    if (!r.value) return 0;
    const n = parseFloat(r.value.replace(/[^0-9.-]/g, ""));
    return isNaN(n) ? 0 : Math.abs(n);
  });
  const maxVal = Math.max(...numericValues, 1);

  const totalRows = section?.rows ? (section.rows as unknown[]).length : answer.highlights.length;

  return (
    <CardShell chartPayload={answer.chart_payload} sqlUsed={answer.sql_used} rowsUsed={answer.rows_used}>
      <div className="px-6 py-4">
        <p className="text-xs font-semibold uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>
          Ranking
        </p>
        <h3 className="text-sm font-semibold leading-snug" style={{ color: "var(--text-primary)" }}>
          {answer.title}
        </h3>
        {answer.summary && (
          <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>{answer.summary}</p>
        )}
      </div>

      <Divider />

      <motion.div
        variants={staggerContainer}
        initial="hidden"
        animate="visible"
        className="px-6 py-4 space-y-3"
      >
        {rows.map((row, i) => {
          const barPct = maxVal > 0 && numericValues[i] > 0 ? (numericValues[i] / maxVal) * 100 : 0;
          const isTop = i === 0;
          return (
            <motion.div key={i} variants={staggerChild} className="space-y-1.5">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3 min-w-0">
                  <span
                    className="w-5 text-xs font-bold text-right shrink-0 tabular"
                    style={{ color: isTop ? "rgba(34,211,238,0.80)" : "var(--chat-rank-num)" }}
                  >
                    {i + 1}
                  </span>
                  <span className="text-sm truncate" style={{ color: "var(--text-secondary)" }}>{row.label}</span>
                </div>
                {row.value && (
                  <span
                    className="text-sm font-bold tabular shrink-0"
                    style={{ color: isTop ? "var(--text-primary)" : "var(--text-muted)" }}
                  >
                    {row.value}
                  </span>
                )}
              </div>
              {barPct > 0 && (
                <div className="pl-8">
                  <div className="chat-rank-track">
                    <div
                      className={`chat-rank-fill ${isTop ? "chat-rank-fill-top" : ""}`}
                      style={{ width: `${barPct}%` }}
                    />
                  </div>
                </div>
              )}
            </motion.div>
          );
        })}
      </motion.div>

      {totalRows > 10 && (
        <p className="px-6 pb-3 text-xs" style={{ color: "var(--text-dim)" }}>
          Showing top 10 of {totalRows}
        </p>
      )}

      <CaveatBar caveats={answer.caveats} />
      <SourcesDrawer citations={answer.citations} />
      <FollowUps questions={answer.suggested_followups} onSelect={onFollowup} />
    </CardShell>
  );
}

// ── TableAnswer ───────────────────────────────────────────────────────────────

function TableAnswer({ answer, onFollowup }: CardExtraProps) {
  const section = answer.sections.find((s) => s.type === "table" && s.rows && s.columns);

  return (
    <CardShell chartPayload={answer.chart_payload} sqlUsed={answer.sql_used} rowsUsed={answer.rows_used}>
      <div className="px-6 py-4">
        <p className="text-xs font-semibold uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>
          Table
        </p>
        <h3 className="text-sm font-semibold leading-snug" style={{ color: "var(--text-primary)" }}>
          {answer.title}
        </h3>
        {answer.summary && (
          <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>{answer.summary}</p>
        )}
      </div>

      <Divider />

      {section && section.rows && section.columns ? (
        <div className="overflow-x-auto">
          <table className="chat-glass-table" aria-label={answer.title}>
            <thead>
              <tr>
                {(section.columns as string[]).map((col) => (
                  <th key={col}>{friendlyLabel(col)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(section.rows as Record<string, unknown>[]).slice(0, 15).map((row, i) => (
                <motion.tr
                  key={i}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: i * 0.025 }}
                >
                  {(section.columns as string[]).map((col) => (
                    <td key={col}>
                      {row[col] != null ? String(row[col]) : "—"}
                    </td>
                  ))}
                </motion.tr>
              ))}
            </tbody>
          </table>
          {(section.rows as unknown[]).length > 15 && (
            <p
              className="px-4 py-2.5 text-xs"
              style={{ borderTop: "1px solid var(--chat-table-border)", color: "var(--text-dim)" }}
            >
              Showing 15 of {(section.rows as unknown[]).length} rows
            </p>
          )}
        </div>
      ) : (
        <div className="px-6 py-5">
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>{answer.summary}</p>
        </div>
      )}

      <CaveatBar caveats={answer.caveats} />
      <SourcesDrawer citations={answer.citations} />
      <FollowUps questions={answer.suggested_followups} onSelect={onFollowup} />
    </CardShell>
  );
}

// ── ComparisonAnswer ──────────────────────────────────────────────────────────

function DeltaBadge({ value }: { value: string }) {
  const num = parseFloat(value.replace(/[^0-9.-]/g, ""));
  if (isNaN(num)) return <span className="chat-delta-neu">{value}</span>;
  if (num > 0) return (
    <span className="inline-flex items-center gap-0.5 chat-delta-pos font-semibold text-xs">
      <TrendingUp size={11} aria-hidden />
      {value}
    </span>
  );
  if (num < 0) return (
    <span className="inline-flex items-center gap-0.5 chat-delta-neg font-semibold text-xs">
      <TrendingDown size={11} aria-hidden />
      {value}
    </span>
  );
  return (
    <span className="inline-flex items-center gap-0.5 chat-delta-neu font-semibold text-xs">
      <Minus size={11} aria-hidden />
      {value}
    </span>
  );
}

function ComparisonAnswer({ answer, onFollowup }: CardExtraProps) {
  // Pair up highlights into before/after columns
  const highlights = answer.highlights.slice(0, 6);
  const isDelta = (label: string) =>
    label.toLowerCase().includes("change") || label.toLowerCase().includes("delta") || label.toLowerCase().includes("diff");

  return (
    <CardShell chartPayload={answer.chart_payload} sqlUsed={answer.sql_used} rowsUsed={answer.rows_used}>
      <div className="px-6 py-4">
        <p className="text-xs font-semibold uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>
          Comparison
        </p>
        <h3 className="text-sm font-semibold leading-snug" style={{ color: "var(--text-primary)" }}>
          {answer.title}
        </h3>
      </div>

      <Divider />

      {highlights.length > 0 && (
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          animate="visible"
          className="px-6 py-5 grid grid-cols-2 gap-3"
        >
          {highlights.map((h, i) => (
            <motion.div key={i} variants={staggerChild} className="chat-cmp-cell">
              <p className="text-[11px] font-medium mb-1" style={{ color: "var(--text-muted)" }}>{h.label}</p>
              {isDelta(h.label)
                ? <DeltaBadge value={h.value} />
                : <p className="text-base font-bold tabular" style={{ color: "var(--text-primary)" }}>{h.value}</p>
              }
            </motion.div>
          ))}
        </motion.div>
      )}

      {answer.summary && (
        <>
          <Divider />
          <div className="px-6 py-5">
            <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>{answer.summary}</p>
          </div>
        </>
      )}

      <CaveatBar caveats={answer.caveats} />
      <SourcesDrawer citations={answer.citations} />
      <FollowUps questions={answer.suggested_followups} onSelect={onFollowup} />
    </CardShell>
  );
}

// ── NoDataAnswer ──────────────────────────────────────────────────────────────

function NoDataAnswer({ answer, onFollowup }: CardExtraProps) {
  return (
    <CardShell>
      <div
        className="px-6 py-10 text-center"
        style={{ background: "var(--chat-empty-bg)" }}
      >
        <motion.div
          animate={{ y: [0, -6, 0] }}
          transition={{ duration: 3.5, ease: "easeInOut", repeat: Infinity }}
          className="inline-flex items-center justify-center w-14 h-14 rounded-full mb-5"
          style={{
            background: "rgba(34,211,238,0.08)",
            border: "1px solid var(--chat-empty-border)",
          }}
          aria-hidden
        >
          <Search size={22} style={{ color: "rgba(34,211,238,0.55)" }} />
        </motion.div>
        <h3 className="text-sm font-semibold mb-2" style={{ color: "var(--text-primary)" }}>
          {answer.title}
        </h3>
        <p className="text-sm leading-relaxed max-w-xs mx-auto" style={{ color: "var(--text-secondary)" }}>
          {answer.summary || "No data found. Try uploading relevant statements first."}
        </p>
      </div>
      {answer.suggested_followups.length > 0 && (
        <>
          <Divider />
          <FollowUps questions={answer.suggested_followups} onSelect={onFollowup} />
        </>
      )}
    </CardShell>
  );
}

// ── Router ────────────────────────────────────────────────────────────────────

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
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
    <div className="flex flex-col items-start gap-1.5 w-full">
      {card}
      <DebugPanel answer={answer} />
      {timestamp && (
        <span className="text-[10px] ml-1 opacity-45" style={{ color: "var(--text-dim)" }}>
          {formatTime(timestamp)}
        </span>
      )}
    </div>
  );
}
