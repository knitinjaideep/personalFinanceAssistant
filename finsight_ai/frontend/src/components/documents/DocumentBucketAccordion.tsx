import { ChevronRight, Landmark, CreditCard, Calendar } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import type { DocumentIssue, DocumentSummary } from "../../types";
import type {
  AccountGroup,
  InstitutionGroup,
  YearGroup,
} from "../../utils/documentUtils";
import { DocumentRow } from "./DocumentRow";

export const instKey = (slug: string) => `i:${slug}`;
export const acctKey = (slug: string, account: string) => `a:${slug}:${account}`;
export const yearKey = (slug: string, account: string, year: number | null) =>
  `y:${slug}:${account}:${year ?? "unknown"}`;

interface Props {
  groups: InstitutionGroup[];
  expanded: Set<string>;
  toggle: (key: string) => void;
  onChanged: () => void;
  issuesByDoc?: Record<string, DocumentIssue>;
}

function Caret({ open }: { open: boolean }) {
  return (
    <motion.span
      animate={{ rotate: open ? 90 : 0 }}
      transition={{ duration: 0.18 }}
      style={{ color: "var(--border-accent)" }}
    >
      <ChevronRight size={15} />
    </motion.span>
  );
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

function YearSection({
  slug, account, group, expanded, toggle, onChanged, issuesByDoc,
}: {
  slug: string;
  account: string;
  group: YearGroup;
  expanded: Set<string>;
  toggle: (k: string) => void;
  onChanged: () => void;
  issuesByDoc?: Record<string, DocumentIssue>;
}) {
  const key = yearKey(slug, account, group.year);
  const open = expanded.has(key);
  return (
    <div>
      <button
        onClick={() => toggle(key)}
        className="w-full flex items-center gap-2 pl-9 pr-4 py-2 transition-colors"
        style={{ background: open ? "var(--accordion-open-bg)" : "transparent" }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--row-bg)")}
        onMouseLeave={(e) => (e.currentTarget.style.background = open ? "var(--accordion-open-bg)" : "transparent")}
      >
        <Caret open={open} />
        <Calendar size={12} style={{ color: "var(--border-accent)" }} />
        <span className="text-[11.5px] font-semibold" style={{ color: "var(--text-secondary)" }}>
          {group.yearLabel}
        </span>
        <span className="text-[10px]" style={{ color: "var(--text-dim)" }}>
          ({group.docs.length})
        </span>
      </button>
      <Collapse open={open}>
        {group.docs.map((doc: DocumentSummary) => (
          <DocumentRow key={doc.id} doc={doc} onChanged={onChanged} issue={issuesByDoc?.[doc.id]} />
        ))}
      </Collapse>
    </div>
  );
}

function AccountSection({
  slug, group, expanded, toggle, onChanged, issuesByDoc,
}: {
  slug: string;
  group: AccountGroup;
  expanded: Set<string>;
  toggle: (k: string) => void;
  onChanged: () => void;
  issuesByDoc?: Record<string, DocumentIssue>;
}) {
  const key = acctKey(slug, group.account);
  const open = expanded.has(key);
  return (
    <div>
      <button
        onClick={() => toggle(key)}
        className="w-full flex items-center gap-2 pl-5 pr-4 py-2.5 transition-colors"
        style={{
          borderTop: "1px solid var(--row-border)",
          background: open ? "var(--accordion-open-bg)" : "transparent",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--row-bg)")}
        onMouseLeave={(e) => (e.currentTarget.style.background = open ? "var(--accordion-open-bg)" : "transparent")}
      >
        <Caret open={open} />
        <CreditCard size={13} style={{ color: "var(--border-accent)" }} />
        <span className="text-[12.5px] font-semibold" style={{ color: "var(--text-primary)" }}>
          {group.account}
        </span>
        <span className="text-[10px]" style={{ color: "var(--text-dim)" }}>
          ({group.count})
        </span>
      </button>
      <Collapse open={open}>
        {group.years.map((yg) => (
          <YearSection
            key={yearKey(slug, group.account, yg.year)}
            slug={slug}
            account={group.account}
            group={yg}
            expanded={expanded}
            toggle={toggle}
            onChanged={onChanged}
            issuesByDoc={issuesByDoc}
          />
        ))}
      </Collapse>
    </div>
  );
}

export function DocumentBucketAccordion({ groups, expanded, toggle, onChanged, issuesByDoc }: Props) {
  return (
    <div className="space-y-3">
      {groups.map((inst) => {
        const key = instKey(inst.slug);
        const open = expanded.has(key);
        return (
          <div
            key={inst.slug}
            className="rounded-2xl overflow-hidden card-shimmer-hover gradient-border-hover"
            style={{
              background: "var(--panel-bg)",
              backdropFilter: "blur(20px)",
              WebkitBackdropFilter: "blur(20px)",
              border: "1px solid var(--panel-border-accent)",
              boxShadow: "var(--panel-shadow)",
              transition: "box-shadow 0.25s ease, border-color 0.25s ease",
            }}
          >
            <button
              onClick={() => toggle(key)}
              className="w-full flex items-center gap-2.5 px-4 py-3.5 transition-colors"
              style={{ background: open ? "var(--accordion-open-bg)" : "transparent" }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "var(--row-bg)")}
              onMouseLeave={(e) => (e.currentTarget.style.background = open ? "var(--accordion-open-bg)" : "transparent")}
            >
              <Caret open={open} />
              <div
                className="p-1.5 rounded-lg shrink-0"
                style={{ background: "var(--insight-bg)", color: "var(--border-accent)" }}
              >
                <Landmark size={14} />
              </div>
              <span className="text-[14px] font-bold tracking-tight aurora-heading">
                {inst.label}
              </span>
              <span className="text-[11px] font-medium" style={{ color: "var(--text-muted)" }}>
                {inst.count} document{inst.count !== 1 ? "s" : ""}
              </span>
            </button>
            <Collapse open={open}>
              {inst.accounts.map((acct) => (
                <AccountSection
                  key={acctKey(inst.slug, acct.account)}
                  slug={inst.slug}
                  group={acct}
                  expanded={expanded}
                  toggle={toggle}
                  onChanged={onChanged}
                  issuesByDoc={issuesByDoc}
                />
              ))}
            </Collapse>
          </div>
        );
      })}
    </div>
  );
}
