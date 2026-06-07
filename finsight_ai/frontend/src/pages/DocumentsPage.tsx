import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, RefreshCw } from "lucide-react";
import toast from "react-hot-toast";
import { useAppStore } from "../store/appStore";
import { UploadModal } from "../components/upload/UploadModal";
import { BulkUploadModal } from "../components/upload/BulkUploadModal";
import { useDocuments } from "../hooks/useDocuments";
import { useIngestionHealth } from "../hooks/useIngestionHealth";
import { documentsApi } from "../api/documents";
import { computeStats } from "../utils/documentUtils";
import { contentPageVariants, staggerChild } from "../design/motion";
import { CoralLoadingState } from "../components/CoralLoadingState";

import { FinancialLibraryHeader } from "../components/documents/FinancialLibraryHeader";
import { DocumentDataHealth } from "../components/documents/DocumentDataHealth";
import { StatementDetailDrawer } from "../components/documents/StatementDetailDrawer";
import { LibraryView } from "../components/documents/LibraryView";
import { NeedsAttentionView } from "../components/documents/NeedsAttentionView";
import { TimelineView } from "../components/documents/TimelineView";
import { RawFilesView } from "../components/documents/RawFilesView";
import { ReprocessToolbar } from "../components/documents/ReprocessToolbar";
import { computeLibraryHealth } from "../lib/documentLibrary";
import type { DocumentSummary } from "../types";

// ── Tab types ─────────────────────────────────────────────────────────────────

type Tab = "library" | "needs_attention" | "timeline" | "raw_files";

const TABS: Array<{ id: Tab; label: string; shortLabel: string }> = [
  { id: "library",          label: "Library",          shortLabel: "Library" },
  { id: "needs_attention",  label: "Needs Attention",  shortLabel: "Attention" },
  { id: "timeline",         label: "Timeline",         shortLabel: "Timeline" },
  { id: "raw_files",        label: "Raw Files",        shortLabel: "Raw" },
];

// ── Tab bar ───────────────────────────────────────────────────────────────────

function TabBar({
  active,
  onChange,
  attentionCount,
}: {
  active: Tab;
  onChange: (t: Tab) => void;
  attentionCount: number;
}) {
  return (
    <div
      className="flex items-center gap-1 p-1 rounded-2xl shrink-0"
      style={{
        background: "rgba(3,17,31,0.60)",
        border: "1px solid rgba(34,211,238,0.14)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
      }}
    >
      {TABS.map((tab) => {
        const isActive = tab.id === active;
        return (
          <button
            key={tab.id}
            onClick={() => onChange(tab.id)}
            className="relative flex items-center gap-1.5 px-3.5 py-2.5 rounded-xl coral-nav-text font-semibold transition-all duration-200"
            style={{
              background: isActive ? "rgba(34,211,238,0.14)" : "transparent",
              color: isActive ? "rgba(34,211,238,0.95)" : "var(--text-muted)",
              boxShadow: isActive ? "0 0 16px rgba(34,211,238,0.12), inset 0 1px 0 rgba(34,211,238,0.10)" : "none",
              border: isActive ? "1px solid rgba(34,211,238,0.22)" : "1px solid transparent",
            }}
          >
            <span className="hidden sm:inline">{tab.label}</span>
            <span className="sm:hidden">{tab.shortLabel}</span>
            {tab.id === "needs_attention" && attentionCount > 0 && (
              <span
                className="inline-flex items-center justify-center w-4 h-4 rounded-full coral-badge-text font-bold leading-none"
                style={{ background: "#c89a00", color: "#03111f" }}
              >
                {attentionCount > 9 ? "9+" : attentionCount}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function DocumentsPage() {
  const { ingestionJobs } = useAppStore();
  const { docs, loading, error, refetch, polling } = useDocuments();
  const { health, issuesByDoc, loading: healthLoading, refetch: refetchHealth } = useIngestionHealth();

  const [uploadOpen, setUploadOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>("library");
  const [selectedDoc, setSelectedDoc] = useState<DocumentSummary | null>(null);
  const [reprocessingMissing, setReprocessingMissing] = useState(false);

  // Refetch when an ingestion job transitions out of processing.
  const processingJobCount = ingestionJobs.filter((j) => j.status === "processing").length;
  useEffect(() => {
    refetch();
  }, [processingJobCount, refetch]);

  const refreshAll = () => {
    refetch();
    refetchHealth();
  };

  const handleReprocessMissing = async () => {
    setReprocessingMissing(true);
    try {
      const start = await documentsApi.reprocessMissingData();
      if (start.count === 0) {
        toast("Nothing to reprocess — all complete.");
      } else {
        toast.success(`Reprocessing ${start.count} document${start.count !== 1 ? "s" : ""}…`);
        setTimeout(refreshAll, 2000);
      }
    } catch {
      toast.error("Failed to start reprocessing");
    } finally {
      setReprocessingMissing(false);
    }
  };

  const stats = useMemo(() => computeStats(docs), [docs]);
  const libraryHealth = useMemo(() => computeLibraryHealth(docs, health), [docs, health]);

  const attentionCount = useMemo(() => {
    // quick count: failed + stuck (no full attention analysis needed for badge)
    return docs.filter((d) => {
      const s = d.status?.toLowerCase() ?? "";
      return s === "failed" || s === "error" || (issuesByDoc?.[d.id]?.issues?.length ?? 0) > 0;
    }).length;
  }, [docs, issuesByDoc]);

  return (
    <div className="flex flex-col h-full" style={{ background: "transparent" }}>
      {/* Header */}
      <FinancialLibraryHeader
        onUpload={() => setUploadOpen(true)}
        onBulkUpload={() => setBulkOpen(true)}
        onReprocessMissing={handleReprocessMissing}
        reprocessingMissing={reprocessingMissing}
        docCount={docs.length}
      />

      <motion.div
        variants={contentPageVariants}
        initial="hidden"
        animate="visible"
        className="flex-1 overflow-y-auto px-6 pb-8 space-y-4"
        style={{ background: "transparent" }}
      >
        {/* Error banner */}
        {error && (
          <motion.div
            variants={staggerChild}
            className="flex items-center gap-2 rounded-2xl px-4 py-3 text-[12px] font-medium"
            style={{ background: "rgba(228,87,87,0.08)", border: "1px solid rgba(228,87,87,0.25)", color: "#E45757" }}
          >
            <AlertTriangle size={14} />
            <span>Couldn't refresh documents ({error}).</span>
            <button onClick={refetch} className="underline underline-offset-2 ml-1">Retry</button>
          </motion.div>
        )}

        {/* Data health summary */}
        {!loading && docs.length > 0 && (
          <motion.div variants={staggerChild}>
            <DocumentDataHealth health={libraryHealth} loading={healthLoading} />
          </motion.div>
        )}

        {/* Reprocess toolbar — only shown when there's something to do */}
        {!loading && docs.length > 0 && (health?.summary.incomplete_documents ?? 0) + stats.failed > 0 && (
          <motion.div variants={staggerChild}>
            <ReprocessToolbar
              onDone={refreshAll}
              missingCount={health?.summary.incomplete_documents ?? 0}
              failedCount={health?.summary.failed ?? stats.failed}
            />
          </motion.div>
        )}

        {/* Processing live banner */}
        {!loading && docs.length > 0 && polling && (
          <motion.div variants={staggerChild}>
            <CoralLoadingState
              variant="documents"
              message="Coral is reading your statements…"
              submessage="Extracting transactions, chunks, and financial details."
            />
          </motion.div>
        )}

        {/* Tab bar + content */}
        {loading ? (
          <div className="space-y-3">
            <CoralLoadingState
              variant="documents"
              message="Loading your financial library…"
              submessage="Fetching statements and ingestion health."
            />
            <div className="space-y-2.5">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="rounded-2xl h-16 animate-pulse" style={{ background: "var(--empty-bg)" }} />
              ))}
            </div>
          </div>
        ) : docs.length === 0 ? (
          <EmptyLibrary onUpload={() => setUploadOpen(true)} />
        ) : (
          <>
            {/* Tab bar */}
            <motion.div variants={staggerChild} className="flex items-center justify-between gap-3 flex-wrap">
              <TabBar active={activeTab} onChange={setActiveTab} attentionCount={attentionCount} />
              <button
                onClick={() => { refetch(); refetchHealth(); }}
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-[12px] font-medium transition-all hover:scale-[1.02]"
                style={{
                  background: "var(--btn-glass-bg)",
                  border: "1px solid var(--btn-glass-border)",
                  color: "var(--btn-glass-color)",
                }}
              >
                <RefreshCw size={12} />
                Refresh
              </button>
            </motion.div>

            {/* Tab content */}
            <motion.div variants={staggerChild}>
              <AnimatePresence mode="wait">
                <motion.div
                  key={activeTab}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.18 }}
                >
                  {activeTab === "library" && (
                    <LibraryView
                      docs={docs}
                      onChanged={refreshAll}
                      onDocClick={setSelectedDoc}
                      issuesByDoc={issuesByDoc}
                    />
                  )}
                  {activeTab === "needs_attention" && (
                    <NeedsAttentionView
                      docs={docs}
                      onChanged={refreshAll}
                      onDocClick={setSelectedDoc}
                      issuesByDoc={issuesByDoc}
                    />
                  )}
                  {activeTab === "timeline" && (
                    <TimelineView
                      docs={docs}
                      onDocClick={setSelectedDoc}
                    />
                  )}
                  {activeTab === "raw_files" && (
                    <RawFilesView
                      docs={docs}
                      onChanged={refreshAll}
                      onDocClick={setSelectedDoc}
                      issuesByDoc={issuesByDoc}
                    />
                  )}
                </motion.div>
              </AnimatePresence>
            </motion.div>
          </>
        )}

        <div className="h-4" />
      </motion.div>

      {/* Statement detail drawer */}
      <StatementDetailDrawer
        doc={selectedDoc}
        onClose={() => setSelectedDoc(null)}
        onChanged={() => { refreshAll(); setSelectedDoc(null); }}
      />

      {/* Upload modals */}
      <UploadModal
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onUploaded={() => { setUploadOpen(false); refreshAll(); }}
      />
      <BulkUploadModal
        open={bulkOpen}
        onClose={() => setBulkOpen(false)}
        onUploaded={() => { setBulkOpen(false); refreshAll(); }}
      />
    </div>
  );
}

function EmptyLibrary({ onUpload }: { onUpload: () => void }) {
  return (
    <motion.div
      variants={staggerChild}
      className="rounded-3xl px-6 py-16 text-center"
      style={{
        background: "var(--panel-bg)",
        backdropFilter: "blur(16px)",
        border: "1px dashed var(--empty-border)",
      }}
    >
      <div
        className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4"
        style={{ background: "rgba(34,211,238,0.08)", color: "rgba(34,211,238,0.50)" }}
      >
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="12" y1="18" x2="12" y2="12" />
          <line x1="9" y1="15" x2="15" y2="15" />
        </svg>
      </div>
      <p className="text-[15px] font-bold mb-1.5" style={{ color: "var(--text-primary)" }}>
        Your financial library is empty
      </p>
      <p className="text-[12.5px] mb-6" style={{ color: "var(--text-muted)" }}>
        Upload your first statement. Coral will organize it by institution, account, and month.
      </p>
      <motion.button
        whileHover={{ scale: 1.03 }}
        whileTap={{ scale: 0.97 }}
        onClick={onUpload}
        className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-[13px] font-semibold text-white"
        style={{ background: "linear-gradient(135deg, #FF7A5A, #FFA38F)", boxShadow: "0 4px 18px rgba(255,122,90,0.35)" }}
      >
        Upload a Statement
      </motion.button>
    </motion.div>
  );
}
