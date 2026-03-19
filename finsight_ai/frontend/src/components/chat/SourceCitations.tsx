/**
 * SourceCitations — displays evidence chunks from RAG retrieval.
 *
 * Shown below the assistant's answer so the user can verify which
 * document chunks grounded the response.
 */

import React, { useState } from "react";
import { clsx } from "clsx";
import { FileText, ChevronDown, ChevronUp } from "lucide-react";

export interface SourceChunk {
  id: string;
  document_id: string;
  chunk_text: string;
  page_number: number | null;
  section: string | null;
  institution_type: string | null;
  statement_period: string | null;
}

interface SourceCitationsProps {
  sources: SourceChunk[];
}

function Citation({ source, index }: { source: SourceChunk; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const preview = source.chunk_text.slice(0, 120).trimEnd();
  const hasMore = source.chunk_text.length > 120;

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-gray-50 transition-colors"
      >
        <span className="text-xs font-medium text-gray-500 shrink-0 w-4 text-center">
          {index + 1}
        </span>
        <FileText size={13} className="text-gray-400 shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            {source.institution_type && (
              <span className="text-xs px-1.5 py-0.5 rounded bg-blue-100 text-blue-700">
                {source.institution_type.replace("_", " ")}
              </span>
            )}
            {source.statement_period && (
              <span className="text-xs text-gray-500">{source.statement_period}</span>
            )}
            {source.page_number != null && (
              <span className="text-xs text-gray-400">p.{source.page_number}</span>
            )}
            {source.section && (
              <span className="text-xs text-gray-400 truncate max-w-[120px]">
                {source.section}
              </span>
            )}
          </div>
          {!expanded && (
            <p className="text-xs text-gray-600 mt-0.5 truncate">{preview}{hasMore ? "…" : ""}</p>
          )}
        </div>
        {expanded ? (
          <ChevronUp size={13} className="text-gray-400 shrink-0" />
        ) : (
          <ChevronDown size={13} className="text-gray-400 shrink-0" />
        )}
      </button>

      {expanded && (
        <div className="px-3 pb-3 pt-1 bg-gray-50 border-t border-gray-100">
          <p className="text-xs text-gray-700 leading-relaxed whitespace-pre-wrap font-mono">
            {source.chunk_text}
          </p>
        </div>
      )}
    </div>
  );
}

export function SourceCitations({ sources }: SourceCitationsProps) {
  const [showAll, setShowAll] = useState(false);

  if (sources.length === 0) return null;

  const visible = showAll ? sources : sources.slice(0, 3);

  return (
    <div className="mt-2 space-y-1">
      <p className="text-[10px] font-medium text-gray-400 uppercase tracking-wide px-1">
        Sources ({sources.length})
      </p>
      <div className="space-y-1">
        {visible.map((s, i) => (
          <Citation key={s.id} source={s} index={i} />
        ))}
      </div>
      {sources.length > 3 && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className={clsx(
            "text-xs text-blue-600 hover:text-blue-800 transition-colors px-1"
          )}
        >
          {showAll ? "Show fewer" : `Show ${sources.length - 3} more…`}
        </button>
      )}
    </div>
  );
}
