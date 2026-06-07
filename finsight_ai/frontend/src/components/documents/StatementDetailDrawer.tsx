import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X, RefreshCw, Trash2, MessageSquare, Loader2, ExternalLink,
  FileText, Calendar, Building2, CreditCard, Hash, CheckCircle2, XCircle,
} from "lucide-react";
import toast from "react-hot-toast";
import type { DocumentSummary } from "../../types";
import { documentsApi } from "../../api/documents";
import { DocumentStatusBadge } from "./DocumentStatusBadge";
import {
  normalizeDocumentStatus,
  normalizeDocumentInstitution,
  normalizeDocumentAccount,
  normalizeDocumentYear,
  normalizeDocumentMonth,
  monthName,
  formatDate,
  relativeTime,
} from "../../lib/documentLibrary";
import { useAppStore } from "../../store/appStore";

interface Props {
  doc: DocumentSummary | null;
  onClose: () => void;
  onChanged: () => void;
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5" style={{ borderBottom: "1px solid var(--row-border)" }}>
      <span className="text-[11.5px] font-medium shrink-0" style={{ color: "var(--text-muted)" }}>
        {label}
      </span>
      <span className="text-[12px] font-medium text-right" style={{ color: "var(--text-primary)" }}>
        {value}
      </span>
    </div>
  );
}

function Check({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2 py-1.5">
      {ok ? (
        <CheckCircle2 size={13} style={{ color: "#3db886" }} />
      ) : (
        <XCircle size={13} style={{ color: "rgba(228,87,87,0.70)" }} />
      )}
      <span className="text-[12px]" style={{ color: ok ? "var(--text-secondary)" : "var(--text-muted)" }}>
        {label}
      </span>
    </div>
  );
}

export function StatementDetailDrawer({ doc, onClose, onChanged }: Props) {
  const { setActivePage } = useAppStore();
  const [deleting, setDeleting] = useState(false);
  const [reprocessing, setReprocessing] = useState(false);

  const handleDelete = async () => {
    if (!doc) return;
    if (!confirm(`Delete "${doc.filename}"? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      await documentsApi.delete(doc.id);
      toast.success("Document deleted");
      onChanged();
      onClose();
    } catch {
      toast.error("Failed to delete");
      setDeleting(false);
    }
  };

  const handleReprocess = async () => {
    if (!doc) return;
    setReprocessing(true);
    try {
      const res = await documentsApi.reprocess(doc.id);
      if (res.ok) {
        toast.success(`Reprocessed: ${res.transactions} txns, ${res.chunks} chunks`);
      } else {
        toast.error(res.error || "Reprocess failed");
      }
      onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Reprocess failed");
    } finally {
      setReprocessing(false);
    }
  };

  const handleAskCoral = () => {
    setActivePage("chat");
    onClose();
  };

  const status = doc ? normalizeDocumentStatus(doc) : "unknown";
  const year = doc ? normalizeDocumentYear(doc) : null;
  const month = doc ? normalizeDocumentMonth(doc) : null;
  const monthLabel = month ? monthName(month) : null;
  const period = monthLabel && year ? `${monthLabel} ${year}` : year ? String(year) : "—";

  const hasTransactions = doc ? (doc.statement_count > 0) : false;

  return (
    <AnimatePresence>
      {doc && (
        <>
          {/* Backdrop */}
          <motion.div
            className="fixed inset-0 z-40"
            style={{ background: "rgba(3,17,31,0.50)", backdropFilter: "blur(4px)" }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />

          {/* Drawer */}
          <motion.aside
            className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-[400px] overflow-y-auto"
            style={{
              background: "rgba(4,16,30,0.97)",
              backdropFilter: "blur(24px)",
              WebkitBackdropFilter: "blur(24px)",
              borderLeft: "1px solid rgba(34,211,238,0.18)",
              boxShadow: "-24px 0 80px rgba(0,0,0,0.40)",
            }}
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 320, damping: 34 }}
          >
            {/* Header */}
            <div
              className="flex items-center justify-between px-5 py-4 sticky top-0 z-10"
              style={{
                background: "rgba(4,16,30,0.95)",
                borderBottom: "1px solid var(--row-border)",
                backdropFilter: "blur(16px)",
              }}
            >
              <div className="flex items-center gap-2">
                <div
                  className="p-1.5 rounded-lg"
                  style={{ background: "rgba(34,211,238,0.10)", color: "rgba(34,211,238,0.80)" }}
                >
                  <FileText size={14} />
                </div>
                <h2 className="text-[14px] font-bold" style={{ color: "var(--text-primary)" }}>
                  Statement Details
                </h2>
              </div>
              <button
                onClick={onClose}
                className="p-2 rounded-xl transition-colors"
                style={{ color: "var(--text-muted)" }}
                onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text-primary)")}
                onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-muted)")}
              >
                <X size={16} />
              </button>
            </div>

            <div className="px-5 py-5 space-y-5">
              {/* Identity card */}
              <div
                className="rounded-2xl p-4"
                style={{
                  background: "rgba(34,211,238,0.05)",
                  border: "1px solid rgba(34,211,238,0.14)",
                }}
              >
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="min-w-0">
                    <p className="text-[13px] font-bold truncate" style={{ color: "var(--text-primary)" }}>
                      {normalizeDocumentInstitution(doc)}
                    </p>
                    <p className="text-[11.5px] mt-0.5" style={{ color: "var(--text-muted)" }}>
                      {normalizeDocumentAccount(doc)} · {period}
                    </p>
                  </div>
                  <DocumentStatusBadge status={status} size="sm" />
                </div>
                <p
                  className="text-[10.5px] font-mono truncate"
                  style={{ color: "var(--text-dim)" }}
                  title={doc.filename}
                >
                  {doc.filename}
                </p>
              </div>

              {/* Metadata */}
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wider mb-2" style={{ color: "var(--text-dim)" }}>
                  Details
                </p>
                <div>
                  <Row label="Institution" value={
                    <span className="flex items-center gap-1.5">
                      <Building2 size={11} style={{ color: "var(--border-accent)" }} />
                      {normalizeDocumentInstitution(doc)}
                    </span>
                  } />
                  <Row label="Account" value={
                    <span className="flex items-center gap-1.5">
                      <CreditCard size={11} style={{ color: "var(--border-accent)" }} />
                      {normalizeDocumentAccount(doc)}
                    </span>
                  } />
                  <Row label="Period" value={
                    <span className="flex items-center gap-1.5">
                      <Calendar size={11} style={{ color: "var(--border-accent)" }} />
                      {period}
                    </span>
                  } />
                  {doc.page_count != null && (
                    <Row label="Pages" value={`${doc.page_count} pages`} />
                  )}
                  {doc.statement_count > 0 && (
                    <Row label="Statements" value={
                      <span className="flex items-center gap-1.5">
                        <Hash size={11} style={{ color: "var(--border-accent)" }} />
                        {doc.statement_count}
                      </span>
                    } />
                  )}
                  <Row label="Uploaded" value={
                    <span title={formatDate(doc.upload_time)}>
                      {relativeTime(doc.upload_time)}
                    </span>
                  } />
                  {doc.processed_time && (
                    <Row label="Processed" value={
                      <span title={formatDate(doc.processed_time)}>
                        {relativeTime(doc.processed_time)}
                      </span>
                    } />
                  )}
                  {doc.period_start && (
                    <Row label="Period start" value={doc.period_start} />
                  )}
                  {doc.period_end && (
                    <Row label="Period end" value={doc.period_end} />
                  )}
                </div>
              </div>

              {/* Parsing health */}
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wider mb-2" style={{ color: "var(--text-dim)" }}>
                  Parsing Health
                </p>
                <div
                  className="rounded-2xl p-4"
                  style={{ background: "var(--panel-bg)", border: "1px solid var(--panel-border)" }}
                >
                  <Check ok={status === "parsed"} label="Document parsed" />
                  <Check ok={hasTransactions} label="Transactions extracted" />
                  <Check ok={status === "parsed" && year != null} label="Year detected" />
                  <Check ok={status === "parsed" && month != null} label="Month detected" />
                  <Check ok={normalizeDocumentInstitution(doc) !== "Unknown"} label="Institution identified" />
                  <Check ok={normalizeDocumentAccount(doc) !== "Unknown Account"} label="Account identified" />
                </div>
              </div>

              {/* Error message */}
              {doc.error && (
                <div
                  className="rounded-2xl px-4 py-3 text-[11.5px]"
                  style={{ background: "rgba(228,87,87,0.08)", border: "1px solid rgba(228,87,87,0.20)", color: "#E45757" }}
                >
                  <p className="font-semibold mb-1">Parse error</p>
                  <p style={{ color: "rgba(228,87,87,0.80)" }}>{doc.error}</p>
                </div>
              )}

              {/* Actions */}
              <div className="space-y-2 pt-1">
                <button
                  onClick={handleAskCoral}
                  className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-[13px] font-semibold transition-all hover:scale-[1.01]"
                  style={{
                    background: "linear-gradient(135deg, rgba(34,211,238,0.15), rgba(34,211,238,0.08))",
                    border: "1px solid rgba(34,211,238,0.25)",
                    color: "rgba(34,211,238,0.90)",
                  }}
                >
                  <MessageSquare size={14} />
                  Ask Coral About This Statement
                  <ExternalLink size={11} style={{ opacity: 0.6 }} />
                </button>

                <div className="flex gap-2">
                  <button
                    onClick={handleReprocess}
                    disabled={reprocessing}
                    className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-[12.5px] font-semibold transition-all hover:scale-[1.01] disabled:opacity-50"
                    style={{
                      background: "var(--btn-glass-bg)",
                      border: "1px solid var(--btn-glass-border)",
                      color: "var(--btn-glass-color)",
                    }}
                  >
                    {reprocessing ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
                    Reprocess
                  </button>

                  <button
                    onClick={handleDelete}
                    disabled={deleting}
                    className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-[12.5px] font-semibold transition-all hover:scale-[1.01] disabled:opacity-50"
                    style={{
                      background: "rgba(228,87,87,0.08)",
                      border: "1px solid rgba(228,87,87,0.22)",
                      color: "#E45757",
                    }}
                  >
                    {deleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
                    Delete
                  </button>
                </div>
              </div>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
