import { useState, useEffect, useCallback } from "react";
import {
  FileText, BarChart3, Building2, DollarSign,
  TrendingUp, ChevronDown, Calendar,
  FolderOpen, RefreshCw,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "../api/client";
import { foldersApi } from "../api/folders";
import type { FolderScanResult, FolderSummary } from "../api/folders";
import type { AnalyticsSummary } from "../types";
import { MetricCard } from "../components/ui/MetricCard";
import { Card } from "../components/ui/Card";
import { SectionHeader } from "../components/ui/SectionHeader";
import { EmptyState } from "../components/ui/EmptyState";
import { BucketToggle } from "../components/ui/BucketToggle";
import { UploadCard } from "../components/upload/UploadCard";
import { OceanBackground } from "../components/ui/OceanBackground";
import { INSTITUTION_COLORS } from "../design/tokens";
import {
  pageVariants, staggerContainer, staggerChild,
  fadeVariants,
} from "../design/motion";

type Bucket = "investments" | "banking";

// ── Skeleton loader ───────────────────────────────────────────────────────────

function MetricSkeleton() {
  return (
    <div className="rounded-3xl p-5 flex flex-col gap-4"
      style={{
        background: "rgba(255,255,255,0.65)",
        border: "1px solid rgba(255,255,255,0.25)",
        backdropFilter: "blur(12px)",
      }}
    >
      <div className="flex items-start justify-between">
        <div className="skeleton w-20 h-3" />
        <div className="skeleton w-9 h-9 rounded-xl" />
      </div>
      <div className="skeleton w-16 h-8" />
    </div>
  );
}

// ── Folder card ───────────────────────────────────────────────────────────────

function FolderCard({ folder }: { folder: FolderSummary }) {
  const colorCls =
    INSTITUTION_COLORS[folder.institution_type] ||
    "bg-ocean-50 text-ocean border-ocean-100";

  return (
    <motion.div
      variants={staggerChild}
      whileHover={{ y: -2, transition: { type: "spring", stiffness: 350, damping: 25 } }}
      className="flex items-center justify-between p-4 rounded-2xl cursor-default"
      style={{
        background: "rgba(255,255,255,0.78)",
        border: "1px solid rgba(255,255,255,0.35)",
        boxShadow: "0 2px 12px rgba(11,60,93,0.07)",
        backdropFilter: "blur(8px)",
      }}
    >
      <div className="flex items-center gap-3">
        <div className={`p-2 rounded-xl border ${colorCls}`}>
          <FolderOpen size={14} />
        </div>
        <div>
          <p className="text-sm font-semibold text-ocean-deep leading-tight">{folder.label}</p>
          {folder.latest_file_date && (
            <p className="text-xs text-ocean/35 mt-0.5 flex items-center gap-1">
              <Calendar size={9} />
              Latest: {folder.latest_file_date}
            </p>
          )}
        </div>
      </div>
      <div className="text-right">
        <p className="text-lg font-bold text-ocean-deep tabular">{folder.file_count}</p>
        <p className="text-[10px] text-ocean/35 uppercase tracking-wide">
          {folder.file_count === 1 ? "file" : "files"}
        </p>
      </div>
    </motion.div>
  );
}

// ── Recent files — collapsible ─────────────────────────────────────────────

function RecentFilesSection({ scan }: { scan: FolderScanResult }) {
  const [expanded, setExpanded] = useState(false);
  const files = scan.recent_files;
  if (files.length === 0) return null;

  return (
    <motion.div variants={staggerChild}>
      <Card padding="none">
        <button
          className="w-full px-5 py-4 flex items-center justify-between text-left"
          onClick={() => setExpanded(!expanded)}
        >
          <SectionHeader title="Recent Files" subtitle={`Last ${files.length} added`} />
          <motion.span
            animate={{ rotate: expanded ? 180 : 0 }}
            transition={{ duration: 0.25 }}
            className="text-ocean/30"
          >
            <ChevronDown size={14} />
          </motion.span>
        </button>

        <AnimatePresence>
          {expanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
              className="overflow-hidden"
            >
              <div className="divide-y divide-ocean-50/70 border-t border-ocean-50/80">
                {files.map((f, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.04 }}
                    className="px-5 py-3 flex items-center justify-between"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <FileText size={13} className="text-ocean/30 shrink-0" />
                      <div className="min-w-0">
                        <p className="text-xs font-medium text-ocean-deep truncate">{f.filename}</p>
                        <p className="text-[10px] text-ocean/35">{f.folder_label}</p>
                      </div>
                    </div>
                    <div className="text-[10px] text-ocean/30 shrink-0 ml-3">{f.modified_date}</div>
                  </motion.div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </Card>
    </motion.div>
  );
}

// ── Bucket dashboards ─────────────────────────────────────────────────────────

function InvestmentsDashboard({ analytics }: { analytics: AnalyticsSummary | null }) {
  if (!analytics || analytics.total_documents === 0) {
    return (
      <EmptyState
        title="No investment data yet"
        description="Add PDFs to data/investments/morgan_stanley or data/investments/etrade, then ask Coral to ingest them."
        showMascot
      />
    );
  }
  return (
    <div className="space-y-4">
      <motion.div
        variants={staggerContainer}
        initial="hidden"
        animate="visible"
        className="grid grid-cols-2 gap-4"
      >
        <MetricCard
          label="Holdings"
          value={analytics.total_holdings}
          icon={<TrendingUp size={15} />}
          accent="ocean"
        />
        <MetricCard
          label="Fees Tracked"
          value={analytics.total_fees}
          icon={<DollarSign size={15} />}
          accent="coral"
        />
      </motion.div>
      {analytics.date_range.start && (
        <p className="text-xs text-white/35 px-1">
          Coverage: {analytics.date_range.start} → {analytics.date_range.end}
        </p>
      )}
    </div>
  );
}

function BankingDashboard({ analytics }: { analytics: AnalyticsSummary | null }) {
  if (!analytics || analytics.total_documents === 0) {
    return (
      <EmptyState
        title="No banking data yet"
        description="Add PDFs to data/banking/chase, data/banking/amex, or data/banking/discover, then ingest them."
        showMascot
      />
    );
  }
  return (
    <div className="space-y-4">
      <motion.div
        variants={staggerContainer}
        initial="hidden"
        animate="visible"
        className="grid grid-cols-2 gap-4"
      >
        <MetricCard
          label="Transactions"
          value={analytics.total_transactions}
          icon={<BarChart3 size={15} />}
          accent="ocean"
        />
        <MetricCard
          label="Statements"
          value={analytics.total_statements}
          icon={<FileText size={15} />}
          accent="coral"
        />
      </motion.div>
      {analytics.date_range.start && (
        <p className="text-xs text-white/35 px-1">
          Coverage: {analytics.date_range.start} → {analytics.date_range.end}
        </p>
      )}
    </div>
  );
}

// ── Section card wrapper ──────────────────────────────────────────────────────

function SectionCard({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-3xl p-5 ${className ?? ""}`}
      style={{
        background: "rgba(255,255,255,0.88)",
        backdropFilter: "blur(14px)",
        WebkitBackdropFilter: "blur(14px)",
        border: "1px solid rgba(255,255,255,0.28)",
        boxShadow: "0 6px 32px rgba(11,60,93,0.10), inset 0 1px 0 rgba(255,255,255,0.5)",
      }}
    >
      {children}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function HomePage() {
  const [scan, setScan] = useState<FolderScanResult | null>(null);
  const [analytics, setAnalytics] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [bucket, setBucket] = useState<Bucket>("investments");

  const fetchData = useCallback(async () => {
    try {
      const [scanResult, stats] = await Promise.all([
        foldersApi.scan(10),
        api.get<AnalyticsSummary>("/analytics/summary"),
      ]);
      setScan(scanResult);
      setAnalytics(stats);
    } catch {
      // backend may not be ready yet
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 15000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const visibleFolders = scan?.folders.filter((f) => f.bucket === bucket) ?? [];
  const totalForBucket =
    bucket === "investments" ? (scan?.investments_total ?? 0) : (scan?.banking_total ?? 0);

  return (
    <div className="relative flex-1 overflow-y-auto">
      {/* Ocean background fills the content area */}
      <OceanBackground />

      {/* Content */}
      <motion.div
        variants={pageVariants}
        initial="hidden"
        animate="visible"
        className="relative z-10 max-w-4xl mx-auto px-6 py-8 space-y-7"
      >
        {/* Header */}
        <motion.div variants={staggerChild} className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white leading-tight">
              Dashboard
            </h1>
            <p className="text-sm text-white/45 mt-1 font-medium">
              Your financial statements, analyzed locally
            </p>
          </div>
          <BucketToggle value={bucket} onChange={setBucket} />
        </motion.div>

        {/* Top KPIs */}
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          animate="visible"
          className="grid grid-cols-2 md:grid-cols-4 gap-4"
        >
          {loading ? (
            <>
              <MetricSkeleton />
              <MetricSkeleton />
              <MetricSkeleton />
              <MetricSkeleton />
            </>
          ) : scan ? (
            <>
              <MetricCard label="Total Files"    value={scan.total_files}                      icon={<FileText size={16} />}  accent="ocean" />
              <MetricCard label="Institutions"   value={analytics?.institutions.length ?? 0}   icon={<Building2 size={16} />} accent="highlight" />
              <MetricCard label="Statements"     value={analytics?.total_statements ?? 0}      icon={<BarChart3 size={16} />} accent="coral" />
              <MetricCard label="Transactions"   value={analytics?.total_transactions ?? 0}    icon={<DollarSign size={16} />} accent="positive" />
            </>
          ) : null}
        </motion.div>

        {/* Institution / folder cards */}
        <motion.div variants={staggerChild}>
          <SectionCard>
            <div className="flex items-center justify-between mb-5">
              <SectionHeader
                title={bucket === "investments" ? "Investment Accounts" : "Banking Accounts"}
                subtitle={`${totalForBucket} file${totalForBucket !== 1 ? "s" : ""}`}
              />
              <button
                onClick={fetchData}
                className="flex items-center gap-1.5 text-xs text-ocean/40 hover:text-ocean font-medium transition-colors"
              >
                <RefreshCw size={11} />
                Refresh
              </button>
            </div>

            {loading ? (
              <div className="py-8 text-center">
                <motion.div
                  animate={{ rotate: 360 }}
                  transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                  className="inline-block mb-2"
                >
                  <RefreshCw size={18} className="text-ocean/30" />
                </motion.div>
                <p className="text-sm text-ocean/40">Scanning folders…</p>
              </div>
            ) : visibleFolders.length === 0 ? (
              <p className="text-sm text-ocean/40 py-2">No folders configured for this bucket.</p>
            ) : (
              <motion.div
                variants={staggerContainer}
                initial="hidden"
                animate="visible"
                className="grid grid-cols-1 sm:grid-cols-2 gap-3"
              >
                {visibleFolders.map((f) => (
                  <FolderCard key={f.folder_key} folder={f} />
                ))}
              </motion.div>
            )}
          </SectionCard>
        </motion.div>

        {/* Bucket analytics */}
        <motion.div variants={staggerChild}>
          <SectionCard>
            <div className="mb-5">
              <SectionHeader
                title={bucket === "investments" ? "Investments Overview" : "Banking Overview"}
              />
            </div>
            <AnimatePresence mode="wait">
              <motion.div
                key={bucket}
                variants={fadeVariants}
                initial="hidden"
                animate="visible"
                exit="exit"
              >
                {bucket === "investments" ? (
                  <InvestmentsDashboard analytics={analytics} />
                ) : (
                  <BankingDashboard analytics={analytics} />
                )}
              </motion.div>
            </AnimatePresence>
          </SectionCard>
        </motion.div>

        {/* Upload */}
        <motion.div variants={staggerChild}>
          <UploadCard onUploaded={fetchData} />
        </motion.div>

        {/* Recent files */}
        {scan && <RecentFilesSection scan={scan} />}
      </motion.div>
    </div>
  );
}
