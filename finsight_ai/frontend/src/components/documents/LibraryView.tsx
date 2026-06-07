import type { DocumentSummary, DocumentIssue } from "../../types";
import { InstitutionCard } from "./InstitutionCard";
import { StatementCoverageGrid } from "./StatementCoverageGrid";
import { RecentlyAddedDocuments } from "./RecentlyAddedDocuments";
import { groupDocumentsByInstitution } from "../../lib/documentLibrary";

interface Props {
  docs: DocumentSummary[];
  onChanged: () => void;
  onDocClick: (doc: DocumentSummary) => void;
  issuesByDoc?: Record<string, DocumentIssue>;
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[12px] font-semibold uppercase tracking-wider mb-3" style={{ color: "var(--text-dim)" }}>
      {children}
    </p>
  );
}

export function LibraryView({ docs, onChanged, onDocClick, issuesByDoc }: Props) {
  const institutions = groupDocumentsByInstitution(docs);

  if (docs.length === 0) {
    return (
      <div
        className="rounded-2xl px-6 py-12 text-center"
        style={{
          background: "var(--empty-bg)",
          border: "1px dashed var(--empty-border)",
        }}
      >
        <div
          className="w-12 h-12 rounded-2xl flex items-center justify-center mx-auto mb-3"
          style={{ background: "rgba(34,211,238,0.08)", color: "rgba(34,211,238,0.50)" }}
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
          </svg>
        </div>
        <p className="text-[13px] font-semibold mb-1" style={{ color: "var(--text-primary)" }}>
          No statements uploaded yet
        </p>
        <p className="text-[11.5px]" style={{ color: "var(--text-muted)" }}>
          Upload your first statement and Coral will organize it by institution, account, and month.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-7">
      {/* Statement Coverage */}
      <div>
        <SectionLabel>Statement Coverage</SectionLabel>
        <div
          className="rounded-2xl p-5"
          style={{
            background: "var(--panel-bg)",
            border: "1px solid var(--panel-border)",
            backdropFilter: "blur(16px)",
            WebkitBackdropFilter: "blur(16px)",
          }}
        >
          <StatementCoverageGrid docs={docs} />
        </div>
      </div>

      {/* Institution cards */}
      <div>
        <SectionLabel>Institutions</SectionLabel>
        <div className="space-y-3">
          {institutions.map((inst) => (
            <InstitutionCard
              key={inst.slug}
              institution={inst}
              onChanged={onChanged}
              onDocClick={onDocClick}
              issuesByDoc={issuesByDoc}
            />
          ))}
        </div>
      </div>

      {/* Recently Added */}
      <RecentlyAddedDocuments docs={docs} onDocClick={onDocClick} />
    </div>
  );
}
