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
    case "parsed":     return <CheckCircle2 size={13} className="text-emerald-500 shrink-0" />;
    case "processing": return <Loader2 size={13} className="text-ocean/50 animate-spin shrink-0" />;
    case "failed":     return <AlertCircle size={13} className="text-coral shrink-0" />;
    default:           return <Clock size={13} className="text-ocean/30 shrink-0" />;
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

  // Escape to close
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
      style={{ background: "rgba(11,60,93,0.55)", backdropFilter: "blur(6px)" }}
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
            background: "rgba(255,255,255,0.97)",
            border: "1px solid rgba(205,237,246,0.7)",
            maxHeight: "80vh",
          }}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-6 pt-6 pb-4 shrink-0">
            <div>
              <h2 className="text-lg font-bold text-ocean-900">Documents</h2>
              <p className="text-xs text-ocean/40 mt-0.5">
                {docs.length} total · {parsed} parsed
                {processing > 0 ? ` · ${processing} processing` : ""}
                {failed > 0 ? ` · ${failed} failed` : ""}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={load}
                disabled={loading}
                className="rounded-full p-1.5 text-ocean/30 hover:text-ocean/70 hover:bg-ocean-50 transition-colors disabled:opacity-40"
              >
                <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
              </button>
              <button
                onClick={onClose}
                className="rounded-full p-1.5 text-ocean/30 hover:text-ocean/70 hover:bg-ocean-50 transition-colors"
              >
                <X size={18} />
              </button>
            </div>
          </div>

          {/* Document list */}
          <div className="flex-1 overflow-y-auto px-6 pb-6">
            {loading && docs.length === 0 ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 size={22} className="animate-spin text-ocean/30" />
              </div>
            ) : docs.length === 0 ? (
              <div className="text-center py-12">
                <FileText size={32} className="mx-auto mb-3 text-ocean/20" />
                <p className="text-sm text-ocean/40 font-medium">No documents yet</p>
                <p className="text-xs text-ocean/30 mt-1">Upload a statement to get started</p>
              </div>
            ) : (
              <div className="space-y-2">
                {docs.map((doc) => (
                  <div
                    key={doc.id}
                    className="flex items-start gap-3 p-3 rounded-2xl"
                    style={{
                      background: "rgba(240,249,252,0.6)",
                      border: "1px solid rgba(205,237,246,0.5)",
                    }}
                  >
                    {statusIcon(doc.status)}

                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-semibold text-ocean-800 truncate leading-tight">
                        {doc.filename}
                      </p>
                      <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                        <span className="text-[10px] text-ocean/50">
                          {INSTITUTION_LABELS[doc.institution] ?? doc.institution}
                        </span>
                        <span className="text-[10px] text-ocean/30">·</span>
                        <span className="text-[10px] text-ocean/50">{statusLabel(doc.status)}</span>
                        {doc.statement_count > 0 && (
                          <>
                            <span className="text-[10px] text-ocean/30">·</span>
                            <span className="text-[10px] text-ocean/50">
                              {doc.statement_count} statement{doc.statement_count > 1 ? "s" : ""}
                            </span>
                          </>
                        )}
                      </div>
                      {doc.status === "failed" && doc.error && (
                        <p className="text-[10px] text-coral mt-0.5 truncate">{doc.error}</p>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1 shrink-0">
                      {(doc.status === "parsed" || doc.status === "failed") && (
                        <button
                          onClick={() => handleReingest(doc.id)}
                          disabled={actionId === doc.id}
                          className="p-1.5 rounded-lg text-ocean/30 hover:text-ocean/70 hover:bg-ocean-100 transition-colors disabled:opacity-40"
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
                        className="p-1.5 rounded-lg text-ocean/20 hover:text-coral/70 hover:bg-coral/5 transition-colors disabled:opacity-40"
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
