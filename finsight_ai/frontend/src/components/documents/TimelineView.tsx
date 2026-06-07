import type { DocumentSummary } from "../../types";
import { DocumentStatusBadge } from "./DocumentStatusBadge";
import {
  buildTimeline,
  normalizeDocumentStatus,
  normalizeDocumentInstitution,
  normalizeDocumentAccount,
} from "../../lib/documentLibrary";

interface Props {
  docs: DocumentSummary[];
  onDocClick: (doc: DocumentSummary) => void;
}

export function TimelineView({ docs, onDocClick }: Props) {
  const years = buildTimeline(docs);

  if (years.length === 0) {
    return (
      <div
        className="rounded-2xl px-6 py-12 text-center"
        style={{ background: "var(--empty-bg)", border: "1px dashed var(--empty-border)" }}
      >
        <p className="text-[12.5px]" style={{ color: "var(--text-muted)" }}>
          Timeline will appear once statement months are detected.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {years.map((yearGroup) => (
        <div key={yearGroup.year}>
          {/* Year badge */}
          <div className="flex items-center gap-3 mb-3">
            <span
              className="px-3 py-1 rounded-full text-[12px] font-bold"
              style={{
                background: "rgba(34,211,238,0.12)",
                border: "1px solid rgba(34,211,238,0.22)",
                color: "rgba(34,211,238,0.90)",
              }}
            >
              {yearGroup.year}
            </span>
            <span className="text-[11px]" style={{ color: "var(--text-dim)" }}>
              {yearGroup.totalDocs} statement{yearGroup.totalDocs !== 1 ? "s" : ""}
            </span>
            <div className="flex-1 h-px" style={{ background: "var(--row-border)" }} />
          </div>

          <div className="space-y-2">
            {yearGroup.months.map((monthGroup) => (
              <div
                key={monthGroup.month}
                className="rounded-2xl overflow-hidden"
                style={{
                  background: "var(--panel-bg)",
                  border: "1px solid var(--panel-border)",
                }}
              >
                {/* Month header */}
                <div
                  className="flex items-center gap-3 px-4 py-2.5"
                  style={{ borderBottom: monthGroup.docs.length > 0 ? "1px solid var(--row-border)" : "none" }}
                >
                  <span
                    className="text-[12.5px] font-bold w-12 shrink-0"
                    style={{ color: "var(--text-primary)" }}
                  >
                    {monthGroup.monthLabel.slice(0, 3)}
                  </span>
                  <span className="text-[11px]" style={{ color: "var(--text-dim)" }}>
                    {monthGroup.docs.length} statement{monthGroup.docs.length !== 1 ? "s" : ""}
                  </span>
                </div>

                {/* Documents in month */}
                {monthGroup.docs.map((doc) => {
                  const status = normalizeDocumentStatus(doc);
                  const inst = normalizeDocumentInstitution(doc);
                  const acct = normalizeDocumentAccount(doc);

                  return (
                    <button
                      key={doc.id}
                      onClick={() => onDocClick(doc)}
                      className="w-full flex items-center justify-between px-4 py-2.5 transition-colors text-left group"
                      style={{ borderTop: "1px solid var(--row-border)" }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = "var(--row-bg)")}
                      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div
                          className="w-7 h-7 rounded-xl shrink-0 flex items-center justify-center"
                          style={{ background: "rgba(34,211,238,0.07)", color: "rgba(34,211,238,0.60)" }}
                        >
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                            <polyline points="14 2 14 8 20 8" />
                          </svg>
                        </div>
                        <div className="min-w-0">
                          <p className="text-[12px] font-semibold truncate" style={{ color: "var(--text-primary)" }}>
                            {inst !== "Unknown" ? inst : acct}
                            {acct !== "Unknown Account" && inst !== "Unknown" && (
                              <span className="font-normal ml-1" style={{ color: "var(--text-muted)" }}>
                                · {acct}
                              </span>
                            )}
                          </p>
                        </div>
                      </div>
                      <DocumentStatusBadge status={status} size="xs" />
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
