"use client";

import { useState } from "react";
import { RefreshCw, Trash2, Loader2, AlertTriangle, ChevronRight, Hash } from "lucide-react";
import toast from "react-hot-toast";
import type { DocumentSummary } from "@/types/index";
import DocumentStatusBadge from "./DocumentStatusBadge";
import {
  normalizeDocumentStatus, normalizeDocumentMonth, normalizeDocumentYear,
  monthShort, relativeTime,
} from "@/lib/documentLibrary";
import { documentsApi } from "@/features/documents/api";

interface Props {
  doc: DocumentSummary;
  onChanged: () => void;
  onClick: (doc: DocumentSummary) => void;
  issueCount?: number;
}

export default function MonthStatementRow({ doc, onChanged, onClick, issueCount = 0 }: Props) {
  const [deleting, setDeleting] = useState(false);
  const [reprocessing, setReprocessing] = useState(false);

  const status = normalizeDocumentStatus(doc);
  const month = normalizeDocumentMonth(doc);
  const year = normalizeDocumentYear(doc);
  const monthLabel = month ? (monthShort(month) ?? "?") : "—";
  const period = year ? `${monthLabel} ${year}` : monthLabel;

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`Delete "${doc.filename}"? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      await documentsApi.delete(doc.id);
      toast.success("Document deleted");
      onChanged();
    } catch {
      toast.error("Failed to delete");
      setDeleting(false);
    }
  };

  const handleReprocess = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setReprocessing(true);
    try {
      const res = await documentsApi.reprocess(doc.id);
      if (res.ok) {
        toast.success(`Reprocessed: ${res.transactions} txns, ${res.chunks} chunks`);
      } else {
        toast.error(res.error || "Reprocess failed");
      }
      onChanged();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Reprocess failed");
    } finally {
      setReprocessing(false);
    }
  };

  return (
    <button
      onClick={() => onClick(doc)}
      className="w-full flex items-center justify-between pl-12 pr-4 py-2.5 transition-all group text-left"
      style={{ borderTop: "1px solid var(--row-border)" }}
      onMouseEnter={(e) => (e.currentTarget.style.background = "var(--row-bg)")}
      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
    >
      <div className="flex items-center gap-3 min-w-0">
        <div className="min-w-0">
          <p className="text-[12.5px] font-semibold" style={{ color: "var(--text-primary)" }}>{period}</p>
          <div className="flex items-center gap-2 mt-0.5 flex-wrap">
            {doc.statement_count > 0 && (
              <span className="flex items-center gap-0.5 text-[10px]" style={{ color: "var(--text-dim)" }}>
                <Hash size={9} />{doc.statement_count} stmt
              </span>
            )}
            {doc.upload_time && (
              <span className="text-[10px]" style={{ color: "var(--text-dim)" }}>{relativeTime(doc.upload_time)}</span>
            )}
          </div>
        </div>
        {issueCount > 0 && (
          <span className="flex items-center gap-1 text-[9.5px] font-semibold px-1.5 py-0.5 rounded-full"
            style={{ background: "rgba(200,154,0,0.10)", color: "#c89a00" }}>
            <AlertTriangle size={9} />{issueCount} issue{issueCount !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      <div className="flex items-center gap-1.5 shrink-0 ml-3">
        <DocumentStatusBadge status={status} size="xs" />
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity" onClick={(e) => e.stopPropagation()}>
          <button onClick={handleReprocess} disabled={reprocessing}
            className="p-1.5 rounded-lg transition-colors disabled:opacity-40"
            style={{ color: "var(--text-dim)" }}
            onMouseEnter={(e) => (e.currentTarget.style.color = "var(--border-accent)")}
            onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-dim)")}
            title="Reprocess">
            {reprocessing ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
          </button>
          <button onClick={handleDelete} disabled={deleting}
            className="p-1.5 rounded-lg transition-colors disabled:opacity-40"
            style={{ color: "var(--text-dim)" }}
            onMouseEnter={(e) => (e.currentTarget.style.color = "rgba(228,87,87,0.85)")}
            onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-dim)")}
            title="Delete">
            {deleting ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
          </button>
        </div>
        <ChevronRight size={12} className="opacity-0 group-hover:opacity-100 transition-opacity" style={{ color: "var(--text-dim)" }} />
      </div>
    </button>
  );
}
