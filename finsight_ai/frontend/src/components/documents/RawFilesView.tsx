import { useState, useMemo } from "react";
import { Search, RefreshCw, Trash2, Loader2, AlertTriangle } from "lucide-react";
import toast from "react-hot-toast";
import type { DocumentSummary, DocumentIssue } from "../../types";
import { DocumentStatusBadge } from "./DocumentStatusBadge";
import {
  normalizeDocumentStatus,
  normalizeDocumentInstitution,
  normalizeDocumentAccount,
  normalizeDocumentMonth,
  normalizeDocumentYear,
  monthShort,
  relativeTime,
  inferInstitution,
  inferYear,
  institutionLabel,
} from "../../lib/documentLibrary";
import { filterDocuments, EMPTY_FILTERS, type DocumentFilterState } from "../../utils/documentUtils";
import { documentsApi } from "../../api/documents";

interface Props {
  docs: DocumentSummary[];
  onChanged: () => void;
  onDocClick: (doc: DocumentSummary) => void;
  issuesByDoc?: Record<string, DocumentIssue>;
}

function RawRow({
  doc,
  onChanged,
  onDocClick,
  issue,
}: {
  doc: DocumentSummary;
  onChanged: () => void;
  onDocClick: (doc: DocumentSummary) => void;
  issue?: DocumentIssue;
}) {
  const [deleting, setDeleting] = useState(false);
  const [reprocessing, setReprocessing] = useState(false);

  const status = normalizeDocumentStatus(doc);
  const inst = normalizeDocumentInstitution(doc);
  const acct = normalizeDocumentAccount(doc);
  const month = normalizeDocumentMonth(doc);
  const year = normalizeDocumentYear(doc);
  const period = month && year ? `${monthShort(month)} ${year}` : year ? String(year) : "—";
  const hasIssues = issue && issue.issues.length > 0;

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`Delete "${doc.filename}"? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      await documentsApi.delete(doc.id);
      toast.success("Document deleted");
      onChanged();
    } catch {
      toast.error("Failed to delete");
      setDeleting(false);
    }
  };

  const handleReprocess = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setReprocessing(true);
    try {
      const res = await documentsApi.reprocess(doc.id);
      if (res.ok) {
        toast.success(`Reprocessed: ${res.transactions} txns, ${res.chunks} chunks`);
      } else {
        toast.error(res.error || "Reprocess failed");
      }
      onChanged();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Reprocess failed");
    } finally {
      setReprocessing(false);
    }
  };

  return (
    <div
      className="flex items-center justify-between px-4 py-3 transition-colors group cursor-pointer"
      style={{ borderBottom: "1px solid var(--row-border)" }}
      onClick={() => onDocClick(doc)}
      onMouseEnter={(e) => (e.currentTarget.style.background = "var(--row-bg)")}
      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
    >
      <div className="flex items-center gap-3 min-w-0">
        <div
          className="w-7 h-7 rounded-lg shrink-0 flex items-center justify-center"
          style={{ background: "rgba(34,211,238,0.07)", color: "rgba(34,211,238,0.60)" }}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
          </svg>
        </div>
        <div className="min-w-0">
          <p className="text-[12px] font-medium truncate" style={{ color: "var(--text-primary)" }} title={doc.filename}>
            {doc.filename}
          </p>
          <p className="text-[10.5px] mt-0.5 flex items-center gap-1.5 flex-wrap" style={{ color: "var(--text-muted)" }}>
            <span>{inst}</span>
            {acct !== "Unknown Account" && (
              <>
                <span style={{ color: "var(--text-dim)" }}>·</span>
                <span>{acct}</span>
              </>
            )}
            <span style={{ color: "var(--text-dim)" }}>·</span>
            <span>{period}</span>
            {doc.page_count != null && (
              <>
                <span style={{ color: "var(--text-dim)" }}>·</span>
                <span>{doc.page_count}p</span>
              </>
            )}
            <span style={{ color: "var(--text-dim)" }}>·</span>
            <span>{relativeTime(doc.upload_time)}</span>
          </p>
          {doc.error && (
            <p className="text-[10px] mt-0.5 truncate" style={{ color: "rgba(228,87,87,0.75)" }} title={doc.error}>
              {doc.error}
            </p>
          )}
        </div>
      </div>

      <div className="flex items-center gap-1.5 shrink-0 ml-4">
        {hasIssues && (
          <span
            className="flex items-center gap-1 text-[9.5px] font-semibold px-1.5 py-0.5 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
            style={{ background: "rgba(200,154,0,0.10)", color: "#c89a00" }}
          >
            <AlertTriangle size={9} />
            {issue!.issues.length}
          </span>
        )}
        <DocumentStatusBadge status={status} size="xs" />
        <div
          className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity ml-1"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            onClick={handleReprocess}
            disabled={reprocessing}
            className="p-1.5 rounded-lg transition-colors disabled:opacity-40"
            style={{ color: "var(--text-dim)" }}
            onMouseEnter={(e) => (e.currentTarget.style.color = "var(--border-accent)")}
            onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-dim)")}
            title="Reprocess"
          >
            {reprocessing ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
          </button>
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="p-1.5 rounded-lg transition-colors disabled:opacity-40"
            style={{ color: "var(--text-dim)" }}
            onMouseEnter={(e) => (e.currentTarget.style.color = "rgba(228,87,87,0.85)")}
            onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-dim)")}
            title="Delete"
          >
            {deleting ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
          </button>
        </div>
      </div>
    </div>
  );
}

// Re-export helpers from documentUtils since they accept DocumentSummary[]
function yearOptions(docs: DocumentSummary[]): number[] {
  const years = new Set<number>();
  for (const d of docs) {
    const y = inferYear(d);
    if (y) years.add(y);
  }
  return [...years].sort((a, b) => b - a);
}

function institutionOptions(docs: DocumentSummary[]): Array<{ value: string; label: string }> {
  const slugs = new Set(docs.map((d) => inferInstitution(d)));
  return [...slugs].map((slug) => ({ value: slug, label: institutionLabel(slug) }));
}

export function RawFilesView({ docs, onChanged, onDocClick, issuesByDoc }: Props) {
  const [filters, setFilters] = useState<DocumentFilterState>(EMPTY_FILTERS);

  const instOpts = useMemo(() => institutionOptions(docs), [docs]);
  const yrOpts = useMemo(() => yearOptions(docs), [docs]);

  const filtered = useMemo(() => filterDocuments(docs, filters), [docs, filters]);

  const hasFilters =
    filters.search !== "" || filters.institution !== "all" || filters.year !== "all" || filters.status !== "all";

  return (
    <div className="space-y-4">
      {/* Search + filters bar */}
      <div className="flex flex-wrap gap-2">
        <div
          className="flex items-center gap-2 flex-1 min-w-[180px] rounded-xl px-3 py-2"
          style={{
            background: "var(--panel-bg)",
            border: "1px solid var(--panel-border-accent)",
          }}
        >
          <Search size={13} style={{ color: "var(--text-dim)" }} />
          <input
            type="text"
            placeholder="Search filenames, accounts, institutions…"
            value={filters.search}
            onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
            className="flex-1 bg-transparent text-[12px] outline-none placeholder:opacity-40"
            style={{ color: "var(--text-primary)" }}
          />
        </div>

        <select
          value={filters.institution}
          onChange={(e) => setFilters((f) => ({ ...f, institution: e.target.value }))}
          className="rounded-xl px-3 py-2 text-[12px] font-medium outline-none cursor-pointer"
          style={{
            background: "var(--panel-bg)",
            border: "1px solid var(--panel-border-accent)",
            color: "var(--text-secondary)",
          }}
        >
          <option value="all">All institutions</option>
          {instOpts.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>

        <select
          value={filters.year}
          onChange={(e) => setFilters((f) => ({ ...f, year: e.target.value }))}
          className="rounded-xl px-3 py-2 text-[12px] font-medium outline-none cursor-pointer"
          style={{
            background: "var(--panel-bg)",
            border: "1px solid var(--panel-border-accent)",
            color: "var(--text-secondary)",
          }}
        >
          <option value="all">All years</option>
          {yrOpts.map((y) => (
            <option key={y} value={String(y)}>{y}</option>
          ))}
        </select>

        <select
          value={filters.status}
          onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}
          className="rounded-xl px-3 py-2 text-[12px] font-medium outline-none cursor-pointer"
          style={{
            background: "var(--panel-bg)",
            border: "1px solid var(--panel-border-accent)",
            color: "var(--text-secondary)",
          }}
        >
          <option value="all">All statuses</option>
          <option value="parsed">Parsed</option>
          <option value="processing">Processing</option>
          <option value="uploaded">Uploaded</option>
          <option value="failed">Failed</option>
        </select>

        {hasFilters && (
          <button
            onClick={() => setFilters(EMPTY_FILTERS)}
            className="px-3 py-2 rounded-xl text-[11.5px] font-medium transition-colors"
            style={{
              background: "var(--btn-glass-bg)",
              border: "1px solid var(--btn-glass-border)",
              color: "var(--btn-glass-color)",
            }}
          >
            Clear
          </button>
        )}
      </div>

      <p className="text-[11px]" style={{ color: "var(--text-dim)" }}>
        {filtered.length} of {docs.length} file{docs.length !== 1 ? "s" : ""}
        {hasFilters ? " (filtered)" : ""}
      </p>

      {/* File list */}
      {filtered.length === 0 ? (
        <div
          className="rounded-2xl px-6 py-10 text-center"
          style={{ background: "var(--empty-bg)", border: "1px dashed var(--empty-border)" }}
        >
          <p className="text-[12.5px]" style={{ color: "var(--text-muted)" }}>
            {hasFilters ? "No files match your filters." : "No files found."}
          </p>
        </div>
      ) : (
        <div
          className="rounded-2xl overflow-hidden"
          style={{
            background: "var(--panel-bg)",
            border: "1px solid var(--panel-border)",
            backdropFilter: "blur(16px)",
          }}
        >
          {filtered.map((doc) => (
            <RawRow
              key={doc.id}
              doc={doc}
              onChanged={onChanged}
              onDocClick={onDocClick}
              issue={issuesByDoc?.[doc.id]}
            />
          ))}
        </div>
      )}
    </div>
  );
}
