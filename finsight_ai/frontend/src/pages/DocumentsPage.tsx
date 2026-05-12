import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import { FileText, Trash2, RefreshCw, Loader2, CheckCircle2, XCircle, Clock, Upload } from "lucide-react";
import toast from "react-hot-toast";
import { documentsApi } from "../api/documents";
import type { DocumentSummary } from "../types";
import { useAppStore } from "../store/appStore";
import { UploadModal } from "../components/upload/UploadModal";
import { staggerContainer, staggerChild, contentPageVariants } from "../design/motion";

const STATUS_CONFIG: Record<string, { icon: React.ReactNode; label: string; color: string }> = {
  parsed:     { icon: <CheckCircle2 size={12} />, label: "Parsed",     color: "#4CAF93" },
  processing: { icon: <Loader2 size={12} className="animate-spin" />, label: "Processing", color: "#1F6F8B" },
  uploaded:   { icon: <Clock size={12} />,        label: "Uploaded",   color: "#c89a00" },
  failed:     { icon: <XCircle size={12} />,      label: "Failed",     color: "#E45757" },
};

function PageHeader({ onUpload, count }: { onUpload: () => void; count: number }) {
  return (
    <div
      className="shrink-0 px-7 py-4 flex items-center justify-between"
      style={{
        borderBottom: "1px solid rgba(205,237,246,0.50)",
        background: "rgba(255,255,255,0.55)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
      }}
    >
      <div>
        <h1 className="text-[18px] font-bold text-ocean-deep tracking-tight">Documents</h1>
        <p className="text-[12px] text-ocean/40 mt-0.5 font-medium">
          {count > 0 ? `${count} statement${count !== 1 ? "s" : ""} processed` : "No documents yet"}
        </p>
      </div>
      <motion.button
        whileHover={{ scale: 1.03 }}
        whileTap={{ scale: 0.97 }}
        onClick={onUpload}
        className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-[13px] font-semibold text-white"
        style={{
          background: "linear-gradient(135deg, #FF7A5A, #FFA38F)",
          boxShadow: "0 4px 14px rgba(255,122,90,0.32)",
        }}
      >
        <Upload size={13} />
        Upload
      </motion.button>
    </div>
  );
}

function DocRow({ doc, onDelete, onReingest }: {
  doc: DocumentSummary;
  onDelete: () => void;
  onReingest: () => void;
}) {
  const statusCfg = STATUS_CONFIG[doc.status] ?? STATUS_CONFIG.uploaded;
  const [deleting, setDeleting]   = useState(false);
  const [reingesting, setReingesting] = useState(false);

  const handleDelete = async () => {
    if (!confirm(`Delete "${doc.filename}"? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      await documentsApi.delete(doc.id);
      toast.success("Document deleted");
      onDelete();
    } catch {
      toast.error("Failed to delete");
    } finally {
      setDeleting(false);
    }
  };

  const handleReingest = async () => {
    setReingesting(true);
    try {
      await documentsApi.reingest(doc.id);
      toast.success("Re-ingestion started");
      onReingest();
    } catch {
      toast.error("Re-ingest failed");
    } finally {
      setReingesting(false);
    }
  };

  return (
    <motion.div
      variants={staggerChild}
      className="flex items-center justify-between px-5 py-3.5 border-b border-ocean-50/50 last:border-0 hover:bg-ocean-50/25 transition-colors"
    >
      <div className="flex items-center gap-3.5 min-w-0">
        <div className="p-2 rounded-xl shrink-0"
          style={{ background: "rgba(31,111,139,0.08)", color: "#1F6F8B" }}>
          <FileText size={14} />
        </div>
        <div className="min-w-0">
          <p className="text-[13px] font-medium text-ocean-deep truncate">{doc.filename}</p>
          <p className="text-[10px] text-ocean/40 mt-0.5">
            {doc.institution && <span className="capitalize">{doc.institution} · </span>}
            {doc.page_count !== null && <span>{doc.page_count}p · </span>}
            {doc.statement_count > 0 && <span>{doc.statement_count} stmt · </span>}
            {doc.upload_time && new Date(doc.upload_time).toLocaleDateString()}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2.5 shrink-0 ml-4">
        {/* Status badge */}
        <span
          className="flex items-center gap-1 text-[10px] font-semibold px-2 py-1 rounded-full"
          style={{
            background: `${statusCfg.color}14`,
            color: statusCfg.color,
          }}
        >
          {statusCfg.icon}
          {statusCfg.label}
        </span>

        {/* Actions */}
        {doc.status === "failed" && (
          <button
            onClick={handleReingest}
            disabled={reingesting}
            className="p-1.5 rounded-lg text-ocean/35 hover:text-ocean transition-colors disabled:opacity-40"
            title="Re-ingest"
          >
            {reingesting ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
          </button>
        )}
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="p-1.5 rounded-lg text-ocean/25 hover:text-negative/70 transition-colors disabled:opacity-40"
          title="Delete"
        >
          {deleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
        </button>
      </div>
    </motion.div>
  );
}

export function DocumentsPage() {
  const { ingestionJobs } = useAppStore();
  const [docs, setDocs]         = useState<DocumentSummary[]>([]);
  const [loading, setLoading]   = useState(true);
  const [uploadOpen, setUploadOpen] = useState(false);

  const fetchDocs = useCallback(async () => {
    try { setDocs(await documentsApi.list(100)); }
    catch { /* backend not ready */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchDocs(); }, [fetchDocs]);

  // Auto-refresh when ingestion jobs finish
  useEffect(() => {
    const hasProcessing = ingestionJobs.some(j => j.status === "processing");
    if (!hasProcessing) fetchDocs();
  }, [ingestionJobs, fetchDocs]);

  const byStatus = {
    parsed:     docs.filter(d => d.status === "parsed"),
    processing: docs.filter(d => d.status === "processing"),
    uploaded:   docs.filter(d => d.status === "uploaded"),
    failed:     docs.filter(d => d.status === "failed"),
  };

  return (
    <div className="flex flex-col h-full">
      <PageHeader onUpload={() => setUploadOpen(true)} count={docs.length} />

      <motion.div
        variants={contentPageVariants}
        initial="hidden"
        animate="visible"
        className="flex-1 overflow-y-auto px-7 py-6 space-y-5"
      >

        {/* Status summary strip */}
        {!loading && docs.length > 0 && (
          <motion.div variants={staggerChild}>
            <div className="grid grid-cols-4 gap-3">
              {(["parsed", "processing", "uploaded", "failed"] as const).map((status) => {
                const cfg = STATUS_CONFIG[status];
                return (
                  <div key={status} className="rounded-2xl p-3 text-center"
                    style={{ background: "rgba(255,255,255,0.82)", border: "1px solid rgba(205,237,246,0.60)" }}>
                    <div className="flex items-center justify-center mb-1" style={{ color: cfg.color }}>
                      {cfg.icon}
                    </div>
                    <p className="text-[18px] font-bold text-ocean-deep tabular">{byStatus[status].length}</p>
                    <p className="text-[10px] text-ocean/35 font-medium mt-0.5">{cfg.label}</p>
                  </div>
                );
              })}
            </div>
          </motion.div>
        )}

        {loading ? (
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="rounded-2xl h-14 animate-pulse"
                style={{ background: "rgba(205,237,246,0.20)" }} />
            ))}
          </div>
        ) : docs.length === 0 ? (
          <motion.div variants={staggerChild}>
            <div className="rounded-2xl px-6 py-12 text-center"
              style={{ background: "rgba(255,255,255,0.65)", border: "1px dashed rgba(205,237,246,0.70)" }}>
              <div className="text-3xl mb-3">📄</div>
              <p className="text-[14px] font-semibold text-ocean-deep mb-1.5">No documents yet</p>
              <p className="text-[12px] text-ocean/40 max-w-xs mx-auto leading-relaxed mb-4">
                Upload your first PDF statement to get started. Coral parses it locally — nothing leaves your device.
              </p>
              <button
                onClick={() => setUploadOpen(true)}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-[13px] font-semibold text-white"
                style={{ background: "linear-gradient(135deg, #FF7A5A, #FFA38F)" }}
              >
                <Upload size={13} />
                Upload a statement
              </button>
            </div>
          </motion.div>
        ) : (
          <motion.div
            variants={staggerChild}
            className="rounded-2xl overflow-hidden"
            style={{
              background: "rgba(255,255,255,0.85)",
              border: "1px solid rgba(205,237,246,0.65)",
              boxShadow: "0 4px 24px rgba(11,60,93,0.07)",
            }}
          >
            {/* Failed first (need attention) */}
            {byStatus.failed.length > 0 && (
              <>
                <div className="px-5 py-2.5 border-b border-ocean-50/50"
                  style={{ background: "rgba(228,87,87,0.05)" }}>
                  <p className="text-[10px] font-semibold text-negative/60 uppercase tracking-widest">
                    Failed · needs attention
                  </p>
                </div>
                <motion.div variants={staggerContainer} initial="hidden" animate="visible">
                  {byStatus.failed.map(doc => (
                    <DocRow key={doc.id} doc={doc} onDelete={fetchDocs} onReingest={fetchDocs} />
                  ))}
                </motion.div>
              </>
            )}

            {/* Processing */}
            {byStatus.processing.length > 0 && (
              <>
                <div className="px-5 py-2.5 border-b border-ocean-50/50"
                  style={{ background: "rgba(31,111,139,0.04)" }}>
                  <p className="text-[10px] font-semibold text-ocean/40 uppercase tracking-widest">
                    Processing
                  </p>
                </div>
                <motion.div variants={staggerContainer} initial="hidden" animate="visible">
                  {byStatus.processing.map(doc => (
                    <DocRow key={doc.id} doc={doc} onDelete={fetchDocs} onReingest={fetchDocs} />
                  ))}
                </motion.div>
              </>
            )}

            {/* Parsed */}
            {byStatus.parsed.length > 0 && (
              <>
                <div className="px-5 py-2.5 border-b border-ocean-50/50"
                  style={{ background: "rgba(76,175,147,0.04)" }}>
                  <p className="text-[10px] font-semibold text-positive/50 uppercase tracking-widest">
                    Parsed · {byStatus.parsed.length}
                  </p>
                </div>
                <motion.div variants={staggerContainer} initial="hidden" animate="visible">
                  {byStatus.parsed.map(doc => (
                    <DocRow key={doc.id} doc={doc} onDelete={fetchDocs} onReingest={fetchDocs} />
                  ))}
                </motion.div>
              </>
            )}

            {/* Uploaded but not parsed */}
            {byStatus.uploaded.length > 0 && (
              <>
                <div className="px-5 py-2.5 border-b border-ocean-50/50">
                  <p className="text-[10px] font-semibold text-ocean/30 uppercase tracking-widest">
                    Uploaded · pending parse
                  </p>
                </div>
                <motion.div variants={staggerContainer} initial="hidden" animate="visible">
                  {byStatus.uploaded.map(doc => (
                    <DocRow key={doc.id} doc={doc} onDelete={fetchDocs} onReingest={fetchDocs} />
                  ))}
                </motion.div>
              </>
            )}
          </motion.div>
        )}

        <div className="h-3" />
      </motion.div>

      <UploadModal
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onUploaded={() => { setUploadOpen(false); fetchDocs(); }}
      />
    </div>
  );
}
