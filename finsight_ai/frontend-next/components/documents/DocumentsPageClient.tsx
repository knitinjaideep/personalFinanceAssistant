"use client";

import { useState, useMemo, useCallback } from "react";
import {
  Upload, RefreshCw, Loader2, AlertTriangle, Lock, Wand2, FileText,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import toast from "react-hot-toast";

import { useDocuments } from "@/features/documents/hooks";
import { documentsApi } from "@/features/documents/api";
import { useAppStore } from "@/store/appStore";
import MetricCard from "@/components/coral/MetricCard";
import SectionHeader from "@/components/coral/SectionHeader";
import GlassCard from "@/components/coral/GlassCard";
import type { DocumentSummary, DocumentIssue, IngestionHealth } from "@/types/index";

import DocumentStatusBadge from "./DocumentStatusBadge";
import StatementCoverageGrid from "./StatementCoverageGrid";
import InstitutionCard from "./InstitutionCard";
import NeedsAttentionView from "./NeedsAttentionView";
import TimelineView from "./TimelineView";
import StatementDetailDrawer from "./StatementDetailDrawer";
import { groupDocumentsByInstitution, findDocumentsNeedingAttention, getRecentlyAddedDocuments, relativeTime } from "@/lib/documentLibrary";

// ── Tab types ─────────────────────────────────────────────────────────────────

type Tab = "library" | "needs_attention" | "timeline" | "raw_files";

const TABS: Array<{ id: Tab; label: string; shortLabel: string }> = [
  { id: "library",         label: "Library",         shortLabel: "Library" },
  { id: "needs_attention", label: "Needs Attention",  shortLabel: "Attention" },
  { id: "timeline",        label: "Timeline",         shortLabel: "Timeline" },
  { id: "raw_files",       label: "Raw Files",        shortLabel: "Raw" },
];

// ── Tab bar ───────────────────────────────────────────────────────────────────

function TabBar({ active, onChange, attentionCount }: { active: Tab; onChange: (t: Tab) => void; attentionCount: number }) {
  return (
    <div className="flex items-center gap-1 p-1 rounded-2xl shrink-0"
      style={{ background: "var(--glass-dark-bg)", border: "1px solid var(--border-subtle)", backdropFilter: "blur(12px)" }}>
      {TABS.map((tab) => {
        const isActive = tab.id === active;
        return (
          <button key={tab.id} onClick={() => onChange(tab.id)}
            className="relative flex items-center gap-1.5 px-3.5 py-2.5 rounded-xl text-[12px] font-semibold transition-all duration-200"
            style={{
              background: isActive ? "var(--accent-soft)" : "transparent",
              color: isActive ? "var(--accent-strong)" : "var(--text-muted)",
              boxShadow: isActive ? "0 0 16px var(--accent-glow-soft), inset 0 1px 0 var(--accent-soft)" : "none",
              border: isActive ? "1px solid var(--border-accent)" : "1px solid transparent",
            }}>
            <span className="hidden sm:inline">{tab.label}</span>
            <span className="sm:hidden">{tab.shortLabel}</span>
            {tab.id === "needs_attention" && attentionCount > 0 && (
              <span className="inline-flex items-center justify-center w-4 h-4 rounded-full text-[9.5px] font-bold leading-none"
                style={{ background: "var(--warning-strong)", color: "var(--text-on-warning)" }}>
                {attentionCount > 9 ? "9+" : attentionCount}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

// ── Library view (coverage + institution cards + recently added) ──────────────

function LibraryView({ docs, onChanged, onDocClick, issuesByDoc }: {
  docs: DocumentSummary[]; onChanged: () => void;
  onDocClick: (d: DocumentSummary) => void; issuesByDoc?: Record<string, DocumentIssue>;
}) {
  const institutions = groupDocumentsByInstitution(docs);
  const recent = getRecentlyAddedDocuments(docs, 6);

  if (docs.length === 0) {
    return (
      <div className="rounded-2xl px-6 py-12 text-center"
        style={{ background: "var(--empty-bg)", border: "1px dashed var(--border-subtle)" }}>
        <div className="w-12 h-12 rounded-2xl flex items-center justify-center mx-auto mb-3"
          style={{ background: "var(--accent-soft)", color: "var(--accent-strong)" }}>
          <FileText size={22} />
        </div>
        <p className="text-[13px] font-semibold mb-1" style={{ color: "var(--text-primary)" }}>No statements uploaded yet</p>
        <p className="text-[11.5px]" style={{ color: "var(--text-muted)" }}>
          Upload your first statement and Coral will organize it by institution, account, and month.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-7">
      <div>
        <p className="text-[12px] font-semibold uppercase tracking-wider mb-3" style={{ color: "var(--text-dim)" }}>
          Statement Coverage
        </p>
        <div className="rounded-2xl p-5"
          style={{ background: "var(--panel-bg)", border: "1px solid var(--panel-border)", backdropFilter: "blur(16px)" }}>
          <StatementCoverageGrid docs={docs} />
        </div>
      </div>

      <div>
        <p className="text-[12px] font-semibold uppercase tracking-wider mb-3" style={{ color: "var(--text-dim)" }}>Institutions</p>
        <div className="space-y-3">
          {institutions.map((inst) => (
            <InstitutionCard key={inst.slug} institution={inst} onChanged={onChanged} onDocClick={onDocClick} issuesByDoc={issuesByDoc} />
          ))}
        </div>
      </div>

      {recent.length > 0 && (
        <div>
          <p className="text-[12px] font-semibold uppercase tracking-wider mb-3" style={{ color: "var(--text-dim)" }}>Recently Added</p>
          <div className="space-y-1.5">
            {recent.map((doc) => (
              <button key={doc.id} onClick={() => onDocClick(doc)}
                className="w-full flex items-center gap-3 px-4 py-3 rounded-2xl transition-colors text-left"
                style={{ background: "var(--panel-bg)", border: "1px solid var(--panel-border)" }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "var(--row-bg)")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "var(--panel-bg)")}>
                <div className="w-7 h-7 rounded-xl flex items-center justify-center shrink-0"
                  style={{ background: "var(--accent-soft)", color: "var(--accent-strong)" }}>
                  <FileText size={12} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-[12px] font-semibold truncate" style={{ color: "var(--text-primary)" }}>{doc.filename}</p>
                  <p className="text-[10px]" style={{ color: "var(--text-dim)" }}>{relativeTime(doc.upload_time)}</p>
                </div>
                <DocumentStatusBadge status={doc.status as "parsed"|"processing"|"uploaded"|"failed"} size="xs" />
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Raw files view ────────────────────────────────────────────────────────────

function RawFilesView({ docs, onChanged, onDocClick, issuesByDoc }: {
  docs: DocumentSummary[]; onChanged: () => void;
  onDocClick: (d: DocumentSummary) => void; issuesByDoc?: Record<string, DocumentIssue>;
}) {
  const sorted = [...docs].sort((a, b) =>
    new Date(b.upload_time ?? 0).getTime() - new Date(a.upload_time ?? 0).getTime()
  );

  return (
    <div className="space-y-1.5">
      {sorted.map((doc) => {
        const issue = issuesByDoc?.[doc.id];
        return (
          <button key={doc.id} onClick={() => onDocClick(doc)}
            className="w-full flex items-center gap-3 px-4 py-3.5 rounded-2xl transition-colors text-left"
            style={{ background: "var(--panel-bg)", border: "1px solid var(--panel-border)" }}
            onMouseEnter={(e) => (e.currentTarget.style.background = "var(--row-bg)")}
            onMouseLeave={(e) => (e.currentTarget.style.background = "var(--panel-bg)")}>
            <div className="w-7 h-7 rounded-xl flex items-center justify-center shrink-0"
              style={{ background: "var(--accent-soft)", color: "var(--accent-strong)" }}>
              <FileText size={12} />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[12.5px] font-semibold truncate" style={{ color: "var(--text-primary)" }}>{doc.filename}</p>
              <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                {doc.upload_time && (
                  <span className="text-[10px]" style={{ color: "var(--text-dim)" }}>{relativeTime(doc.upload_time)}</span>
                )}
                {issue?.issues.length ? (
                  <span className="flex items-center gap-0.5 text-[9.5px] font-medium px-1.5 py-0.5 rounded-full"
                    style={{ background: "rgba(200,154,0,0.10)", color: "#c89a00" }}>
                    <AlertTriangle size={8} />{issue.issues.length} issue{issue.issues.length !== 1 ? "s" : ""}
                  </span>
                ) : null}
                {doc.error && (
                  <span className="text-[10px] truncate max-w-[200px]" style={{ color: "#E45757" }}>{doc.error}</span>
                )}
              </div>
            </div>
            <DocumentStatusBadge status={doc.status as "parsed"|"processing"|"uploaded"|"failed"} size="xs" />
          </button>
        );
      })}
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────

interface Props { compact?: boolean }

export default function DocumentsPageClient({ compact }: Props) {
  const { docs, loading, error, refetch, polling } = useDocuments();
  const openUploadModal = useAppStore((s) => s.openUploadModal);
  const [ingestionHealth, setIngestionHealth] = useState<IngestionHealth | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>("library");
  const [selectedDoc, setSelectedDoc] = useState<DocumentSummary | null>(null);
  const [reprocessingMissing, setReprocessingMissing] = useState(false);

  // issuesByDoc is derived from ingestionHealth
  const issuesByDoc = useMemo<Record<string, DocumentIssue>>(() => {
    if (!ingestionHealth) return {};
    return Object.fromEntries(ingestionHealth.documents.map((d) => [d.document_id, d]));
  }, [ingestionHealth]);

  const fetchHealth = useCallback(async () => {
    setHealthLoading(true);
    try {
      const h = await documentsApi.ingestionHealth();
      setIngestionHealth(h);
    } catch { /* non-fatal */ }
    finally { setHealthLoading(false); }
  }, []);

  const refreshAll = useCallback(async () => {
    const dev = process.env.NODE_ENV === "development";
    if (dev) console.time("documents-refresh");
    try {
      await Promise.all([refetch(), fetchHealth()]);
    } finally {
      if (dev) console.timeEnd("documents-refresh");
    }
  }, [refetch, fetchHealth]);

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

  const attentionCount = useMemo(() => findDocumentsNeedingAttention(docs, issuesByDoc).length, [docs, issuesByDoc]);

  const stats = useMemo(() => ({
    total:      docs.length,
    parsed:     docs.filter((d) => d.status === "parsed").length,
    processing: docs.filter((d) => d.status === "processing").length,
    failed:     docs.filter((d) => d.status === "failed").length,
    uploaded:   docs.filter((d) => d.status === "uploaded").length,
    lastUpload: docs.map((d) => d.upload_time ? new Date(d.upload_time).getTime() : 0).reduce((a, b) => Math.max(a, b), 0),
  }), [docs]);

  // ── Loading / error ───────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="space-y-10">
        <SectionHeader eyebrow="Library" title="Documents" size="lg" />
        <div className="space-y-2.5">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="rounded-2xl h-16 animate-pulse" style={{ background: "var(--panel-bg)" }} />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-10">
        <SectionHeader eyebrow="Library" title="Documents" size="lg" />
        <div className="flex items-center gap-2 rounded-2xl px-4 py-3 text-[12px] font-medium"
          style={{ background: "rgba(228,87,87,0.08)", border: "1px solid rgba(228,87,87,0.25)", color: "#E45757" }}>
          <AlertTriangle size={14} />
          <span>{error}</span>
          <button onClick={refetch} className="underline underline-offset-2 ml-1">Retry</button>
        </div>
      </div>
    );
  }

  if (docs.length === 0) {
    return (
      <div className="space-y-10">
        <SectionHeader eyebrow="Library" title="Documents"
          description="Your statements and financial documents, organized by institution, account, and year."
          size="lg" />
        <GlassCard variant="default" className="flex flex-col items-center py-16 text-center">
          <div className="w-14 h-14 rounded-2xl flex items-center justify-center mb-4"
            style={{ background: "var(--accent-soft)", color: "var(--accent-strong)" }}>
            <FileText size={26} />
          </div>
          <p className="text-[15px] font-bold mb-1.5" style={{ color: "var(--text-primary)" }}>
            Your financial library is empty
          </p>
          <p className="text-[12.5px] mb-6" style={{ color: "var(--text-muted)" }}>
            Upload your first statement. Coral will organize it by institution, account, and month.
          </p>
          <button type="button" onClick={openUploadModal}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-[13px] font-semibold text-white btn-coral">
            <Upload size={13} /> Upload a Statement
          </button>
        </GlassCard>
      </div>
    );
  }

  // ── Full page ─────────────────────────────────────────────────────────────

  return (
    <div className="space-y-10">

      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="flex items-center gap-2.5 mb-2">
            <div className="flex items-center justify-center w-9 h-9 rounded-2xl shrink-0"
              style={{ background: "var(--accent-soft)", border: "1px solid var(--border-accent)", color: "var(--accent-strong)" }}>
              <FileText size={17} />
            </div>
            <h1 className="page-title">Financial Library</h1>
          </div>
          <p className="body-text pl-11" style={{ color: "var(--text-secondary)" }}>
            {docs.length > 0
              ? `${docs.length} statement${docs.length !== 1 ? "s" : ""} · organized locally by institution, account, and time.`
              : "Your statements, organized locally by institution, account, and time."}
          </p>
          <div className="flex items-center gap-1.5 pl-11 mt-1">
            <Lock size={11} style={{ color: "var(--accent-strong)" }} />
            <span className="text-[11px] font-medium" style={{ color: "var(--accent-strong)" }}>All files stay on your device.</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0 mt-1">
          <button onClick={handleReprocessMissing} disabled={reprocessingMissing}
            className="flex items-center gap-1.5 px-3.5 py-2.5 rounded-xl text-[12px] font-semibold transition-all hover:scale-[1.02] disabled:opacity-50"
            style={{ background: "var(--coral-soft)", border: "1px solid var(--coral-border)", color: "var(--coral-text)" }}>
            <Wand2 size={13} />Reprocess Missing Data
          </button>
          {polling && (
            <span className="small-text flex items-center gap-1.5" style={{ color: "var(--accent-strong)" }}>
              <Loader2 size={12} className="animate-spin" /> Polling for updates
            </span>
          )}
          <button onClick={refreshAll}
            className="flex items-center gap-1.5 text-sm px-3.5 py-2 rounded-xl btn-glass"
            style={{ color: "var(--text-muted)" }}>
            <RefreshCw size={13} /> Refresh
          </button>
          <button type="button" onClick={openUploadModal} className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-xl text-white font-semibold btn-coral">
            <Upload size={13} /> Upload more
          </button>
        </div>
      </div>

      {/* Status summary */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
        {[
          { title: "Total",      value: String(stats.total),      accent: "rgba(34,211,238,0.14)" },
          { title: "Parsed",     value: String(stats.parsed),     accent: "rgba(76,175,147,0.14)",  status: "positive" as const },
          { title: "Processing", value: String(stats.processing), accent: "rgba(255,209,102,0.14)", status: "warning" as const },
          { title: "Failed",     value: String(stats.failed),     accent: "rgba(228,87,87,0.14)",   status: "negative" as const },
          { title: "Pending",    value: String(stats.uploaded),   accent: "rgba(34,211,238,0.08)" },
          { title: "Last Upload", value: stats.lastUpload > 0 ? new Date(stats.lastUpload).toLocaleDateString() : undefined, accent: "rgba(34,211,238,0.08)", emptyText: "No uploads" },
        ].map((m) => (
          <MetricCard key={m.title} title={m.title} value={m.value} status={m.status} accentColor={m.accent} emptyText={m.emptyText} size="sm" />
        ))}
      </div>

      {/* Reprocess banner */}
      {(ingestionHealth?.summary.incomplete_documents ?? 0) + stats.failed > 0 && (
        <div className="flex items-center gap-3 rounded-2xl px-4 py-3"
          style={{ background: "var(--warn-bg)", border: "1px solid var(--warn-border)" }}>
          <AlertTriangle size={14} style={{ color: "var(--warn-text)" }} />
          <p className="text-[12px] font-medium flex-1" style={{ color: "var(--warn-text)" }}>
            {((ingestionHealth?.summary.incomplete_documents ?? 0) + stats.failed)} document{((ingestionHealth?.summary.incomplete_documents ?? 0) + stats.failed) !== 1 ? "s" : ""} may have incomplete data.
          </p>
          <button onClick={handleReprocessMissing} disabled={reprocessingMissing}
            className="flex items-center gap-1 text-[11.5px] font-semibold px-3 py-1.5 rounded-xl transition-all disabled:opacity-50"
            style={{ background: "var(--warn-border)", color: "var(--warn-text)" }}>
            {reprocessingMissing ? <Loader2 size={11} className="animate-spin" /> : <Wand2 size={11} />}
            Fix Now
          </button>
        </div>
      )}

      {/* Tab bar + content */}
      <div className="space-y-5">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <TabBar active={activeTab} onChange={setActiveTab} attentionCount={attentionCount} />
          <button onClick={refreshAll}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-[12px] font-medium transition-all hover:scale-[1.02] btn-glass"
            style={{ color: "var(--text-muted)" }}>
            <RefreshCw size={12} />Refresh
          </button>
        </div>

        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.18 }}
          >
            {activeTab === "library" && (
              <LibraryView docs={docs} onChanged={refreshAll} onDocClick={setSelectedDoc} issuesByDoc={issuesByDoc} />
            )}
            {activeTab === "needs_attention" && (
              <NeedsAttentionView docs={docs} onChanged={refreshAll} onDocClick={setSelectedDoc} issuesByDoc={issuesByDoc} />
            )}
            {activeTab === "timeline" && (
              <TimelineView docs={docs} onDocClick={setSelectedDoc} />
            )}
            {activeTab === "raw_files" && (
              <RawFilesView docs={docs} onChanged={refreshAll} onDocClick={setSelectedDoc} issuesByDoc={issuesByDoc} />
            )}
          </motion.div>
        </AnimatePresence>
      </div>

      {/* Upload CTA */}
      <GlassCard variant="subtle" className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <p className="card-title-lg mb-1">Upload more documents</p>
          <p className="small-text" style={{ color: "var(--text-muted)" }}>
            Add statements to keep your financial picture up to date.
          </p>
        </div>
        <button type="button" onClick={openUploadModal} className="inline-flex items-center gap-2 px-6 py-3 rounded-2xl text-white font-semibold btn-coral shrink-0">
          <Upload size={15} /> Upload statements
        </button>
      </GlassCard>

      {/* Statement detail drawer */}
      <StatementDetailDrawer doc={selectedDoc} onClose={() => setSelectedDoc(null)}
        onChanged={() => { refreshAll(); setSelectedDoc(null); }} />
    </div>
  );
}
