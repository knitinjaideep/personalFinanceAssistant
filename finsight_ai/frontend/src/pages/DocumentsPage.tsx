import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Upload, AlertTriangle } from "lucide-react";
import { useAppStore } from "../store/appStore";
import { UploadModal } from "../components/upload/UploadModal";
import { DocumentStatsCards } from "../components/documents/DocumentStatsCards";
import { DocumentFilters } from "../components/documents/DocumentFilters";
import {
  DocumentBucketAccordion,
  instKey,
  acctKey,
  yearKey,
} from "../components/documents/DocumentBucketAccordion";
import { useDocuments } from "../hooks/useDocuments";
import {
  computeStats,
  groupDocuments,
  filterDocuments,
  EMPTY_FILTERS,
  type DocumentFilterState,
  type InstitutionGroup,
} from "../utils/documentUtils";
import { contentPageVariants, staggerChild } from "../design/motion";

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
          {count > 0 ? `${count} statement${count !== 1 ? "s" : ""}` : "No documents yet"}
        </p>
      </div>
      <motion.button
        whileHover={{ scale: 1.03 }}
        whileTap={{ scale: 0.97 }}
        onClick={onUpload}
        className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-[13px] font-semibold text-white"
        style={{ background: "linear-gradient(135deg, #FF7A5A, #FFA38F)", boxShadow: "0 4px 14px rgba(255,122,90,0.32)" }}
      >
        <Upload size={13} />
        Upload
      </motion.button>
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
  const [filters, setFilters] = useState<DocumentFilterState>(EMPTY_FILTERS);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const initializedExpansion = useRef(false);

  // Refetch when an ingestion job transitions out of processing (upload finished).
  const processingJobCount = ingestionJobs.filter((j) => j.status === "processing").length;
  useEffect(() => {
    refetch();
  }, [processingJobCount, refetch]);

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
    <div className="flex flex-col h-full">
      <PageHeader onUpload={() => setUploadOpen(true)} count={docs.length} />

      <motion.div
        variants={contentPageVariants}
        initial="hidden"
        animate="visible"
        className="flex-1 overflow-y-auto px-7 py-6 space-y-5"
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

        {/* Body */}
        {loading ? (
          <div className="space-y-2.5">
            {Array.from({ length: 5 }).map((_, i) => (
              <div
                key={i}
                className="rounded-2xl h-16 animate-pulse"
                style={{ background: "rgba(205,237,246,0.20)" }}
              />
            ))}
          </div>
        ) : docs.length === 0 ? (
          <EmptyAll onUpload={() => setUploadOpen(true)} />
        ) : groups.length === 0 ? (
          <NoMatches filtersActive={filtersActive} onClear={() => setFilters(EMPTY_FILTERS)} />
        ) : (
          <motion.div variants={staggerChild}>
            <DocumentBucketAccordion groups={groups} expanded={expanded} toggle={toggle} onChanged={refetch} />
          </motion.div>
        )}

        <div className="h-3" />
      </motion.div>

      <UploadModal
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onUploaded={() => {
          setUploadOpen(false);
          refetch();
        }}
      />
    </div>
  );
}

function EmptyAll({ onUpload }: { onUpload: () => void }) {
  return (
    <motion.div variants={staggerChild}>
      <div
        className="rounded-2xl px-6 py-12 text-center"
        style={{ background: "rgba(255,255,255,0.65)", border: "1px dashed rgba(205,237,246,0.70)" }}
      >
        <div className="text-3xl mb-3">📄</div>
        <p className="text-[14px] font-semibold text-ocean-deep mb-1.5">No documents yet</p>
        <p className="text-[12px] text-ocean/40 max-w-xs mx-auto leading-relaxed mb-4">
          Upload your first PDF statement to get started. Coral parses it locally — nothing leaves your device.
        </p>
        <button
          onClick={onUpload}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-[13px] font-semibold text-white"
          style={{ background: "linear-gradient(135deg, #FF7A5A, #FFA38F)" }}
        >
          <Upload size={13} />
          Upload a statement
        </button>
      </div>
    </motion.div>
  );
}

function NoMatches({ filtersActive, onClear }: { filtersActive: boolean; onClear: () => void }) {
  return (
    <motion.div variants={staggerChild}>
      <div
        className="rounded-2xl px-6 py-10 text-center"
        style={{ background: "rgba(255,255,255,0.65)", border: "1px dashed rgba(205,237,246,0.70)" }}
      >
        <p className="text-[13px] font-semibold text-ocean-deep mb-1">No documents match your filters</p>
        <p className="text-[11.5px] text-ocean/40 mb-4">Try a different search term, institution, year, or status.</p>
        {filtersActive && (
          <button
            onClick={onClear}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-[12px] font-medium text-ocean/70"
            style={{ background: "rgba(255,255,255,0.9)", border: "1px solid rgba(205,237,246,0.7)" }}
          >
            Clear filters
          </button>
        )}
      </div>
    </motion.div>
  );
}
