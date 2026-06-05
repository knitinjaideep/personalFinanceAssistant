/**
 * DocumentsModal — list uploaded documents with status, reingest, delete.
 */

import { useState, useEffect } from "react";
import { X, FileText, Loader2, CheckCircle2, AlertCircle, RefreshCw, Trash2, Clock } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import toast from "react-hot-toast";
import { documentsApi } from "../../api/documents";
import type { DocumentSummary } from "../../types";

const INSTITUTION_LABELS: Record<string, string> = {
  morgan_stanley: "Morgan Stanley",
  chase: "Chase",
  etrade: "E*TRADE",
  amex: "American Express",
  discover: "Discover",
  bofa: "Bank of America",
  marcus: "Marcus",
  unknown: "Unknown",
};

function statusIcon(status: DocumentSummary["status"]) {
  switch (status) {
    case "parsed":     return <CheckCircle2 size={13} className="text-emerald-400 shrink-0" />;
    case "processing": return <Loader2 size={13} className="animate-spin shrink-0" style={{ color: "rgba(34,211,238,0.55)" }} />;
    case "failed":     return <AlertCircle size={13} className="shrink-0" style={{ color: "#FF7A5A" }} />;
    default:           return <Clock size={13} className="shrink-0" style={{ color: "var(--text-muted)" }} />;
  }
}

function statusLabel(status: DocumentSummary["status"]) {
  switch (status) {
    case "parsed":     return "Parsed";
    case "processing": return "Processing…";
    case "failed":     return "Failed";
    default:           return "Uploaded";
  }
}

interface Props {
  open: boolean;
  onClose: () => void;
}

export function DocumentsModal({ open, onClose }: Props) {
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionId, setActionId] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const data = await documentsApi.list(100);
      setDocs(data.sort((a, b) =>
        new Date(b.upload_time ?? 0).getTime() - new Date(a.upload_time ?? 0).getTime()
      ));
    } catch {
      toast.error("Failed to load documents");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (open) load();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  async function handleReingest(doc_id: string) {
    setActionId(doc_id);
    try {
      await documentsApi.reingest(doc_id);
      toast.success("Re-parsing in background…");
      await load();
    } catch {
      toast.error("Reingest failed");
    } finally {
      setActionId(null);
    }
  }

  async function handleDelete(doc_id: string, filename: string) {
    if (!confirm(`Delete "${filename}"? This removes all extracted data too.`)) return;
    setActionId(doc_id);
    try {
      await documentsApi.delete(doc_id);
      toast.success("Document deleted");
      await load();
    } catch {
      toast.error("Delete failed");
    } finally {
      setActionId(null);
    }
  }

  if (!open) return null;

  const parsed     = docs.filter((d) => d.status === "parsed").length;
  const processing = docs.filter((d) => d.status === "processing").length;
  const failed     = docs.filter((d) => d.status === "failed").length;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "var(--modal-overlay)", backdropFilter: "blur(8px)" }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <AnimatePresence>
        <motion.div
          key="docs-modal"
          initial={{ opacity: 0, scale: 0.96, y: 12 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: 12 }}
          transition={{ type: "spring", stiffness: 320, damping: 28 }}
          className="relative w-full max-w-lg rounded-3xl overflow-hidden shadow-2xl flex flex-col"
          style={{
            background: "var(--modal-bg)",
            backdropFilter: "blur(20px)",
            WebkitBackdropFilter: "blur(20px)",
            border: "1px solid var(--modal-border)",
            boxShadow: "var(--modal-shadow)",
            maxHeight: "80vh",
          }}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-6 pt-6 pb-4 shrink-0" style={{ borderBottom: "1px solid var(--panel-border)" }}>
            <div>
              <h2 className="text-lg font-bold" style={{ color: "var(--text-primary)" }}>Documents</h2>
              <p className="text-xs mt-0.5" style={{ color: "rgba(34,211,238,0.65)" }}>
                {docs.length} total · {parsed} parsed
                {processing > 0 ? ` · ${processing} processing` : ""}
                {failed > 0 ? ` · ${failed} failed` : ""}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={load}
                disabled={loading}
                className="rounded-full p-1.5 transition-colors disabled:opacity-40"
                style={{ color: "var(--text-muted)" }}
              >
                <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
              </button>
              <button
                onClick={onClose}
                className="rounded-full p-1.5 transition-colors"
                style={{ color: "var(--text-muted)" }}
              >
                <X size={18} />
              </button>
            </div>
          </div>

          {/* Document list */}
          <div className="flex-1 overflow-y-auto px-6 pb-6 pt-4">
            {loading && docs.length === 0 ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 size={22} className="animate-spin" style={{ color: "rgba(34,211,238,0.40)" }} />
              </div>
            ) : docs.length === 0 ? (
              <div className="text-center py-12">
                <FileText size={32} className="mx-auto mb-3" style={{ color: "var(--empty-icon)" }} />
                <p className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>No documents yet</p>
                <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>Upload a statement to get started</p>
              </div>
            ) : (
              <div className="space-y-2">
                {docs.map((doc) => (
                  <div
                    key={doc.id}
                    className="flex items-start gap-3 p-3 rounded-2xl"
                    style={{
                      background: "var(--row-bg)",
                      border: "1px solid var(--row-border)",
                    }}
                  >
                    {statusIcon(doc.status)}

                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-semibold truncate leading-tight" style={{ color: "var(--text-primary)" }}>
                        {doc.filename}
                      </p>
                      <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                        <span className="text-[10px]" style={{ color: "rgba(34,211,238,0.65)" }}>
                          {INSTITUTION_LABELS[doc.institution] ?? doc.institution}
                        </span>
                        <span className="text-[10px]" style={{ color: "var(--text-dim)" }}>·</span>
                        <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>{statusLabel(doc.status)}</span>
                        {doc.statement_count > 0 && (
                          <>
                            <span className="text-[10px]" style={{ color: "var(--text-dim)" }}>·</span>
                            <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>
                              {doc.statement_count} statement{doc.statement_count > 1 ? "s" : ""}
                            </span>
                          </>
                        )}
                      </div>
                      {doc.status === "failed" && doc.error && (
                        <p className="text-[10px] mt-0.5 truncate" style={{ color: "#FF7A5A" }}>{doc.error}</p>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1 shrink-0">
                      {(doc.status === "parsed" || doc.status === "failed") && (
                        <button
                          onClick={() => handleReingest(doc.id)}
                          disabled={actionId === doc.id}
                          className="p-1.5 rounded-lg transition-colors disabled:opacity-40"
                          style={{ color: "var(--text-muted)" }}
                          title="Re-parse"
                        >
                          {actionId === doc.id ? (
                            <Loader2 size={12} className="animate-spin" />
                          ) : (
                            <RefreshCw size={12} />
                          )}
                        </button>
                      )}
                      <button
                        onClick={() => handleDelete(doc.id, doc.filename)}
                        disabled={actionId === doc.id}
                        className="p-1.5 rounded-lg transition-colors disabled:opacity-40"
                        style={{ color: "var(--text-dim)" }}
                        title="Delete"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
