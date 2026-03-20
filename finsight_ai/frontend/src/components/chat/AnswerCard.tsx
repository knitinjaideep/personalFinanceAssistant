/**
 * AnswerCard — premium answer rendering for the chat interface.
 *
 * 5 card types:
 *   numeric    → MetricAnswer    (big number + context)
 *   table      → TableAnswer or RankedListAnswer
 *   prose      → SummaryAnswer
 *   comparison → ComparisonAnswer
 *   no_data    → NoDataAnswer
 */

import { useState } from "react";
import { ChevronDown, ChevronUp, FileText, ArrowRight } from "lucide-react";
import { clsx } from "clsx";
import { motion, AnimatePresence } from "framer-motion";
import { assistantBubbleVariants, staggerContainer, staggerChild } from "../../design/motion";
import type { StructuredAnswer } from "../../types";

// ── Column label map ─────────────────────────────────────────────────────────

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

// ── Shared subcomponents ─────────────────────────────────────────────────────

function SourcesDrawer({ citations }: { citations: StructuredAnswer["citations"] }) {
  const [open, setOpen] = useState(false);
  if (citations.length === 0) return null;

  return (
    <div className="border-t border-ocean-50/80">
      <button
        onClick={() => setOpen(!open)}
        className="w-full px-5 py-2.5 flex items-center justify-between text-xs text-ocean/30 hover:text-ocean/50 transition-colors"
      >
        <span className="flex items-center gap-1.5">
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
            transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
            className="overflow-hidden"
          >
            <div className="px-5 pb-4 space-y-2">
              {citations.map((c, i) => (
                <div
                  key={i}
                  className="p-3 rounded-2xl text-xs"
                  style={{
                    background: "rgba(240,249,252,0.7)",
                    border: "1px solid rgba(205,237,246,0.6)",
                  }}
                >
                  <p className="font-semibold text-ocean">{c.source}</p>
                  <p className="text-slate/50 mt-1 leading-relaxed">
                    {c.text.length > 200 ? `${c.text.slice(0, 200)}…` : c.text}
                  </p>
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
    <div className="px-5 py-3.5 border-t border-ocean-50/80 flex flex-wrap gap-2">
      {questions.map((q) => (
        <motion.button
          key={q}
          whileHover={{ scale: 1.03, y: -1 }}
          whileTap={{ scale: 0.97 }}
          onClick={() => onSelect(q)}
          className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-ocean/60 rounded-full transition-colors duration-150"
          style={{
            background: "rgba(240,249,252,0.8)",
            border: "1px solid rgba(205,237,246,0.7)",
          }}
        >
          {q}
          <ArrowRight size={9} />
        </motion.button>
      ))}
    </div>
  );
}

function CaveatBar({ caveats }: { caveats: string[] }) {
  if (caveats.length === 0) return null;
  return (
    <div className="px-5 py-2.5 border-t border-highlight/20" style={{ background: "rgba(255,209,102,0.08)" }}>
      {caveats.map((c, i) => (
        <p key={i} className="text-xs text-yellow-700/70">⚠ {c}</p>
      ))}
    </div>
  );
}

function CardShell({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <motion.div
      variants={assistantBubbleVariants}
      initial="hidden"
      animate="visible"
      className={clsx("max-w-2xl rounded-3xl overflow-hidden", className)}
      style={{
        background: "rgba(255,255,255,0.90)",
        backdropFilter: "blur(14px)",
        WebkitBackdropFilter: "blur(14px)",
        border: "1px solid rgba(205,237,246,0.70)",
        boxShadow: "0 6px 32px rgba(11,60,93,0.10), inset 0 1px 0 rgba(255,255,255,0.5)",
      }}
    >
      {children}
    </motion.div>
  );
}

// ── MetricAnswer ─────────────────────────────────────────────────────────────

function MetricAnswer({ answer, onFollowup }: { answer: StructuredAnswer; onFollowup: (q: string) => void }) {
  const bullets = answer.highlights.slice(0, 4);
  return (
    <CardShell>
      <div className="px-5 py-4 border-b border-ocean-50/70">
        <h3 className="text-sm font-semibold text-ocean-deep">{answer.title}</h3>
      </div>

      {answer.primary_value && (
        <div
          className="px-5 py-5 border-b border-ocean-50/60"
          style={{ background: "linear-gradient(135deg, rgba(11,60,93,0.04), rgba(95,168,211,0.04))" }}
        >
          <motion.p
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.1, duration: 0.4, ease: [0.34, 1.1, 0.64, 1] }}
            className="text-3xl font-bold text-ocean-deep tracking-tight tabular"
          >
            {answer.primary_value}
          </motion.p>
          {answer.summary && (
            <p className="text-sm text-slate/60 mt-1.5 leading-relaxed">{answer.summary}</p>
          )}
        </div>
      )}

      {bullets.length > 0 && (
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          animate="visible"
          className="px-5 py-4 space-y-2 border-b border-ocean-50/60"
        >
          {bullets.map((h, i) => (
            <motion.div key={i} variants={staggerChild} className="flex items-baseline gap-2 text-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-ocean-sea shrink-0 mt-[5px]" />
              <span className="text-slate/50">{h.label}:</span>
              <span className="font-semibold text-ocean-deep">{h.value}</span>
            </motion.div>
          ))}
        </motion.div>
      )}

      <CaveatBar caveats={answer.caveats} />
      <SourcesDrawer citations={answer.citations} />
      <FollowUps questions={answer.suggested_followups} onSelect={onFollowup} />
    </CardShell>
  );
}

// ── SummaryAnswer ─────────────────────────────────────────────────────────────

function SummaryAnswer({ answer, onFollowup }: { answer: StructuredAnswer; onFollowup: (q: string) => void }) {
  return (
    <CardShell>
      <div className="px-5 py-4 border-b border-ocean-50/70">
        <h3 className="text-sm font-semibold text-ocean-deep">{answer.title}</h3>
      </div>

      <div className="px-5 py-4">
        <p className="text-sm text-slate/80 leading-relaxed whitespace-pre-wrap">{answer.summary}</p>
      </div>

      {answer.highlights.length > 0 && (
        <div className="px-5 pb-4 pt-3 space-y-1.5 border-t border-ocean-50/60">
          {answer.highlights.slice(0, 4).map((h, i) => (
            <div key={i} className="flex items-baseline gap-2 text-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-coral shrink-0 mt-[5px]" />
              <span className="text-slate/50">{h.label}:</span>
              <span className="font-semibold text-slate">{h.value}</span>
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

// ── RankedListAnswer ──────────────────────────────────────────────────────────

function RankedListAnswer({ answer, onFollowup }: { answer: StructuredAnswer; onFollowup: (q: string) => void }) {
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
          <motion.div
            key={i}
            variants={staggerChild}
            className="flex items-center justify-between py-2.5 border-b border-ocean-50/50 last:border-0"
          >
            <div className="flex items-center gap-3">
              <span className="w-5 text-xs text-ocean/25 font-bold text-right shrink-0">{i + 1}</span>
              <span className="text-sm text-slate/80">{label}</span>
            </div>
            {value && <span className="text-sm font-bold text-ocean-deep">{value}</span>}
          </motion.div>
        );
      });
    }
    return answer.highlights.map((h, i) => (
      <motion.div
        key={i}
        variants={staggerChild}
        className="flex items-center justify-between py-2.5 border-b border-ocean-50/50 last:border-0"
      >
        <div className="flex items-center gap-3">
          <span className="w-5 text-xs text-ocean/25 font-bold text-right shrink-0">{i + 1}</span>
          <span className="text-sm text-slate/80">{h.label}</span>
        </div>
        <span className="text-sm font-bold text-ocean-deep">{h.value}</span>
      </motion.div>
    ));
  };

  const totalRows = section?.rows ? (section.rows as unknown[]).length : answer.highlights.length;

  return (
    <CardShell>
      <div className="px-5 py-4 border-b border-ocean-50/70">
        <h3 className="text-sm font-semibold text-ocean-deep">{answer.title}</h3>
        {answer.summary && <p className="text-xs text-slate/45 mt-1">{answer.summary}</p>}
      </div>

      <motion.div
        variants={staggerContainer}
        initial="hidden"
        animate="visible"
        className="px-5 py-3"
      >
        {renderRows()}
      </motion.div>

      {totalRows > 10 && (
        <p className="px-5 pb-3 text-xs text-ocean/35">Showing top 10 of {totalRows}</p>
      )}

      <CaveatBar caveats={answer.caveats} />
      <SourcesDrawer citations={answer.citations} />
      <FollowUps questions={answer.suggested_followups} onSelect={onFollowup} />
    </CardShell>
  );
}

// ── TableAnswer ───────────────────────────────────────────────────────────────

function TableAnswer({ answer, onFollowup }: { answer: StructuredAnswer; onFollowup: (q: string) => void }) {
  const section = answer.sections.find((s) => s.type === "table" && s.rows && s.columns);

  return (
    <CardShell>
      <div className="px-5 py-4 border-b border-ocean-50/70">
        <h3 className="text-sm font-semibold text-ocean-deep">{answer.title}</h3>
        {answer.summary && <p className="text-xs text-slate/45 mt-1">{answer.summary}</p>}
      </div>

      {section && section.rows && section.columns ? (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr
                className="border-b border-ocean-50/80"
                style={{ background: "rgba(240,249,252,0.5)" }}
              >
                {(section.columns as string[]).map((col) => (
                  <th
                    key={col}
                    className="px-4 py-2.5 text-left font-semibold text-ocean/40 uppercase tracking-wide text-[10px]"
                  >
                    {friendlyLabel(col)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(section.rows as Record<string, unknown>[]).slice(0, 15).map((row, i) => (
                <motion.tr
                  key={i}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: i * 0.03 }}
                  className="border-b border-ocean-50/40 hover:bg-ocean-50/30 transition-colors"
                >
                  {(section.columns as string[]).map((col) => (
                    <td key={col} className="px-4 py-2.5 text-slate/75">
                      {row[col] != null ? String(row[col]) : "—"}
                    </td>
                  ))}
                </motion.tr>
              ))}
            </tbody>
          </table>
          {(section.rows as unknown[]).length > 15 && (
            <p className="px-4 py-2 text-xs text-ocean/35 border-t border-ocean-50/50">
              Showing 15 of {(section.rows as unknown[]).length} rows
            </p>
          )}
        </div>
      ) : (
        <div className="px-5 py-4">
          <p className="text-sm text-slate/60">{answer.summary}</p>
        </div>
      )}

      <CaveatBar caveats={answer.caveats} />
      <SourcesDrawer citations={answer.citations} />
      <FollowUps questions={answer.suggested_followups} onSelect={onFollowup} />
    </CardShell>
  );
}

// ── ComparisonAnswer ──────────────────────────────────────────────────────────

function ComparisonAnswer({ answer, onFollowup }: { answer: StructuredAnswer; onFollowup: (q: string) => void }) {
  return (
    <CardShell>
      <div className="px-5 py-4 border-b border-ocean-50/70">
        <h3 className="text-sm font-semibold text-ocean-deep">{answer.title}</h3>
      </div>

      {answer.highlights.length > 0 && (
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          animate="visible"
          className="px-5 py-4 grid grid-cols-2 gap-4 border-b border-ocean-50/60"
        >
          {answer.highlights.slice(0, 6).map((h, i) => (
            <motion.div key={i} variants={staggerChild} className="space-y-0.5">
              <p className="text-xs text-ocean/38">{h.label}</p>
              <p className="text-base font-bold text-ocean-deep tabular">{h.value}</p>
            </motion.div>
          ))}
        </motion.div>
      )}

      {answer.summary && (
        <div className="px-5 py-4">
          <p className="text-sm text-slate/70 leading-relaxed">{answer.summary}</p>
        </div>
      )}

      <CaveatBar caveats={answer.caveats} />
      <SourcesDrawer citations={answer.citations} />
      <FollowUps questions={answer.suggested_followups} onSelect={onFollowup} />
    </CardShell>
  );
}

// ── NoDataAnswer ──────────────────────────────────────────────────────────────

function NoDataAnswer({ answer, onFollowup }: { answer: StructuredAnswer; onFollowup: (q: string) => void }) {
  return (
    <CardShell>
      <div className="px-5 py-8 text-center">
        <motion.div
          animate={{ y: [0, -5, 0] }}
          transition={{ duration: 3, ease: "easeInOut", repeat: Infinity }}
          className="text-3xl mb-4"
        >
          🔍
        </motion.div>
        <h3 className="text-sm font-semibold text-ocean-deep mb-1.5">{answer.title}</h3>
        <p className="text-sm text-slate/50 leading-relaxed max-w-xs mx-auto">
          {answer.summary || "No data found. Try uploading relevant statements first."}
        </p>
      </div>
      <FollowUps questions={answer.suggested_followups} onSelect={onFollowup} />
    </CardShell>
  );
}

// ── Router ────────────────────────────────────────────────────────────────────

export interface AnswerCardProps {
  answer: StructuredAnswer;
  onFollowup: (q: string) => void;
}

export function AnswerCard({ answer, onFollowup }: AnswerCardProps) {
  if (answer.answer_type === "no_data")   return <NoDataAnswer   answer={answer} onFollowup={onFollowup} />;
  if (answer.answer_type === "numeric")   return <MetricAnswer   answer={answer} onFollowup={onFollowup} />;
  if (answer.answer_type === "comparison") return <ComparisonAnswer answer={answer} onFollowup={onFollowup} />;
  if (answer.answer_type === "table") {
    const section = answer.sections.find((s) => s.type === "table" && s.columns && s.rows);
    const colCount = (section?.columns as string[] | undefined)?.length ?? 0;
    if (colCount <= 3) return <RankedListAnswer answer={answer} onFollowup={onFollowup} />;
    return <TableAnswer answer={answer} onFollowup={onFollowup} />;
  }
  return <SummaryAnswer answer={answer} onFollowup={onFollowup} />;
}
