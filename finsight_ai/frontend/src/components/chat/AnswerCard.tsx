/**
 * AnswerCard — polished answer rendering for the chat interface.
 *
 * Uses 5 card types that map to answer_type from the backend:
 *   numeric    → MetricAnswer    (big number + context)
 *   table      → TableAnswer or RankedListAnswer depending on column count
 *   prose      → SummaryAnswer   (narrative + bullets)
 *   comparison → ComparisonAnswer (side-by-side)
 *   no_data    → NoDataAnswer    (soft empty state)
 *
 * Design principles:
 * - No SQL labels / internal jargon shown to user
 * - Sources collapsed by default (subtle)
 * - Follow-ups as ghost pills, not chip spam
 * - Confidence / path badge hidden (not useful to end user)
 */

import { useState } from "react";
import { ChevronDown, ChevronUp, FileText, ArrowRight } from "lucide-react";
import { clsx } from "clsx";
import type { StructuredAnswer } from "../../types";

// ── Human-friendly column label map ─────────────────────────────────────────

const FRIENDLY_LABELS: Record<string, string> = {
  fee_category: "Category",
  institution: "Institution",
  fee_count: "Count",
  total_amount: "Amount",
  transaction_type: "Type",
  merchant_name: "Merchant",
  transaction_date: "Date",
  description: "Description",
  amount: "Amount",
  symbol: "Symbol",
  market_value: "Value",
  percent_of_portfolio: "% Portfolio",
  category: "Category",
  count: "Count",
  total: "Total",
  account_type: "Account",
  institution_type: "Institution",
};

function friendlyLabel(col: string): string {
  return (
    FRIENDLY_LABELS[col] ||
    col.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

// ── Shared subcomponents ─────────────────────────────────────────────────────

function SourcesDrawer({ citations }: { citations: StructuredAnswer["citations"] }) {
  const [open, setOpen] = useState(false);
  if (citations.length === 0) return null;

  return (
    <div className="border-t border-ocean-50">
      <button
        onClick={() => setOpen(!open)}
        className="w-full px-5 py-2.5 flex items-center justify-between text-xs text-ocean-DEFAULT/40 hover:text-ocean-DEFAULT/60 transition-colors"
      >
        <span className="flex items-center gap-1.5">
          <FileText size={11} />
          {citations.length} source{citations.length !== 1 ? "s" : ""}
        </span>
        {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>
      {open && (
        <div className="px-5 pb-4 space-y-2">
          {citations.map((c, i) => (
            <div key={i} className="p-3 bg-ocean-50/60 rounded-xl text-xs border border-ocean-100">
              <p className="font-semibold text-ocean-DEFAULT">{c.source}</p>
              <p className="text-slate/50 mt-1 leading-relaxed">
                {c.text.length > 200 ? `${c.text.slice(0, 200)}…` : c.text}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function FollowUps({ questions, onSelect }: { questions: string[]; onSelect: (q: string) => void }) {
  if (questions.length === 0) return null;
  return (
    <div className="px-5 py-3.5 border-t border-ocean-50 flex flex-wrap gap-2">
      {questions.map((q) => (
        <button
          key={q}
          onClick={() => onSelect(q)}
          className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-ocean-DEFAULT/60 bg-ocean-50 border border-ocean-100 rounded-full hover:bg-ocean hover:text-white hover:border-ocean transition-all duration-150"
        >
          {q}
          <ArrowRight size={10} />
        </button>
      ))}
    </div>
  );
}

function CaveatBar({ caveats }: { caveats: string[] }) {
  if (caveats.length === 0) return null;
  return (
    <div className="px-5 py-2.5 bg-highlight/10 border-t border-highlight/20">
      {caveats.map((c, i) => (
        <p key={i} className="text-xs text-slate/60">⚠ {c}</p>
      ))}
    </div>
  );
}

function CardShell({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={clsx("max-w-2xl bg-white border border-ocean-100 rounded-2xl overflow-hidden shadow-soft", className)}>
      {children}
    </div>
  );
}

// ── MetricAnswer — single number with context ────────────────────────────────

function MetricAnswer({ answer, onFollowup }: { answer: StructuredAnswer; onFollowup: (q: string) => void }) {
  const bullets = answer.highlights.slice(0, 4);
  return (
    <CardShell>
      <div className="px-5 py-4 border-b border-ocean-50">
        <h3 className="text-sm font-semibold text-slate">{answer.title}</h3>
      </div>

      {answer.primary_value && (
        <div className="px-5 py-5 bg-gradient-to-br from-ocean-50 to-ocean-aqua/20 border-b border-ocean-100">
          <p className="text-3xl font-bold text-ocean-deep tracking-tight">
            {answer.primary_value}
          </p>
          {answer.summary && (
            <p className="text-sm text-slate/60 mt-1.5 leading-relaxed">{answer.summary}</p>
          )}
        </div>
      )}

      {bullets.length > 0 && (
        <div className="px-5 py-4 space-y-2 border-b border-ocean-50">
          {bullets.map((h, i) => (
            <div key={i} className="flex items-baseline gap-2 text-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-ocean-sea shrink-0 mt-[5px]" />
              <span className="text-slate/55">{h.label}:</span>
              <span className="font-medium text-slate">{h.value}</span>
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

// ── SummaryAnswer — prose with optional bullets ──────────────────────────────

function SummaryAnswer({ answer, onFollowup }: { answer: StructuredAnswer; onFollowup: (q: string) => void }) {
  return (
    <CardShell>
      <div className="px-5 py-4 border-b border-ocean-50">
        <h3 className="text-sm font-semibold text-slate">{answer.title}</h3>
      </div>

      <div className="px-5 py-4">
        <p className="text-sm text-slate/80 leading-relaxed whitespace-pre-wrap">{answer.summary}</p>
      </div>

      {answer.highlights.length > 0 && (
        <div className="px-5 pb-4 space-y-1.5 border-t border-ocean-50 pt-3">
          {answer.highlights.slice(0, 4).map((h, i) => (
            <div key={i} className="flex items-baseline gap-2 text-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-coral shrink-0 mt-[5px]" />
              <span className="text-slate/55">{h.label}:</span>
              <span className="font-medium text-slate">{h.value}</span>
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

// ── RankedListAnswer — numbered list with label + value ──────────────────────

function RankedListAnswer({ answer, onFollowup }: { answer: StructuredAnswer; onFollowup: (q: string) => void }) {
  const section = answer.sections.find((s) => s.type === "table" && s.rows && s.columns);

  const renderRows = () => {
    if (section && section.rows && section.columns) {
      const cols = section.columns as string[];
      const rows = (section.rows as Record<string, unknown>[]).slice(0, 10);
      const valueCol = cols.find((c) =>
        c.includes("amount") || c.includes("total") || c.includes("value")
      );
      return rows.map((row, i) => {
        const label = String(row[cols[0]] ?? "—");
        const value = valueCol ? String(row[valueCol] ?? "") : null;
        return (
          <div key={i} className="flex items-center justify-between py-2.5 border-b border-ocean-50/60 last:border-0">
            <div className="flex items-center gap-3">
              <span className="w-5 text-xs text-ocean-DEFAULT/30 font-medium text-right shrink-0">{i + 1}</span>
              <span className="text-sm text-slate">{label}</span>
            </div>
            {value && <span className="text-sm font-semibold text-slate">{value}</span>}
          </div>
        );
      });
    }
    // Fallback to highlights
    return answer.highlights.map((h, i) => (
      <div key={i} className="flex items-center justify-between py-2.5 border-b border-ocean-50/60 last:border-0">
        <div className="flex items-center gap-3">
          <span className="w-5 text-xs text-ocean-DEFAULT/30 font-medium text-right shrink-0">{i + 1}</span>
          <span className="text-sm text-slate">{h.label}</span>
        </div>
        <span className="text-sm font-semibold text-slate">{h.value}</span>
      </div>
    ));
  };

  const totalRows = section?.rows ? (section.rows as unknown[]).length : answer.highlights.length;

  return (
    <CardShell>
      <div className="px-5 py-4 border-b border-ocean-50">
        <h3 className="text-sm font-semibold text-slate">{answer.title}</h3>
        {answer.summary && <p className="text-xs text-slate/50 mt-1">{answer.summary}</p>}
      </div>

      <div className="px-5 py-3">{renderRows()}</div>

      {totalRows > 10 && (
        <p className="px-5 pb-3 text-xs text-ocean-DEFAULT/40">
          Showing top 10 of {totalRows}
        </p>
      )}

      <CaveatBar caveats={answer.caveats} />
      <SourcesDrawer citations={answer.citations} />
      <FollowUps questions={answer.suggested_followups} onSelect={onFollowup} />
    </CardShell>
  );
}

// ── TableAnswer — full multi-column table ────────────────────────────────────

function TableAnswer({ answer, onFollowup }: { answer: StructuredAnswer; onFollowup: (q: string) => void }) {
  const section = answer.sections.find((s) => s.type === "table" && s.rows && s.columns);

  return (
    <CardShell>
      <div className="px-5 py-4 border-b border-ocean-50">
        <h3 className="text-sm font-semibold text-slate">{answer.title}</h3>
        {answer.summary && <p className="text-xs text-slate/50 mt-1">{answer.summary}</p>}
      </div>

      {section && section.rows && section.columns ? (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-ocean-100 bg-ocean-50/40">
                {(section.columns as string[]).map((col) => (
                  <th key={col} className="px-4 py-2.5 text-left font-semibold text-ocean-DEFAULT/50 uppercase tracking-wide text-[10px]">
                    {friendlyLabel(col)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(section.rows as Record<string, unknown>[]).slice(0, 15).map((row, i) => (
                <tr key={i} className="border-b border-ocean-50/50 hover:bg-ocean-50/30 transition-colors">
                  {(section.columns as string[]).map((col) => (
                    <td key={col} className="px-4 py-2.5 text-slate/80">
                      {row[col] != null ? String(row[col]) : "—"}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {(section.rows as unknown[]).length > 15 && (
            <p className="px-4 py-2 text-xs text-ocean-DEFAULT/40 border-t border-ocean-50">
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

// ── ComparisonAnswer ─────────────────────────────────────────────────────────

function ComparisonAnswer({ answer, onFollowup }: { answer: StructuredAnswer; onFollowup: (q: string) => void }) {
  return (
    <CardShell>
      <div className="px-5 py-4 border-b border-ocean-50">
        <h3 className="text-sm font-semibold text-slate">{answer.title}</h3>
      </div>

      {answer.highlights.length > 0 && (
        <div className="px-5 py-4 grid grid-cols-2 gap-4 border-b border-ocean-50">
          {answer.highlights.slice(0, 6).map((h, i) => (
            <div key={i} className="space-y-0.5">
              <p className="text-xs text-ocean-DEFAULT/40">{h.label}</p>
              <p className="text-base font-bold text-slate">{h.value}</p>
            </div>
          ))}
        </div>
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

// ── NoDataAnswer ─────────────────────────────────────────────────────────────

function NoDataAnswer({ answer, onFollowup }: { answer: StructuredAnswer; onFollowup: (q: string) => void }) {
  return (
    <CardShell>
      <div className="px-5 py-8 text-center">
        <p className="text-2xl mb-3">🔍</p>
        <h3 className="text-sm font-semibold text-slate mb-1.5">{answer.title}</h3>
        <p className="text-sm text-slate/50 leading-relaxed max-w-xs mx-auto">
          {answer.summary || "No data found. Try uploading relevant statements first."}
        </p>
      </div>
      <FollowUps questions={answer.suggested_followups} onSelect={onFollowup} />
    </CardShell>
  );
}

// ── Router ───────────────────────────────────────────────────────────────────

export interface AnswerCardProps {
  answer: StructuredAnswer;
  onFollowup: (q: string) => void;
}

export function AnswerCard({ answer, onFollowup }: AnswerCardProps) {
  if (answer.answer_type === "no_data") {
    return <NoDataAnswer answer={answer} onFollowup={onFollowup} />;
  }
  if (answer.answer_type === "numeric") {
    return <MetricAnswer answer={answer} onFollowup={onFollowup} />;
  }
  if (answer.answer_type === "comparison") {
    return <ComparisonAnswer answer={answer} onFollowup={onFollowup} />;
  }
  if (answer.answer_type === "table") {
    const section = answer.sections.find((s) => s.type === "table" && s.columns && s.rows);
    const colCount = (section?.columns as string[] | undefined)?.length ?? 0;
    if (colCount <= 3) {
      return <RankedListAnswer answer={answer} onFollowup={onFollowup} />;
    }
    return <TableAnswer answer={answer} onFollowup={onFollowup} />;
  }
  return <SummaryAnswer answer={answer} onFollowup={onFollowup} />;
}
