"use client";

/**
 * Demoted document/upload status strip (pr-06-overview.md: "Remove the
 * document-centric dashboard as the dominant Home experience... Do not
 * delete upload functionality"). A single low-key row replaces the old
 * 6-metric-card grid + Next Best Tasks + Recent Uploads sections that used
 * to dominate Home — upload/document-management is still one click away,
 * it's just no longer the primary visual hierarchy.
 */

import Link from "next/link";
import { ArrowRight, FileText, RefreshCw, Upload } from "lucide-react";
import Surface from "@/components/coral-ds/Surface";
import { useAppStore } from "@/store/appStore";
import type { DocumentStats } from "@/types/index";

interface DocumentsStripProps {
  stats: DocumentStats | null;
  loading: boolean;
  /** True when the document-stats request itself failed — distinct from
   * `stats === null && !loading` meaning "confirmed zero documents" isn't
   * possible here (a successful zero-document fetch is a real DocumentStats
   * object with total: 0), so `error` is the only signal needed to tell
   * "couldn't check" apart from "checked, and it's empty". */
  error?: boolean;
  onRetry?: () => void;
}

export default function DocumentsStrip({ stats, loading, error, onRetry }: DocumentsStripProps) {
  const openUploadModal = useAppStore((s) => s.openUploadModal);

  const summary = loading
    ? "Loading document status…"
    : error
      ? "Couldn't load document status."
      : stats
        ? `${stats.total} document${stats.total === 1 ? "" : "s"} uploaded · ${stats.parsed} processed` +
          (stats.processing ? ` · ${stats.processing} processing` : "") +
          (stats.failed ? ` · ${stats.failed} need attention` : "")
        : "No documents uploaded yet.";

  return (
    <Surface padding="sm" className="flex flex-wrap items-center justify-between gap-4">
      <div className="flex items-center gap-3 min-w-0">
        <span
          className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
          style={{ background: "var(--glass-light-bg)", border: "1px solid var(--border-subtle)" }}
        >
          <FileText size={15} style={{ color: "var(--text-muted)" }} />
        </span>
        <p className="small-text truncate" style={{ color: "var(--text-secondary)" }}>{summary}</p>
      </div>
      <div className="flex items-center gap-4 shrink-0">
        {error && onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex items-center gap-1 text-sm font-semibold transition-opacity hover:opacity-70"
            style={{ color: "var(--accent-strong)" }}
          >
            <RefreshCw size={13} /> Retry
          </button>
        )}
        <Link
          href="/documents"
          className="inline-flex items-center gap-1 text-sm font-semibold transition-opacity hover:opacity-70"
          style={{ color: "var(--accent-strong)" }}
        >
          Manage documents <ArrowRight size={13} />
        </Link>
        <button
          type="button"
          onClick={openUploadModal}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-semibold btn-glass transition-all"
        >
          <Upload size={14} /> Upload
        </button>
      </div>
    </Surface>
  );
}
