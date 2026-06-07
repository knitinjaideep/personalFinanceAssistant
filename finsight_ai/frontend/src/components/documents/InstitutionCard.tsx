import { useState } from "react";
import { ChevronDown, ChevronRight, Landmark, CreditCard, Calendar } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import type { DocumentSummary, DocumentIssue } from "../../types";
import type { InstitutionEntry, AccountEntry, YearEntry } from "../../lib/documentLibrary";
import { DocumentStatusBadge } from "./DocumentStatusBadge";
import { MonthStatementRow } from "./MonthStatementRow";
import { relativeTime } from "../../lib/documentLibrary";

interface Props {
  institution: InstitutionEntry;
  onChanged: () => void;
  onDocClick: (doc: DocumentSummary) => void;
  issuesByDoc?: Record<string, DocumentIssue>;
}

function Collapse({ open, children }: { open: boolean; children: React.ReactNode }) {
  return (
    <AnimatePresence initial={false}>
      {open && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          style={{ overflow: "hidden" }}
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function YearAccordion({
  institutionSlug,
  account,
  yearEntry,
  onChanged,
  onDocClick,
  issuesByDoc,
}: {
  institutionSlug: string;
  account: string;
  yearEntry: YearEntry;
  onChanged: () => void;
  onDocClick: (doc: DocumentSummary) => void;
  issuesByDoc?: Record<string, DocumentIssue>;
}) {
  const [open, setOpen] = useState(false);
  const key = `y:${institutionSlug}:${account}:${yearEntry.year}`;

  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 pl-9 pr-4 py-2 transition-colors"
        style={{ background: open ? "var(--accordion-open-bg)" : "transparent" }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--row-bg)")}
        onMouseLeave={(e) => (e.currentTarget.style.background = open ? "var(--accordion-open-bg)" : "transparent")}
        data-key={key}
      >
        <motion.span animate={{ rotate: open ? 90 : 0 }} transition={{ duration: 0.18 }} style={{ color: "var(--border-accent)" }}>
          <ChevronRight size={13} />
        </motion.span>
        <Calendar size={11} style={{ color: "var(--border-accent)" }} />
        <span className="coral-table-text font-semibold" style={{ color: "var(--text-secondary)" }}>
          {yearEntry.yearLabel}
        </span>
        <span className="coral-badge-text" style={{ color: "var(--text-dim)" }}>
          ({yearEntry.docs.length})
        </span>
      </button>
      <Collapse open={open}>
        {yearEntry.months.flatMap((m) =>
          m.docs.map((doc) => (
            <MonthStatementRow
              key={doc.id}
              doc={doc}
              onChanged={onChanged}
              onClick={onDocClick}
              issueCount={issuesByDoc?.[doc.id]?.issues.length ?? 0}
            />
          ))
        )}
      </Collapse>
    </div>
  );
}

function AccountAccordion({
  institutionSlug,
  account,
  onChanged,
  onDocClick,
  issuesByDoc,
}: {
  institutionSlug: string;
  account: AccountEntry;
  onChanged: () => void;
  onDocClick: (doc: DocumentSummary) => void;
  issuesByDoc?: Record<string, DocumentIssue>;
}) {
  const [open, setOpen] = useState(true);

  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 pl-5 pr-4 py-2.5 transition-colors"
        style={{
          borderTop: "1px solid var(--row-border)",
          background: open ? "var(--accordion-open-bg)" : "transparent",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--row-bg)")}
        onMouseLeave={(e) => (e.currentTarget.style.background = open ? "var(--accordion-open-bg)" : "transparent")}
      >
        <motion.span animate={{ rotate: open ? 90 : 0 }} transition={{ duration: 0.18 }} style={{ color: "var(--border-accent)" }}>
          <ChevronRight size={14} />
        </motion.span>
        <CreditCard size={13} style={{ color: "var(--border-accent)" }} />
        <span className="coral-table-text font-bold flex-1 text-left" style={{ color: "var(--text-primary)" }}>
          {account.account}
        </span>
        <span className="coral-badge-text mr-2" style={{ color: "var(--text-dim)" }}>
          {account.totalDocs} statement{account.totalDocs !== 1 ? "s" : ""}
        </span>
        {account.latestDate && (
          <span className="coral-badge-text mr-2" style={{ color: "var(--text-dim)" }}>
            {relativeTime(account.latestDate)}
          </span>
        )}
        <DocumentStatusBadge status={account.overallStatus} size="xs" />
      </button>
      <Collapse open={open}>
        {account.years.map((yr) => (
          <YearAccordion
            key={yr.yearLabel}
            institutionSlug={institutionSlug}
            account={account.account}
            yearEntry={yr}
            onChanged={onChanged}
            onDocClick={onDocClick}
            issuesByDoc={issuesByDoc}
          />
        ))}
      </Collapse>
    </div>
  );
}

export function InstitutionCard({ institution, onChanged, onDocClick, issuesByDoc }: Props) {
  const [open, setOpen] = useState(true);

  return (
    <div
      className="rounded-2xl overflow-hidden transition-all duration-300"
      style={{
        background: "var(--panel-bg)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        border: "1px solid var(--panel-border-accent)",
        boxShadow: "var(--panel-shadow)",
      }}
    >
      {/* Institution header */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 px-4 py-3.5 transition-colors"
        style={{ background: open ? "var(--accordion-open-bg)" : "transparent" }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--row-bg)")}
        onMouseLeave={(e) => (e.currentTarget.style.background = open ? "var(--accordion-open-bg)" : "transparent")}
      >
        <div
          className="p-1.5 rounded-lg shrink-0"
          style={{ background: "var(--insight-bg)", color: "var(--border-accent)" }}
        >
          <Landmark size={14} />
        </div>

        <div className="flex-1 text-left min-w-0">
          <p className="coral-card-title font-bold leading-tight" style={{ color: "var(--text-primary)" }}>
            {institution.label}
          </p>
          <p className="coral-badge-text mt-0.5 flex items-center gap-1.5 flex-wrap" style={{ color: "var(--text-muted)" }}>
            <span>{institution.accounts.length} account{institution.accounts.length !== 1 ? "s" : ""}</span>
            <span style={{ color: "var(--text-dim)" }}>·</span>
            <span>{institution.totalDocs} statement{institution.totalDocs !== 1 ? "s" : ""}</span>
            {institution.latestDate && (
              <>
                <span style={{ color: "var(--text-dim)" }}>·</span>
                <span>Last updated {relativeTime(institution.latestDate)}</span>
              </>
            )}
          </p>
        </div>

        <DocumentStatusBadge status={institution.overallStatus} size="sm" />

        <motion.span
          animate={{ rotate: open ? 180 : 0 }}
          transition={{ duration: 0.2 }}
          style={{ color: "var(--text-dim)" }}
        >
          <ChevronDown size={15} />
        </motion.span>
      </button>

      <Collapse open={open}>
        {institution.accounts.map((acct) => (
          <AccountAccordion
            key={acct.account}
            institutionSlug={institution.slug}
            account={acct}
            onChanged={onChanged}
            onDocClick={onDocClick}
            issuesByDoc={issuesByDoc}
          />
        ))}
      </Collapse>
    </div>
  );
}
