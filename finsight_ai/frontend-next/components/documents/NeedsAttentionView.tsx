"use client";

import { useState } from "react";
import { AlertTriangle, RefreshCw, Trash2, Loader2, CheckCircle2 } from "lucide-react";
import toast from "react-hot-toast";
import type { DocumentSummary, DocumentIssue } from "@/types/index";
import DocumentStatusBadge from "./DocumentStatusBadge";
import { findDocumentsNeedingAttention, normalizeDocumentStatus, normalizeDocumentInstitution, normalizeDocumentAccount, normalizeDocumentMonth, normalizeDocumentYear, monthShort } from "@/lib/documentLibrary";
import { documentsApi } from "@/features/documents/api";

interface Props {
  docs: DocumentSummary[];
  onChanged: () => void;
  onDocClick: (doc: DocumentSummary) => void;
  issuesByDoc?: Record<string, DocumentIssue>;
}

function AttentionCard({ doc, reasons, recommendedAction, onChanged, onDocClick }: {
  doc: DocumentSummary; reasons: string[]; recommendedAction: string;
  onChanged: () => void; onDocClick: (doc: DocumentSummary) => void;
}) {
  const [deleting, setDeleting] = useState(false);
  const [reprocessing, setReprocessing] = useState(false);

  const status = normalizeDocumentStatus(doc);
  const inst = normalizeDocumentInstitution(doc);
  const acct = normalizeDocumentAccount(doc);
  const month = normalizeDocumentMonth(doc);
  const year = normalizeDocumentYear(doc);
  const period = month && year ? `${monthShort(month)} ${year}` : year ? String(year) : null;

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
    <div className="rounded-2xl p-4 transition-all"
      style={{ background: "rgba(200,154,0,0.05)", border: "1px solid rgba(200,154,0,0.18)" }}>
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-start gap-3 min-w-0">
          <div className="p-1.5 rounded-lg shrink-0 mt-0.5" style={{ background: "rgba(200,154,0,0.12)", color: "#c89a00" }}>
            <AlertTriangle size={13} />
          </div>
          <div className="min-w-0">
            <button onClick={() => onDocClick(doc)}
              className="text-[13px] font-semibold text-left hover:underline truncate block max-w-full"
              style={{ color: "var(--text-primary)" }}>
              {inst !== "Unknown" ? `${inst}${acct !== "Unknown Account" ? ` · ${acct}` : ""}` : doc.filename}
              {period && <span className="font-normal ml-1.5" style={{ color: "var(--text-muted)" }}>· {period}</span>}
            </button>
            <p className="text-[10.5px] mt-0.5 truncate" style={{ color: "var(--text-dim)" }} title={doc.filename}>
              {doc.filename}
            </p>
          </div>
        </div>
        <DocumentStatusBadge status={status} size="xs" />
      </div>

      <div className="flex flex-wrap gap-1.5 mb-3 pl-8">
        {reasons.map((r) => (
          <span key={r} className="px-2 py-0.5 rounded-full text-[10px] font-medium"
            style={{ background: "rgba(200,154,0,0.10)", color: "#c89a00" }}>
            {r}
          </span>
        ))}
      </div>

      <p className="text-[11px] pl-8 mb-3" style={{ color: "var(--text-muted)" }}>
        Suggested: <span style={{ color: "var(--text-secondary)" }}>{recommendedAction}</span>
      </p>

      <div className="flex items-center gap-2 pl-8">
        <button onClick={handleReprocess} disabled={reprocessing}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-[11.5px] font-semibold transition-all disabled:opacity-50 hover:scale-[1.02]"
          style={{ background: "var(--btn-glass-bg)", border: "1px solid var(--btn-glass-border)", color: "var(--btn-glass-color)" }}>
          {reprocessing ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
          Reprocess
        </button>
        <button onClick={handleDelete} disabled={deleting}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-[11.5px] font-semibold transition-all disabled:opacity-50 hover:scale-[1.02]"
          style={{ background: "rgba(228,87,87,0.06)", border: "1px solid rgba(228,87,87,0.18)", color: "#E45757" }}>
          {deleting ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
          Delete
        </button>
      </div>
    </div>
  );
}

export default function NeedsAttentionView({ docs, onChanged, onDocClick, issuesByDoc }: Props) {
  const items = findDocumentsNeedingAttention(docs, issuesByDoc);

  if (items.length === 0) {
    return (
      <div className="rounded-2xl px-6 py-12 text-center"
        style={{ background: "rgba(61,184,134,0.06)", border: "1px solid rgba(61,184,134,0.18)" }}>
        <div className="w-12 h-12 rounded-2xl flex items-center justify-center mx-auto mb-3"
          style={{ background: "rgba(61,184,134,0.12)", color: "#3db886" }}>
          <CheckCircle2 size={22} />
        </div>
        <p className="text-[14px] font-bold mb-1" style={{ color: "#3db886" }}>All clear</p>
        <p className="text-[12px]" style={{ color: "var(--text-muted)" }}>Your financial library looks healthy.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-[12px]" style={{ color: "var(--text-muted)" }}>
        {items.length} document{items.length !== 1 ? "s" : ""} need{items.length === 1 ? "s" : ""} attention.
        Fix these issues to improve Coral's answers.
      </p>
      {items.map(({ doc, reasons, recommendedAction }) => (
        <AttentionCard key={doc.id} doc={doc} reasons={reasons} recommendedAction={recommendedAction}
          onChanged={onChanged} onDocClick={onDocClick} />
      ))}
    </div>
  );
}
