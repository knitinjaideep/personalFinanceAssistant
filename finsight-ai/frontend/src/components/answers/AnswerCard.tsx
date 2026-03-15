/**
 * AnswerCard — top-level dispatcher that renders the correct answer component
 * based on ``answer_type``.
 *
 * Hierarchy:
 *   AnswerCard
 *     ├── NumericAnswerCard     — hero metric card with large value display
 *     ├── TableAnswerCard       — paginated table with highlights header
 *     ├── ComparisonAnswerCard  — bar-chart comparison with winner callout
 *     └── ProseAnswerCard       — polished narrative card (no longer plain text)
 *
 * All variants share:
 *   AnswerCardShell       — white card with border, title band, confidence slot
 *   FallbackBanner        — amber banner when pipeline_stage !== "llm"
 *   ConfidenceBadge       — green/yellow/red confidence pill
 *   CaveatsList           — amber alert callouts
 *   HighlightsBar         — stat chips
 *   SectionsList          — expandable accordion
 *   FollowupPills         — clickable suggestion pills
 *   EvidenceDrawer        — collapsible source panel
 */

import React from "react";
import {
  AlertTriangle,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  Info,
  Search,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { clsx } from "clsx";
import type {
  StructuredAnswer,
  NumericAnswerPayload,
  TableAnswerPayload,
  ComparisonAnswerPayload,
  ProseAnswer,
  NoDataAnswer,
  PartialDataAnswer,
  ComparisonItem,
  AnswerHighlight,
  AnswerSection,
} from "../../types";
import { EvidenceDrawer } from "./EvidenceDrawer";

// ── Shared props passed through from ChatInterface ─────────────────────────────

export interface AnswerCardProps {
  structured: StructuredAnswer;
  /** pipeline_stage from the response_complete payload: 'llm' | 'retrieval_only' | 'safe_error' */
  pipelineStage?: string;
  /** Warning messages from pipeline_meta.warnings */
  warnings?: string[];
  /** Called when the user clicks a follow-up pill. */
  onFollowup?: (q: string) => void;
}

// ── Fallback banner ────────────────────────────────────────────────────────────

function FallbackBanner({
  stage,
  warnings,
}: {
  stage: string;
  warnings: string[];
}) {
  if (stage === "llm") return null;

  const label =
    stage === "retrieval_only"
      ? "Retrieved answer — LLM generation was unavailable"
      : "Safe fallback — limited data available for this question";

  return (
    <div className="flex items-start gap-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 mb-3">
      <AlertTriangle size={14} className="text-amber-500 shrink-0 mt-0.5" />
      <div className="min-w-0">
        <p className="text-xs font-medium text-amber-800">{label}</p>
        {warnings.length > 0 && (
          <ul className="mt-1 space-y-0.5">
            {warnings.map((w, i) => (
              <li key={i} className="text-xs text-amber-700">
                {w}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

// ── Confidence badge ───────────────────────────────────────────────────────────

function ConfidenceBadge({ confidence }: { confidence: number | null }) {
  if (confidence == null) return null;
  const pct = Math.round(confidence * 100);

  const [colorClass, Icon]: [string, React.ElementType] =
    confidence >= 0.8
      ? ["text-green-700 bg-green-50 border-green-200", CheckCircle]
      : confidence >= 0.5
      ? ["text-yellow-700 bg-yellow-50 border-yellow-200", Info]
      : ["text-red-700 bg-red-50 border-red-200", AlertTriangle];

  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded border font-medium shrink-0",
        colorClass
      )}
    >
      <Icon size={11} />
      {pct}%
    </span>
  );
}

// ── Caveats list ───────────────────────────────────────────────────────────────

function CaveatsList({ caveats }: { caveats: string[] }) {
  if (!caveats.length) return null;
  return (
    <ul className="mt-2 space-y-1.5">
      {caveats.map((c, i) => (
        <li
          key={i}
          className="flex items-start gap-1.5 text-xs text-amber-800 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2"
        >
          <AlertTriangle size={12} className="shrink-0 mt-0.5 text-amber-500" />
          {c}
        </li>
      ))}
    </ul>
  );
}

// ── Highlights bar ─────────────────────────────────────────────────────────────

function HighlightsBar({ highlights }: { highlights: AnswerHighlight[] }) {
  if (!highlights.length) return null;
  return (
    <div className="flex flex-wrap gap-2 mt-1 mb-2">
      {highlights.map((h, i) => (
        <div
          key={i}
          className="bg-blue-50 border border-blue-100 rounded-lg px-3 py-2 min-w-[90px]"
        >
          <p className="text-[10px] font-semibold text-blue-500 uppercase tracking-wide truncate">
            {h.label}
          </p>
          <p className="text-sm font-bold text-blue-900 tabular-nums leading-tight mt-0.5">
            {h.value}
          </p>
          {h.trend_label && (
            <p
              className={clsx(
                "text-[10px] mt-0.5 flex items-center gap-0.5",
                h.trend === "up"
                  ? "text-red-500"
                  : h.trend === "down"
                  ? "text-green-600"
                  : "text-gray-400"
              )}
            >
              {h.trend === "up" ? (
                <TrendingUp size={10} />
              ) : h.trend === "down" ? (
                <TrendingDown size={10} />
              ) : null}
              {h.trend_label}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Expandable sections ────────────────────────────────────────────────────────

function SectionsList({ sections }: { sections: AnswerSection[] }) {
  const [expanded, setExpanded] = React.useState<Set<number>>(() => {
    const s = new Set<number>();
    sections.forEach((sec, i) => {
      if (sec.expanded_by_default) s.add(i);
    });
    return s;
  });

  if (!sections.length) return null;

  const toggle = (i: number) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });

  return (
    <div className="mt-3 space-y-1">
      {sections.map((sec, i) => (
        <div key={i} className="border border-gray-100 rounded-lg overflow-hidden">
          <button
            className="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold text-gray-700 hover:bg-gray-50 transition-colors"
            onClick={() => toggle(i)}
          >
            <span>{sec.heading}</span>
            {expanded.has(i) ? (
              <ChevronUp size={13} className="text-gray-400 shrink-0" />
            ) : (
              <ChevronDown size={13} className="text-gray-400 shrink-0" />
            )}
          </button>
          {expanded.has(i) && (
            <p className="px-3 py-2.5 text-xs text-gray-600 leading-relaxed bg-gray-50/60 whitespace-pre-wrap border-t border-gray-100">
              {sec.content}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Follow-up pills ────────────────────────────────────────────────────────────

interface FollowupPillsProps {
  followups: string[];
  onFollowup?: (q: string) => void;
}

function FollowupPills({ followups, onFollowup }: FollowupPillsProps) {
  if (!followups.length || !onFollowup) return null;
  return (
    <div className="mt-3 pt-3 border-t border-gray-100">
      <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5">
        Suggested follow-ups
      </p>
      <div className="flex flex-wrap gap-1.5">
        {followups.map((q, i) => (
          <button
            key={i}
            onClick={() => onFollowup(q)}
            className="text-xs px-2.5 py-1 rounded-full border border-blue-200 text-blue-600 hover:bg-blue-50 hover:border-blue-400 transition-colors"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Card shell (shared chrome for all answer types) ────────────────────────────

interface AnswerCardShellProps {
  title: string | null | undefined;
  subtitle?: string | null;
  confidence: number | null | undefined;
  pipelineStage?: string;
  warnings?: string[];
  children: React.ReactNode;
  /** Accent color for the top border strip. Defaults to blue. */
  accentColor?: "blue" | "green" | "amber" | "purple";
}

function AnswerCardShell({
  title,
  subtitle,
  confidence,
  pipelineStage = "llm",
  warnings = [],
  children,
  accentColor = "blue",
}: AnswerCardShellProps) {
  const accentBorder: Record<string, string> = {
    blue: "border-t-blue-500",
    green: "border-t-green-500",
    amber: "border-t-amber-400",
    purple: "border-t-purple-500",
  };

  return (
    <div
      className={clsx(
        "bg-white border border-gray-200 rounded-xl overflow-hidden border-t-2",
        accentBorder[accentColor]
      )}
    >
      {/* Fallback banner — rendered inside the card, above all content */}
      {pipelineStage !== "llm" && (
        <div className="px-4 pt-3">
          <FallbackBanner stage={pipelineStage} warnings={warnings} />
        </div>
      )}

      {/* Card header */}
      {(title || confidence != null) && (
        <div className="flex items-start justify-between gap-3 px-4 pt-4 pb-2">
          <div className="min-w-0">
            {title && (
              <h3 className="text-sm font-semibold text-gray-900 leading-snug">
                {title}
              </h3>
            )}
            {subtitle && (
              <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">
                {subtitle}
              </p>
            )}
          </div>
          <ConfidenceBadge confidence={confidence ?? null} />
        </div>
      )}

      {/* Card body */}
      <div className="px-4 pb-4">{children}</div>
    </div>
  );
}

// ── Numeric answer ─────────────────────────────────────────────────────────────

interface NumericAnswerCardProps {
  answer: NumericAnswerPayload;
  pipelineStage?: string;
  warnings?: string[];
  onFollowup?: (q: string) => void;
}

function NumericAnswerCard({
  answer,
  pipelineStage,
  warnings,
  onFollowup,
}: NumericAnswerCardProps) {
  return (
    <AnswerCardShell
      title={answer.title}
      subtitle={answer.period ?? undefined}
      confidence={answer.confidence}
      pipelineStage={pipelineStage}
      warnings={warnings}
      accentColor="blue"
    >
      {/* Label row */}
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mt-1">
        {answer.label}
      </p>

      {/* Hero metric */}
      <div className="flex items-baseline gap-2 mt-1 mb-2">
        <span className="text-4xl font-bold text-gray-900 tabular-nums leading-none">
          {answer.value}
        </span>
        {answer.unit && answer.unit !== "USD" && (
          <span className="text-base text-gray-500 font-medium">{answer.unit}</span>
        )}
      </div>

      {(answer.institution || answer.account) && (
        <p className="text-xs text-gray-400 mb-2">
          {[answer.institution, answer.account].filter(Boolean).join(" · ")}
        </p>
      )}

      <HighlightsBar highlights={answer.highlights ?? []} />

      {answer.summary_text && (
        <p className="text-sm text-gray-600 leading-relaxed border-t border-gray-100 pt-3 mt-1">
          {answer.summary_text}
        </p>
      )}

      <SectionsList sections={answer.sections ?? []} />
      <CaveatsList caveats={answer.caveats} />
      <EvidenceDrawer evidence={answer.evidence} />
      <FollowupPills followups={answer.suggested_followups ?? []} onFollowup={onFollowup} />
    </AnswerCardShell>
  );
}

// ── Table answer ───────────────────────────────────────────────────────────────

interface TableAnswerCardProps {
  answer: TableAnswerPayload;
  pipelineStage?: string;
  warnings?: string[];
  onFollowup?: (q: string) => void;
}

function TableAnswerCard({
  answer,
  pipelineStage,
  warnings,
  onFollowup,
}: TableAnswerCardProps) {
  return (
    <AnswerCardShell
      title={answer.title}
      subtitle={answer.summary_text ?? undefined}
      confidence={answer.confidence}
      pipelineStage={pipelineStage}
      warnings={warnings}
      accentColor="purple"
    >
      {/* Highlights + row count */}
      <div className="flex items-center justify-between mt-1 mb-2">
        {(answer.highlights ?? []).length > 0 ? (
          <HighlightsBar highlights={answer.highlights ?? []} />
        ) : (
          <span className="text-xs text-gray-400">
            {answer.row_count} row{answer.row_count !== 1 ? "s" : ""}
            {answer.truncated && " (truncated)"}
          </span>
        )}
        {(answer.highlights ?? []).length > 0 && (
          <span className="text-xs text-gray-400 shrink-0 ml-2">
            {answer.row_count} row{answer.row_count !== 1 ? "s" : ""}
            {answer.truncated && " · truncated"}
          </span>
        )}
      </div>

      {/* Table */}
      {answer.rows.length > 0 ? (
        <div className="overflow-x-auto rounded-lg border border-gray-100 mt-2">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100">
                {answer.columns.map((col) => (
                  <th
                    key={col}
                    className="px-3 py-2 text-left font-semibold text-gray-600 whitespace-nowrap"
                  >
                    {col.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {answer.rows.map((row, i) => (
                <tr
                  key={i}
                  className={clsx(
                    "border-t border-gray-50 hover:bg-blue-50/30 transition-colors",
                    i % 2 === 1 && "bg-gray-50/40"
                  )}
                >
                  {answer.columns.map((col) => (
                    <td key={col} className="px-3 py-2 text-gray-700 whitespace-nowrap">
                      {String(row.cells[col] ?? "—")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="py-8 text-center">
          <p className="text-sm text-gray-400">No data found.</p>
        </div>
      )}

      <SectionsList sections={answer.sections ?? []} />
      <CaveatsList caveats={answer.caveats} />
      <EvidenceDrawer evidence={answer.evidence} />
      <FollowupPills
        followups={answer.suggested_followups ?? []}
        onFollowup={onFollowup}
      />
    </AnswerCardShell>
  );
}

// ── Comparison answer ──────────────────────────────────────────────────────────

function ComparisonBar({
  item,
  maxValue,
}: {
  item: ComparisonItem;
  maxValue: number;
}) {
  const pct =
    maxValue > 0 && item.raw_value != null
      ? Math.round((Math.abs(item.raw_value) / maxValue) * 100)
      : 0;

  return (
    <div className="flex items-center gap-3 py-1">
      <span
        className={clsx(
          "text-xs w-36 shrink-0 truncate",
          item.is_baseline ? "text-blue-700 font-semibold" : "text-gray-600"
        )}
        title={item.label}
      >
        {item.label}
      </span>
      <div className="flex-1 bg-gray-100 rounded-full h-2 overflow-hidden">
        <div
          className={clsx(
            "h-full rounded-full transition-all duration-500",
            item.is_baseline ? "bg-blue-500" : "bg-gray-300"
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs font-mono text-gray-800 shrink-0 w-24 text-right tabular-nums">
        {item.value}
      </span>
      {item.delta_pct != null && (
        <span
          className={clsx(
            "text-xs shrink-0 w-14 text-right font-medium",
            item.delta_pct > 0 ? "text-red-500" : "text-green-600"
          )}
        >
          {item.delta_pct > 0 ? "+" : ""}
          {item.delta_pct.toFixed(1)}%
        </span>
      )}
    </div>
  );
}

interface ComparisonAnswerCardProps {
  answer: ComparisonAnswerPayload;
  pipelineStage?: string;
  warnings?: string[];
  onFollowup?: (q: string) => void;
}

function ComparisonAnswerCard({
  answer,
  pipelineStage,
  warnings,
  onFollowup,
}: ComparisonAnswerCardProps) {
  const maxValue = Math.max(
    ...answer.items.map((i) => Math.abs(i.raw_value ?? 0)),
    1
  );

  return (
    <AnswerCardShell
      title={answer.title}
      subtitle={answer.summary_text ?? undefined}
      confidence={answer.confidence}
      pipelineStage={pipelineStage}
      warnings={warnings}
      accentColor="green"
    >
      {/* Dimension + metric label */}
      <p className="text-xs text-gray-400 mt-1 mb-2">
        Comparing <span className="font-medium text-gray-600">{answer.metric}</span>
        {" "}by <span className="font-medium text-gray-600">{answer.dimension}</span>
      </p>

      <HighlightsBar highlights={answer.highlights ?? []} />

      {/* Comparison bars */}
      <div className="space-y-0.5 mt-2">
        {answer.items.map((item, i) => (
          <ComparisonBar key={i} item={item} maxValue={maxValue} />
        ))}
      </div>

      <SectionsList sections={answer.sections ?? []} />
      <CaveatsList caveats={answer.caveats} />
      <EvidenceDrawer evidence={answer.evidence} />
      <FollowupPills
        followups={answer.suggested_followups ?? []}
        onFollowup={onFollowup}
      />
    </AnswerCardShell>
  );
}

// ── Prose answer (upgraded from plain <p> to full card) ───────────────────────

interface ProseAnswerCardProps {
  answer: ProseAnswer;
  pipelineStage?: string;
  warnings?: string[];
  onFollowup?: (q: string) => void;
}

function ProseAnswerCard({
  answer,
  pipelineStage,
  warnings,
  onFollowup,
}: ProseAnswerCardProps) {
  // If there's no title and no structured data, render a minimal card
  // to avoid an oversized shell for one-line answers.
  const hasRichContent =
    answer.title ||
    (answer.highlights ?? []).length > 0 ||
    (answer.sections ?? []).length > 0 ||
    (answer.caveats ?? []).length > 0;

  if (!hasRichContent && pipelineStage === "llm") {
    // Minimal rendering: styled bubble, not a full card
    return (
      <div className="space-y-2">
        <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap bg-gray-50 border border-gray-100 rounded-xl px-4 py-3">
          {answer.text}
        </p>
        {answer.confidence != null && (
          <div className="flex items-center gap-2">
            <ConfidenceBadge confidence={answer.confidence} />
          </div>
        )}
        <FollowupPills
          followups={answer.suggested_followups ?? []}
          onFollowup={onFollowup}
        />
      </div>
    );
  }

  return (
    <AnswerCardShell
      title={answer.title ?? undefined}
      confidence={answer.confidence}
      pipelineStage={pipelineStage}
      warnings={warnings}
      accentColor={pipelineStage !== "llm" ? "amber" : "blue"}
    >
      <HighlightsBar highlights={answer.highlights ?? []} />

      <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap mt-1">
        {answer.text}
      </p>

      <SectionsList sections={answer.sections ?? []} />
      <CaveatsList caveats={answer.caveats} />
      <EvidenceDrawer evidence={answer.evidence} />
      <FollowupPills
        followups={answer.suggested_followups ?? []}
        onFollowup={onFollowup}
      />
    </AnswerCardShell>
  );
}

// ── No-data answer card ────────────────────────────────────────────────────────
//
// Polished "nothing found" card.  Never says "The provided context does not..."
// Always grounds the message in the bucket/institution that was searched.

interface NoDataAnswerCardProps {
  answer: NoDataAnswer;
  onFollowup?: (q: string) => void;
}

function NoDataAnswerCard({ answer, onFollowup }: NoDataAnswerCardProps) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden border-t-2 border-t-gray-300">
      {/* Header */}
      <div className="flex items-start gap-3 px-4 pt-4 pb-2">
        <div className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center shrink-0 mt-0.5">
          <Search size={15} className="text-gray-400" />
        </div>
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-gray-900">{answer.title}</h3>
          <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">{answer.summary}</p>
        </div>
      </div>

      <div className="px-4 pb-4 space-y-3">
        {/* What was checked */}
        {answer.what_was_checked.length > 0 && (
          <div>
            <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide mb-1">
              What I checked
            </p>
            <ul className="space-y-0.5">
              {answer.what_was_checked.map((item, i) => (
                <li key={i} className="text-xs text-gray-600 flex items-start gap-1.5">
                  <span className="text-gray-300 mt-0.5">·</span>
                  {item}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Possible reasons */}
        {answer.possible_reasons.length > 0 && (
          <div>
            <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide mb-1">
              Possible reasons
            </p>
            <ul className="space-y-0.5">
              {answer.possible_reasons.map((item, i) => (
                <li key={i} className="text-xs text-gray-500 flex items-start gap-1.5">
                  <span className="text-gray-300 mt-0.5">·</span>
                  {item}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Follow-ups */}
        <FollowupPills followups={answer.suggested_followups ?? []} onFollowup={onFollowup} />
      </div>
    </div>
  );
}

// ── Partial-data answer card ───────────────────────────────────────────────────

interface PartialDataAnswerCardProps {
  answer: PartialDataAnswer;
  onFollowup?: (q: string) => void;
}

function PartialDataAnswerCard({ answer, onFollowup }: PartialDataAnswerCardProps) {
  return (
    <div className="bg-white border border-amber-200 rounded-xl overflow-hidden border-t-2 border-t-amber-400">
      {/* Header */}
      <div className="flex items-start gap-3 px-4 pt-4 pb-2">
        <div className="w-8 h-8 rounded-full bg-amber-50 flex items-center justify-center shrink-0 mt-0.5">
          <Info size={15} className="text-amber-500" />
        </div>
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-gray-900">{answer.title}</h3>
          <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">{answer.summary}</p>
        </div>
      </div>

      <div className="px-4 pb-4 space-y-3">
        {/* What was found */}
        {answer.what_was_found.length > 0 && (
          <div>
            <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide mb-1">
              What was found
            </p>
            <ul className="space-y-0.5">
              {answer.what_was_found.map((item, i) => (
                <li key={i} className="text-xs text-gray-600 flex items-start gap-1.5">
                  <CheckCircle size={11} className="text-amber-400 shrink-0 mt-0.5" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* What is missing */}
        {answer.what_is_missing.length > 0 && (
          <div>
            <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide mb-1">
              What would help
            </p>
            <ul className="space-y-0.5">
              {answer.what_is_missing.map((item, i) => (
                <li key={i} className="text-xs text-gray-500 flex items-start gap-1.5">
                  <span className="text-gray-300 mt-0.5">·</span>
                  {item}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Evidence drawer */}
        {answer.evidence && <EvidenceDrawer evidence={answer.evidence} />}

        {/* Follow-ups */}
        <FollowupPills followups={answer.suggested_followups ?? []} onFollowup={onFollowup} />
      </div>
    </div>
  );
}

// ── Main dispatcher ────────────────────────────────────────────────────────────

export function AnswerCard({
  structured,
  pipelineStage = "llm",
  warnings = [],
  onFollowup,
}: AnswerCardProps) {
  switch (structured.answer_type) {
    case "no_data":
      return (
        <NoDataAnswerCard
          answer={structured as NoDataAnswer}
          onFollowup={onFollowup}
        />
      );
    case "partial_data":
      return (
        <PartialDataAnswerCard
          answer={structured as PartialDataAnswer}
          onFollowup={onFollowup}
        />
      );
    case "numeric":
      return (
        <NumericAnswerCard
          answer={structured as NumericAnswerPayload}
          pipelineStage={pipelineStage}
          warnings={warnings}
          onFollowup={onFollowup}
        />
      );
    case "table":
      return (
        <TableAnswerCard
          answer={structured as TableAnswerPayload}
          pipelineStage={pipelineStage}
          warnings={warnings}
          onFollowup={onFollowup}
        />
      );
    case "comparison":
      return (
        <ComparisonAnswerCard
          answer={structured as ComparisonAnswerPayload}
          pipelineStage={pipelineStage}
          warnings={warnings}
          onFollowup={onFollowup}
        />
      );
    case "prose":
    default:
      return (
        <ProseAnswerCard
          answer={structured as ProseAnswer}
          pipelineStage={pipelineStage}
          warnings={warnings}
          onFollowup={onFollowup}
        />
      );
  }
}
