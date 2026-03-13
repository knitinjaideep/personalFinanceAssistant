/**
 * AnswerCard — top-level dispatcher that renders the correct answer component
 * based on ``answer_type``.
 *
 * Hierarchy:
 *   AnswerCard
 *     ├── NumericAnswerCard
 *     ├── TableAnswerCard
 *     ├── ComparisonAnswerCard
 *     └── ProseAnswerCard (fallback)
 *
 * All variants share:
 * - Confidence badge
 * - Caveats list
 * - EvidenceDrawer (collapsible)
 */

import React from "react";
import { AlertTriangle, CheckCircle, Info } from "lucide-react";
import { clsx } from "clsx";
import type {
  StructuredAnswer,
  NumericAnswerPayload,
  TableAnswerPayload,
  ComparisonAnswerPayload,
  ProseAnswer,
  ComparisonItem,
} from "../../types";
import { EvidenceDrawer } from "./EvidenceDrawer";

// ── Confidence badge ──────────────────────────────────────────────────────────

function ConfidenceBadge({ confidence }: { confidence: number | null }) {
  if (confidence == null) return null;
  const pct = Math.round(confidence * 100);

  let color: string;
  let Icon: React.ElementType;
  if (confidence >= 0.8) {
    color = "text-green-600 bg-green-50";
    Icon = CheckCircle;
  } else if (confidence >= 0.5) {
    color = "text-yellow-600 bg-yellow-50";
    Icon = Info;
  } else {
    color = "text-red-600 bg-red-50";
    Icon = AlertTriangle;
  }

  return (
    <span className={clsx("inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded font-medium", color)}>
      <Icon size={11} />
      {pct}% confidence
    </span>
  );
}

// ── Caveats list ──────────────────────────────────────────────────────────────

function CaveatsList({ caveats }: { caveats: string[] }) {
  if (!caveats.length) return null;
  return (
    <ul className="mt-2 space-y-1">
      {caveats.map((c, i) => (
        <li key={i} className="flex items-start gap-1.5 text-xs text-amber-700 bg-amber-50 rounded px-2 py-1">
          <AlertTriangle size={11} className="shrink-0 mt-0.5" />
          {c}
        </li>
      ))}
    </ul>
  );
}

// ── Numeric answer ────────────────────────────────────────────────────────────

function NumericAnswerCard({ answer }: { answer: NumericAnswerPayload }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
            {answer.label}
          </p>
          {answer.period && (
            <p className="text-xs text-gray-400 mt-0.5">{answer.period}</p>
          )}
        </div>
        <ConfidenceBadge confidence={answer.confidence} />
      </div>

      <div className="flex items-baseline gap-2">
        <span className="text-3xl font-bold text-gray-900 tabular-nums">
          {answer.value}
        </span>
        {answer.unit && answer.unit !== "USD" && (
          <span className="text-sm text-gray-500">{answer.unit}</span>
        )}
      </div>

      {(answer.institution || answer.account) && (
        <p className="text-xs text-gray-500">
          {[answer.institution, answer.account].filter(Boolean).join(" · ")}
        </p>
      )}

      {answer.summary_text && (
        <p className="text-sm text-gray-600 border-t border-gray-100 pt-2">
          {answer.summary_text}
        </p>
      )}

      <CaveatsList caveats={answer.caveats} />
      <EvidenceDrawer evidence={answer.evidence} />
    </div>
  );
}

// ── Table answer ──────────────────────────────────────────────────────────────

function TableAnswerCard({ answer }: { answer: TableAnswerPayload }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden space-y-0">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
        <div>
          <p className="text-sm font-semibold text-gray-800">{answer.title}</p>
          {answer.summary_text && (
            <p className="text-xs text-gray-500 mt-0.5">{answer.summary_text}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-400">
            {answer.row_count} row{answer.row_count !== 1 ? "s" : ""}
            {answer.truncated && " (truncated)"}
          </span>
          <ConfidenceBadge confidence={answer.confidence} />
        </div>
      </div>

      {/* Table */}
      {answer.rows.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-gray-50">
                {answer.columns.map((col) => (
                  <th
                    key={col}
                    className="px-4 py-2 text-left font-medium text-gray-600 whitespace-nowrap"
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
                    "border-t border-gray-50",
                    i % 2 === 0 ? "bg-white" : "bg-gray-50/50"
                  )}
                >
                  {answer.columns.map((col) => (
                    <td key={col} className="px-4 py-2 text-gray-700 whitespace-nowrap">
                      {String(row.cells[col] ?? "—")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="px-4 py-6 text-sm text-gray-400 text-center">No data found.</p>
      )}

      {/* Footer */}
      {(answer.caveats.length > 0 || answer.evidence) && (
        <div className="px-4 py-3 border-t border-gray-100">
          <CaveatsList caveats={answer.caveats} />
          <EvidenceDrawer evidence={answer.evidence} />
        </div>
      )}
    </div>
  );
}

// ── Comparison answer ─────────────────────────────────────────────────────────

function ComparisonBar({ item, maxValue }: { item: ComparisonItem; maxValue: number }) {
  const pct = maxValue > 0 && item.raw_value != null
    ? Math.round((Math.abs(item.raw_value) / maxValue) * 100)
    : 0;

  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-gray-600 w-32 shrink-0 truncate" title={item.label}>
        {item.label}
      </span>
      <div className="flex-1 bg-gray-100 rounded-full h-2 overflow-hidden">
        <div
          className={clsx(
            "h-full rounded-full transition-all",
            item.is_baseline ? "bg-blue-500" : "bg-gray-400"
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs font-mono text-gray-800 shrink-0 w-24 text-right">
        {item.value}
      </span>
      {item.delta_pct != null && (
        <span
          className={clsx(
            "text-xs shrink-0 w-14 text-right",
            item.delta_pct > 0 ? "text-red-500" : "text-green-500"
          )}
        >
          {item.delta_pct > 0 ? "+" : ""}
          {item.delta_pct.toFixed(1)}%
        </span>
      )}
    </div>
  );
}

function ComparisonAnswerCard({ answer }: { answer: ComparisonAnswerPayload }) {
  const maxValue = Math.max(
    ...answer.items.map((i) => Math.abs(i.raw_value ?? 0)),
    1
  );

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-gray-800">{answer.title}</p>
          {answer.summary_text && (
            <p className="text-xs text-gray-500 mt-0.5">{answer.summary_text}</p>
          )}
        </div>
        <ConfidenceBadge confidence={answer.confidence} />
      </div>

      <div className="space-y-2">
        {answer.items.map((item, i) => (
          <ComparisonBar key={i} item={item} maxValue={maxValue} />
        ))}
      </div>

      <CaveatsList caveats={answer.caveats} />
      <EvidenceDrawer evidence={answer.evidence} />
    </div>
  );
}

// ── Prose fallback ────────────────────────────────────────────────────────────

function ProseAnswerCard({ answer }: { answer: ProseAnswer }) {
  return (
    <div className="space-y-1">
      <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">
        {answer.text}
      </p>
      {(answer.confidence != null || answer.caveats.length > 0) && (
        <div className="flex items-center gap-2 flex-wrap mt-2">
          <ConfidenceBadge confidence={answer.confidence} />
        </div>
      )}
      <CaveatsList caveats={answer.caveats} />
      <EvidenceDrawer evidence={answer.evidence} />
    </div>
  );
}

// ── Main dispatcher ───────────────────────────────────────────────────────────

interface AnswerCardProps {
  structured: StructuredAnswer;
}

export function AnswerCard({ structured }: AnswerCardProps) {
  switch (structured.answer_type) {
    case "numeric":
      return <NumericAnswerCard answer={structured as NumericAnswerPayload} />;
    case "table":
      return <TableAnswerCard answer={structured as TableAnswerPayload} />;
    case "comparison":
      return <ComparisonAnswerCard answer={structured as ComparisonAnswerPayload} />;
    case "prose":
    default:
      return <ProseAnswerCard answer={structured as ProseAnswer} />;
  }
}
