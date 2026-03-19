import { useState, useEffect, useCallback } from "react";
import {
  FileText,
  BarChart3,
  Building2,
  DollarSign,
  TrendingUp,
  ChevronDown,
  ChevronUp,
  Calendar,
  FolderOpen,
  RefreshCw,
} from "lucide-react";
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
import { INSTITUTION_COLORS } from "../design/tokens";

type Bucket = "investments" | "banking";

// ── Folder card ───────────────────────────────────────────────────────────────

function FolderCard({ folder }: { folder: FolderSummary }) {
  const colorCls =
    INSTITUTION_COLORS[folder.institution_type] ||
    "bg-ocean-50 text-ocean border-ocean-100";

  return (
    <div className="flex items-center justify-between p-4 rounded-2xl border border-ocean-100 bg-white hover:shadow-soft transition-shadow">
      <div className="flex items-center gap-3">
        <div className={`p-2 rounded-xl border ${colorCls}`}>
          <FolderOpen size={15} />
        </div>
        <div>
          <p className="text-sm font-semibold text-slate leading-tight">{folder.label}</p>
          {folder.latest_file_date && (
            <p className="text-xs text-ocean-DEFAULT/40 mt-0.5 flex items-center gap-1">
              <Calendar size={10} />
              Latest: {folder.latest_file_date}
            </p>
          )}
        </div>
      </div>
      <div className="text-right">
        <p className="text-lg font-bold text-slate">{folder.file_count}</p>
        <p className="text-xs text-ocean-DEFAULT/40">
          {folder.file_count === 1 ? "file" : "files"}
        </p>
      </div>
    </div>
  );
}

// ── Recent files section — collapsible ───────────────────────────────────────

function RecentFilesSection({ scan }: { scan: FolderScanResult }) {
  const [expanded, setExpanded] = useState(false);
  const files = scan.recent_files;
  if (files.length === 0) return null;

  return (
    <Card padding="none">
      <button
        className="w-full px-5 py-4 flex items-center justify-between text-left"
        onClick={() => setExpanded(!expanded)}
      >
        <SectionHeader
          title="Recent Files"
          subtitle={`Last ${files.length} added`}
        />
        {expanded ? (
          <ChevronUp size={14} className="text-ocean-DEFAULT/40" />
        ) : (
          <ChevronDown size={14} className="text-ocean-DEFAULT/40" />
        )}
      </button>
      {expanded && (
        <div className="divide-y divide-ocean-50 border-t border-ocean-50">
          {files.map((f, i) => (
            <div key={i} className="px-5 py-3 flex items-center justify-between">
              <div className="flex items-center gap-3 min-w-0">
                <FileText size={14} className="text-ocean-DEFAULT/40 shrink-0" />
                <div className="min-w-0">
                  <p className="text-xs font-medium text-slate truncate">{f.filename}</p>
                  <p className="text-xs text-ocean-DEFAULT/40">{f.folder_label}</p>
                </div>
              </div>
              <div className="text-xs text-ocean-DEFAULT/40 shrink-0 ml-3">
                {f.modified_date}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

// ── Bucket dashboards ─────────────────────────────────────────────────────────

function InvestmentsDashboard({ analytics }: { analytics: AnalyticsSummary | null }) {
  if (!analytics || analytics.total_documents === 0) {
    return (
      <EmptyState
        title="No investment data yet"
        description="Add PDFs to data/investments/morgan_stanley or data/investments/etrade, then ask Coral to ingest them."
      />
    );
  }
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <MetricCard label="Holdings" value={analytics.total_holdings} icon={<TrendingUp size={15} />} accent="ocean" />
        <MetricCard label="Fees Tracked" value={analytics.total_fees} icon={<DollarSign size={15} />} accent="coral" />
      </div>
      {analytics.date_range.start && (
        <p className="text-xs text-ocean-DEFAULT/40 px-1">
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
      />
    );
  }
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <MetricCard label="Transactions" value={analytics.total_transactions} icon={<BarChart3 size={15} />} accent="ocean" />
        <MetricCard label="Statements" value={analytics.total_statements} icon={<FileText size={15} />} accent="coral" />
      </div>
      {analytics.date_range.start && (
        <p className="text-xs text-ocean-DEFAULT/40 px-1">
          Coverage: {analytics.date_range.start} → {analytics.date_range.end}
        </p>
      )}
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
    <div className="max-w-4xl mx-auto px-6 py-8 space-y-7">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate leading-tight">Dashboard</h1>
          <p className="text-sm text-ocean-DEFAULT/50 mt-1">
            Your financial statements, analyzed locally
          </p>
        </div>
        <BucketToggle value={bucket} onChange={setBucket} />
      </div>

      {/* Top KPIs */}
      {scan && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <MetricCard label="Total Files" value={scan.total_files} icon={<FileText size={16} />} accent="ocean" />
          <MetricCard label="Institutions" value={analytics?.institutions.length ?? 0} icon={<Building2 size={16} />} accent="highlight" />
          <MetricCard label="Statements" value={analytics?.total_statements ?? 0} icon={<BarChart3 size={16} />} accent="coral" />
          <MetricCard label="Transactions" value={analytics?.total_transactions ?? 0} icon={<DollarSign size={16} />} accent="positive" />
        </div>
      )}

      {/* Institution / folder summary cards */}
      <Card padding="md">
        <div className="flex items-center justify-between mb-4">
          <SectionHeader
            title={bucket === "investments" ? "Investment Accounts" : "Banking Accounts"}
            subtitle={`${totalForBucket} file${totalForBucket !== 1 ? "s" : ""}`}
          />
          <button
            onClick={fetchData}
            className="text-xs text-ocean-DEFAULT/40 hover:text-ocean flex items-center gap-1 transition-colors"
          >
            <RefreshCw size={12} />
            Refresh
          </button>
        </div>

        {loading ? (
          <div className="py-8 text-center">
            <RefreshCw size={18} className="mx-auto text-ocean-DEFAULT/30 animate-spin mb-2" />
            <p className="text-sm text-ocean-DEFAULT/40">Scanning folders…</p>
          </div>
        ) : visibleFolders.length === 0 ? (
          <p className="text-sm text-ocean-DEFAULT/40 py-2">No folders configured for this bucket.</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {visibleFolders.map((f) => (
              <FolderCard key={f.folder_key} folder={f} />
            ))}
          </div>
        )}
      </Card>

      {/* Analytics widgets for selected bucket */}
      <Card padding="md">
        <div className="mb-4">
          <SectionHeader
            title={bucket === "investments" ? "Investments Overview" : "Banking Overview"}
          />
        </div>
        {bucket === "investments" ? (
          <InvestmentsDashboard analytics={analytics} />
        ) : (
          <BankingDashboard analytics={analytics} />
        )}
      </Card>

      {/* Upload */}
      <UploadCard onUploaded={fetchData} />

      {/* Recent files — compact, collapsible */}
      {scan && <RecentFilesSection scan={scan} />}
    </div>
  );
}
