import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Upload, AlertTriangle, RefreshCw, FolderUp } from "lucide-react";
import { useAppStore } from "../store/appStore";
import { UploadModal } from "../components/upload/UploadModal";
import { BulkUploadModal } from "../components/upload/BulkUploadModal";
import { DocumentStatsCards } from "../components/documents/DocumentStatsCards";
import { DocumentFilters } from "../components/documents/DocumentFilters";
import {
  DocumentBucketAccordion,
  instKey,
  acctKey,
  yearKey,
} from "../components/documents/DocumentBucketAccordion";
import { useDocuments } from "../hooks/useDocuments";
import { useIngestionHealth } from "../hooks/useIngestionHealth";
import { ReprocessToolbar } from "../components/documents/ReprocessToolbar";
import { IngestionHealthPanel } from "../components/documents/IngestionHealthPanel";
import {
  computeStats,
  groupDocuments,
  filterDocuments,
  EMPTY_FILTERS,
  type DocumentFilterState,
  type InstitutionGroup,
} from "../utils/documentUtils";
import { contentPageVariants, staggerChild } from "../design/motion";
import { CoralMascot } from "../components/CoralMascot";
import { CoralEmptyState } from "../components/CoralEmptyState";
import { CoralLoadingState } from "../components/CoralLoadingState";

function PageHeader({
  onUpload,
  onBulkUpload,
  onRefresh,
  refreshing,
  count,
}: {
  onUpload: () => void;
  onBulkUpload: () => void;
  onRefresh: () => void;
  refreshing: boolean;
  count: number;
}) {
  const secondaryBtn =
    "flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-[13px] font-semibold transition-all disabled:opacity-50";
  const secondaryStyle: React.CSSProperties = {
    background: "rgba(255,255,255,0.08)",
    backdropFilter: "blur(8px)",
    WebkitBackdropFilter: "blur(8px)",
    border: "1px solid rgba(255,255,255,0.14)",
    color: "rgba(255,255,255,0.75)",
  };
  return (
    <div
      className="relative shrink-0 overflow-hidden"
      style={{ minHeight: "160px" }}
    >
      {/* Background image */}
      <img
        src="/backgrounds/documents-bg.png"
        alt=""
        aria-hidden
        className="absolute inset-0 w-full h-full object-cover object-center pointer-events-none select-none"
        style={{ zIndex: 0 }}
      />
      {/* Directional overlay — heavy left for text, lighter right to show scene */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: "linear-gradient(135deg, rgba(3,17,31,0.88) 0%, rgba(6,38,58,0.60) 55%, rgba(3,17,31,0.70) 100%)",
          zIndex: 1,
        }}
      />
      {/* Teal light ray */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: "radial-gradient(ellipse at 70% 0%, rgba(34,211,238,0.14) 0%, transparent 55%)",
          zIndex: 1,
        }}
      />
      {/* Bottom fade blend into content */}
      <div
        className="absolute bottom-0 left-0 right-0 h-12 pointer-events-none"
        style={{ background: "linear-gradient(to bottom, transparent, rgba(3,17,31,0.65))", zIndex: 2 }}
      />
      {/* Content */}
      <div className="relative flex items-center justify-between px-8 py-7" style={{ zIndex: 3 }}>
        <div className="flex items-center gap-4">
          <CoralMascot variant="documents" size="md" className="shrink-0" />
          <div>
            <h1 className="text-[24px] font-extrabold text-white tracking-tight leading-none">Documents</h1>
            <p className="text-[12.5px] mt-1.5 font-medium" style={{ color: "rgba(34,211,238,0.75)" }}>
              {count > 0
                ? `${count} statement${count !== 1 ? "s" : ""} · Upload statements and track parsing.`
                : "Upload statements and track parsing."}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={onRefresh}
            disabled={refreshing}
            className={secondaryBtn}
            style={secondaryStyle}
            title="Refresh documents and ingestion health"
          >
            <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
            Refresh
          </button>
          <button onClick={onBulkUpload} className={secondaryBtn} style={secondaryStyle} title="Upload multiple PDFs">
            <FolderUp size={13} />
            Bulk Upload
          </button>
          <motion.button
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            onClick={onUpload}
            className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-[13px] font-semibold text-white"
            style={{ background: "linear-gradient(135deg, #FF7A5A, #FFA38F)", boxShadow: "0 4px 18px rgba(255,122,90,0.40)" }}
          >
            <Upload size={13} />
            Upload
          </motion.button>
        </div>
      </div>
    </div>
  );
}

/** Default expansion: open every institution + account, open only the newest year per account. */
function defaultExpanded(groups: InstitutionGroup[]): Set<string> {
  const keys = new Set<string>();
  for (const inst of groups) {
    keys.add(instKey(inst.slug));
    for (const acct of inst.accounts) {
      keys.add(acctKey(inst.slug, acct.account));
      // years are sorted desc → first is newest
      if (acct.years.length > 0) {
        keys.add(yearKey(inst.slug, acct.account, acct.years[0].year));
      }
    }
  }
  return keys;
}

function allKeys(groups: InstitutionGroup[]): Set<string> {
  const keys = new Set<string>();
  for (const inst of groups) {
    keys.add(instKey(inst.slug));
    for (const acct of inst.accounts) {
      keys.add(acctKey(inst.slug, acct.account));
      for (const yg of acct.years) keys.add(yearKey(inst.slug, acct.account, yg.year));
    }
  }
  return keys;
}

export function DocumentsPage() {
  const { ingestionJobs } = useAppStore();
  const { docs, loading, error, refetch, polling } = useDocuments();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [filters, setFilters] = useState<DocumentFilterState>(EMPTY_FILTERS);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const initializedExpansion = useRef(false);

  const { health, issuesByDoc, loading: healthLoading, refetch: refetchHealth } = useIngestionHealth();

  // Refetch when an ingestion job transitions out of processing (upload finished).
  const processingJobCount = ingestionJobs.filter((j) => j.status === "processing").length;
  useEffect(() => {
    refetch();
  }, [processingJobCount, refetch]);

  // After any document change (reprocess/delete/upload), refresh both docs + health.
  const refreshAll = () => {
    refetch();
    refetchHealth();
  };

  // Manual refresh from the header button — shows a spinner until both finish.
  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await Promise.all([refetch(), refetchHealth()]);
    } finally {
      setRefreshing(false);
    }
  };

  const stats = useMemo(() => computeStats(docs), [docs]);
  const filtered = useMemo(() => filterDocuments(docs, filters), [docs, filters]);
  const groups = useMemo(() => groupDocuments(filtered), [filtered]);

  // Set sensible default expansion once after the first non-empty load.
  useEffect(() => {
    if (!initializedExpansion.current && docs.length > 0) {
      setExpanded(defaultExpanded(groupDocuments(docs)));
      initializedExpansion.current = true;
    }
  }, [docs]);

  const toggle = (key: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });

  const expandAll = () => setExpanded(allKeys(groups));
  const collapseAll = () => setExpanded(new Set());

  const filtersActive =
    filters.search !== "" || filters.institution !== "all" || filters.year !== "all" || filters.status !== "all";

  return (
    <div className="flex flex-col h-full" style={{ background: "transparent" }}>
      <PageHeader
        onUpload={() => setUploadOpen(true)}
        onBulkUpload={() => setBulkOpen(true)}
        onRefresh={handleRefresh}
        refreshing={refreshing}
        count={docs.length}
      />

      <motion.div
        variants={contentPageVariants}
        initial="hidden"
        animate="visible"
        className="flex-1 overflow-y-auto px-7 py-6 space-y-5"
        style={{ background: "transparent" }}
      >
        {/* Error banner — fetch failed but UI stays usable */}
        {error && (
          <motion.div
            variants={staggerChild}
            className="flex items-center gap-2 rounded-2xl px-4 py-3 text-[12px] font-medium"
            style={{ background: "rgba(228,87,87,0.08)", border: "1px solid rgba(228,87,87,0.25)", color: "#E45757" }}
          >
            <AlertTriangle size={14} />
            <span>Couldn't refresh documents ({error}).</span>
            <button onClick={refetch} className="underline underline-offset-2 ml-1">
              Retry
            </button>
          </motion.div>
        )}

        {/* Summary cards — always derived from the list */}
        {!loading && docs.length > 0 && <DocumentStatsCards stats={stats} liveProcessing={polling} />}

        {/* Reprocess toolbar */}
        {!loading && docs.length > 0 && (
          <motion.div variants={staggerChild}>
            <ReprocessToolbar
              onDone={refreshAll}
              missingCount={health?.summary.incomplete_documents ?? 0}
              failedCount={health?.summary.failed ?? stats.failed}
            />
          </motion.div>
        )}

        {/* Ingestion health */}
        {!loading && docs.length > 0 && (
          <motion.div variants={staggerChild}>
            <IngestionHealthPanel health={health} loading={healthLoading} />
          </motion.div>
        )}

        {/* Filters */}
        {!loading && docs.length > 0 && (
          <motion.div variants={staggerChild}>
            <DocumentFilters
              docs={docs}
              filters={filters}
              onChange={setFilters}
              onExpandAll={expandAll}
              onCollapseAll={collapseAll}
            />
          </motion.div>
        )}

        {/* Mascot-driven processing banner — shown while ingestion is live */}
        {!loading && docs.length > 0 && polling && (
          <motion.div variants={staggerChild}>
            <CoralLoadingState
              variant="documents"
              message="Coral is reading your statements…"
              submessage="Extracting transactions, chunks, and financial details."
            />
          </motion.div>
        )}

        {/* Body */}
        {loading ? (
          <div className="space-y-3">
            <CoralLoadingState
              variant="documents"
              message="Rebuilding your financial memory…"
              submessage="Loading your statements and ingestion health."
            />
            <div className="space-y-2.5">
              {Array.from({ length: 5 }).map((_, i) => (
                <div
                  key={i}
                  className="rounded-2xl h-16 animate-pulse"
                  style={{ background: "rgba(34,211,238,0.06)" }}
                />
              ))}
            </div>
          </div>
        ) : docs.length === 0 ? (
          <EmptyAll onUpload={() => setUploadOpen(true)} />
        ) : groups.length === 0 ? (
          <NoMatches filtersActive={filtersActive} onClear={() => setFilters(EMPTY_FILTERS)} />
        ) : (
          <motion.div variants={staggerChild}>
            <DocumentBucketAccordion
              groups={groups}
              expanded={expanded}
              toggle={toggle}
              onChanged={refreshAll}
              issuesByDoc={issuesByDoc}
            />
          </motion.div>
        )}

        <div className="h-3" />
      </motion.div>

      <UploadModal
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onUploaded={() => {
          setUploadOpen(false);
          refreshAll();
        }}
      />

      <BulkUploadModal
        open={bulkOpen}
        onClose={() => setBulkOpen(false)}
        onUploaded={() => {
          setBulkOpen(false);
          refreshAll();
        }}
      />
    </div>
  );
}

function EmptyAll({ onUpload }: { onUpload: () => void }) {
  return (
    <motion.div variants={staggerChild}>
      <div
        className="rounded-3xl"
        style={{
          background: "rgba(3,17,31,0.55)",
          backdropFilter: "blur(16px)",
          border: "1px dashed rgba(34,211,238,0.18)",
        }}
      >
        <CoralEmptyState
          variant="documents"
          title="No statements uploaded yet"
          description="Drop your PDFs here and Coral will turn them into searchable financial data."
          actionLabel="Upload a statement"
          onAction={onUpload}
        />
      </div>
    </motion.div>
  );
}

function NoMatches({ filtersActive, onClear }: { filtersActive: boolean; onClear: () => void }) {
  return (
    <motion.div variants={staggerChild}>
      <div
        className="rounded-3xl px-6 py-10 text-center"
        style={{
          background: "rgba(3,17,31,0.55)",
          backdropFilter: "blur(16px)",
          border: "1px dashed rgba(34,211,238,0.18)",
        }}
      >
        <p className="text-[13px] font-semibold text-white/80 mb-1">No documents match your filters</p>
        <p className="text-[11.5px] mb-4" style={{ color: "rgba(255,255,255,0.38)" }}>Try a different search term, institution, year, or status.</p>
        {filtersActive && (
          <button
            onClick={onClear}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-[12px] font-medium"
            style={{
              background: "rgba(255,255,255,0.08)",
              border: "1px solid rgba(34,211,238,0.18)",
              color: "rgba(255,255,255,0.65)",
            }}
          >
            Clear filters
          </button>
        )}
      </div>
    </motion.div>
  );
}
