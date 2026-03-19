/**
 * EvidenceDrawer — collapsible panel showing source evidence for an answer.
 *
 * Renders:
 * - Data source badge (SQL / vector / hybrid)
 * - SQL query (syntax-highlighted pre block) when present
 * - Vector chunk citations with institution, period, page
 */

import React, { useState } from "react";
import { ChevronDown, ChevronRight, Database, FileText, Code2 } from "lucide-react";
import { clsx } from "clsx";
import type { AnswerEvidence, EvidenceChunk } from "../../types";

// ── Data source badge ─────────────────────────────────────────────────────────

const DATA_SOURCE_LABELS: Record<string, { label: string; color: string }> = {
  sql: { label: "SQL", color: "bg-purple-100 text-purple-700" },
  vector: { label: "Vector", color: "bg-blue-100 text-blue-700" },
  hybrid: { label: "SQL + Vector", color: "bg-green-100 text-green-700" },
  none: { label: "No data", color: "bg-gray-100 text-gray-500" },
};

function DataSourceBadge({ source }: { source: string }) {
  const { label, color } = DATA_SOURCE_LABELS[source] ?? DATA_SOURCE_LABELS.none;
  return (
    <span className={clsx("inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium", color)}>
      <Database size={10} />
      {label}
    </span>
  );
}

// ── Chunk card ────────────────────────────────────────────────────────────────

function ChunkCard({ chunk }: { chunk: EvidenceChunk }) {
  const [expanded, setExpanded] = useState(false);
  const preview = chunk.chunk_text.slice(0, 120);
  const hasMore = chunk.chunk_text.length > 120;

  return (
    <div className="border border-gray-100 rounded-lg p-3 bg-white">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 text-xs text-gray-500 flex-wrap">
          {chunk.institution_type && (
            <span className="capitalize font-medium text-gray-700">
              {chunk.institution_type.replace("_", " ")}
            </span>
          )}
          {chunk.statement_period && <span>· {chunk.statement_period}</span>}
          {chunk.page_number != null && <span>· p.{chunk.page_number}</span>}
          {chunk.section && <span>· {chunk.section}</span>}
          {chunk.relevance_score != null && (
            <span className="text-gray-400">
              · score {chunk.relevance_score.toFixed(2)}
            </span>
          )}
        </div>
        {hasMore && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-blue-500 text-xs shrink-0"
          >
            {expanded ? "less" : "more"}
          </button>
        )}
      </div>
      <p className="text-xs text-gray-700 mt-1.5 leading-relaxed whitespace-pre-wrap">
        {expanded ? chunk.chunk_text : preview}
        {!expanded && hasMore && "…"}
      </p>
    </div>
  );
}

// ── Main drawer ───────────────────────────────────────────────────────────────

interface EvidenceDrawerProps {
  evidence: AnswerEvidence;
  defaultOpen?: boolean;
}

export function EvidenceDrawer({ evidence, defaultOpen = false }: EvidenceDrawerProps) {
  const [open, setOpen] = useState(defaultOpen);
  const hasContent =
    evidence.chunks.length > 0 || !!evidence.sql_query;

  if (!hasContent) return null;

  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700 transition-colors"
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <span>Evidence</span>
        <DataSourceBadge source={evidence.data_source} />
        {evidence.chunks.length > 0 && (
          <span className="text-gray-400">
            · {evidence.chunks.length} chunk{evidence.chunks.length !== 1 ? "s" : ""}
          </span>
        )}
      </button>

      {open && (
        <div className="mt-2 space-y-2">
          {/* SQL query */}
          {evidence.sql_query && (
            <div className="border border-gray-200 rounded-lg overflow-hidden">
              <div className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-50 border-b border-gray-200">
                <Code2 size={12} className="text-gray-500" />
                <span className="text-xs font-medium text-gray-600">SQL Query</span>
                {evidence.sql_row_count != null && (
                  <span className="text-xs text-gray-400 ml-auto">
                    {evidence.sql_row_count} row{evidence.sql_row_count !== 1 ? "s" : ""}
                  </span>
                )}
              </div>
              <pre className="text-xs p-3 overflow-x-auto bg-gray-900 text-green-300 leading-relaxed">
                {evidence.sql_query}
              </pre>
            </div>
          )}

          {/* Vector chunks */}
          {evidence.chunks.length > 0 && (
            <div className="space-y-1.5">
              <div className="flex items-center gap-1 text-xs text-gray-500">
                <FileText size={11} />
                <span>Source chunks</span>
              </div>
              {evidence.chunks.map((chunk, i) => (
                <ChunkCard key={chunk.id || i} chunk={chunk} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
