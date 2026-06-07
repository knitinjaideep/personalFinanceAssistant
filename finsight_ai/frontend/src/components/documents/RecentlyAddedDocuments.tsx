import type { DocumentSummary } from "../../types";
import { DocumentStatusBadge } from "./DocumentStatusBadge";
import {
  normalizeDocumentStatus,
  normalizeDocumentInstitution,
  normalizeDocumentAccount,
  normalizeDocumentMonth,
  normalizeDocumentYear,
  monthShort,
  relativeTime,
  getRecentlyAddedDocuments,
} from "../../lib/documentLibrary";

interface Props {
  docs: DocumentSummary[];
  onDocClick: (doc: DocumentSummary) => void;
}

export function RecentlyAddedDocuments({ docs, onDocClick }: Props) {
  const recent = getRecentlyAddedDocuments(docs, 6);

  if (recent.length === 0) return null;

  return (
    <div className="space-y-2">
      <p className="text-[12px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-dim)" }}>
        Recently Added
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {recent.map((doc) => {
          const status = normalizeDocumentStatus(doc);
          const inst = normalizeDocumentInstitution(doc);
          const acct = normalizeDocumentAccount(doc);
          const month = normalizeDocumentMonth(doc);
          const year = normalizeDocumentYear(doc);
          const period = month && year ? `${monthShort(month)} ${year}` : year ? String(year) : "—";

          return (
            <button
              key={doc.id}
              onClick={() => onDocClick(doc)}
              className="flex items-center gap-3 rounded-2xl px-4 py-3 text-left transition-all hover:-translate-y-0.5 hover:scale-[1.005]"
              style={{
                background: "var(--panel-bg)",
                border: "1px solid var(--panel-border)",
                backdropFilter: "blur(12px)",
                WebkitBackdropFilter: "blur(12px)",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.borderColor = "var(--panel-border-accent)")}
              onMouseLeave={(e) => (e.currentTarget.style.borderColor = "var(--panel-border)")}
            >
              <div
                className="w-8 h-8 rounded-xl shrink-0 flex items-center justify-center"
                style={{ background: "rgba(34,211,238,0.08)", color: "rgba(34,211,238,0.70)" }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                </svg>
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-[12px] font-semibold truncate" style={{ color: "var(--text-primary)" }}>
                  {inst !== "Unknown" ? inst : acct}
                  {acct !== "Unknown Account" && inst !== "Unknown" && ` · ${acct}`}
                </p>
                <p className="text-[10.5px] mt-0.5" style={{ color: "var(--text-muted)" }}>
                  {period} · {relativeTime(doc.upload_time)}
                </p>
              </div>
              <DocumentStatusBadge status={status} size="xs" />
            </button>
          );
        })}
      </div>
    </div>
  );
}
