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
  issuesByDoc?: Record<string, DocumentIssue>;
}

function Caret({ open }: { open: boolean }) {
  return (
    <motion.span animate={{ rotate: open ? 90 : 0 }} transition={{ duration: 0.18 }} style={{ color: "rgba(34,211,238,0.45)" }}>
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
        className="w-full flex items-center gap-2 pl-9 pr-4 py-2 transition-colors"
        style={{ background: open ? "rgba(34,211,238,0.04)" : "transparent" }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(34,211,238,0.06)")}
        onMouseLeave={(e) => (e.currentTarget.style.background = open ? "rgba(34,211,238,0.04)" : "transparent")}
      >
        <Caret open={open} />
        <Calendar size={12} style={{ color: "rgba(34,211,238,0.40)" }} />
        <span className="text-[11.5px] font-semibold" style={{ color: "rgba(255,255,255,0.65)" }}>{group.yearLabel}</span>
        <span className="text-[10px]" style={{ color: "rgba(255,255,255,0.28)" }}>({group.docs.length})</span>
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
        className="w-full flex items-center gap-2 pl-5 pr-4 py-2.5 transition-colors"
        style={{
          borderTop: "1px solid rgba(34,211,238,0.08)",
          background: open ? "rgba(34,211,238,0.04)" : "transparent",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(34,211,238,0.06)")}
        onMouseLeave={(e) => (e.currentTarget.style.background = open ? "rgba(34,211,238,0.04)" : "transparent")}
      >
        <Caret open={open} />
        <CreditCard size={13} style={{ color: "rgba(34,211,238,0.45)" }} />
        <span className="text-[12.5px] font-semibold text-white">{group.account}</span>
        <span className="text-[10px]" style={{ color: "rgba(255,255,255,0.28)" }}>({group.count})</span>
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
              background: "rgba(3,17,31,0.55)",
              backdropFilter: "blur(20px)",
              WebkitBackdropFilter: "blur(20px)",
              border: "1px solid rgba(34,211,238,0.12)",
              boxShadow: "0 8px 32px rgba(3,17,31,0.35)",
            }}
          >
            <button
              onClick={() => toggle(key)}
              className="w-full flex items-center gap-2.5 px-4 py-3.5 transition-colors"
              style={{ background: open ? "rgba(34,211,238,0.05)" : "transparent" }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(34,211,238,0.07)")}
              onMouseLeave={(e) => (e.currentTarget.style.background = open ? "rgba(34,211,238,0.05)" : "transparent")}
            >
              <Caret open={open} />
              <div
                className="p-1.5 rounded-lg"
                style={{ background: "rgba(34,211,238,0.12)", color: "rgba(34,211,238,0.80)" }}
              >
                <Landmark size={14} />
              </div>
              <span className="text-[14px] font-bold text-white tracking-tight">{inst.label}</span>
              <span className="text-[11px] font-medium" style={{ color: "rgba(255,255,255,0.35)" }}>
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
