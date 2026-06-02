import { ChevronRight, Landmark, CreditCard, Calendar } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import type { DocumentIssue, DocumentSummary } from "../../types";
import type {
  AccountGroup,
  InstitutionGroup,
  YearGroup,
} from "../../utils/documentUtils";
import { DocumentRow } from "./DocumentRow";

/** Stable keys for the expanded-state set. */
export const instKey = (slug: string) => `i:${slug}`;
export const acctKey = (slug: string, account: string) => `a:${slug}:${account}`;
export const yearKey = (slug: string, account: string, year: number | null) =>
  `y:${slug}:${account}:${year ?? "unknown"}`;

interface Props {
  groups: InstitutionGroup[];
  expanded: Set<string>;
  toggle: (key: string) => void;
  onChanged: () => void;
  /** document_id → ingestion issues, for per-row "incomplete" badges. */
  issuesByDoc?: Record<string, DocumentIssue>;
}

function Caret({ open }: { open: boolean }) {
  return (
    <motion.span animate={{ rotate: open ? 90 : 0 }} transition={{ duration: 0.18 }} className="text-ocean/40">
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
  slug,
  account,
  group,
  expanded,
  toggle,
  onChanged,
  issuesByDoc,
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
        className="w-full flex items-center gap-2 pl-9 pr-4 py-2 hover:bg-ocean-50/30 transition-colors"
      >
        <Caret open={open} />
        <Calendar size={12} className="text-ocean/35" />
        <span className="text-[11.5px] font-semibold text-ocean/70">{group.yearLabel}</span>
        <span className="text-[10px] text-ocean/35">({group.docs.length})</span>
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
  slug,
  group,
  expanded,
  toggle,
  onChanged,
  issuesByDoc,
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
        className="w-full flex items-center gap-2 pl-5 pr-4 py-2.5 hover:bg-ocean-50/30 transition-colors border-t border-ocean-50/40"
      >
        <Caret open={open} />
        <CreditCard size={13} className="text-ocean/45" />
        <span className="text-[12.5px] font-semibold text-ocean-deep">{group.account}</span>
        <span className="text-[10px] text-ocean/35">({group.count})</span>
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
            className="rounded-2xl overflow-hidden"
            style={{
              background: "rgba(255,255,255,0.85)",
              border: "1px solid rgba(205,237,246,0.65)",
              boxShadow: "0 4px 24px rgba(11,60,93,0.06)",
            }}
          >
            <button
              onClick={() => toggle(key)}
              className="w-full flex items-center gap-2.5 px-4 py-3.5 hover:bg-ocean-50/25 transition-colors"
            >
              <Caret open={open} />
              <div className="p-1.5 rounded-lg" style={{ background: "rgba(31,111,139,0.10)", color: "#1F6F8B" }}>
                <Landmark size={14} />
              </div>
              <span className="text-[14px] font-bold text-ocean-deep tracking-tight">{inst.label}</span>
              <span className="text-[11px] text-ocean/40 font-medium">
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
