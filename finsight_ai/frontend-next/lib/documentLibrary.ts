/**
 * documentLibrary.ts — Financial Library data utilities for frontend-next.
 * Ported from frontend/src/lib/documentLibrary.ts + frontend/src/utils/documentUtils.ts
 */

import type { DocumentSummary, DocumentStatus, DocumentIssue, IngestionHealth } from "@/types/index";

// ── Status normalization ─────────────────────────────────────────────────────

const STATUS_ALIASES: Record<string, DocumentStatus> = {
  parsed: "parsed", completed: "parsed", processed: "parsed", success: "parsed", done: "parsed",
  processing: "processing", in_progress: "processing", inprogress: "processing", running: "processing",
  uploaded: "uploaded", pending: "uploaded", queued: "uploaded",
  failed: "failed", error: "failed",
};

export function normalizeStatus(value: string | null | undefined): DocumentStatus {
  if (!value) return "uploaded";
  return STATUS_ALIASES[value.trim().toLowerCase()] ?? "uploaded";
}

// ── Month helpers ────────────────────────────────────────────────────────────

const MONTH_NAMES = [
  "January","February","March","April","May","June",
  "July","August","September","October","November","December",
];

const MONTH_LOOKUP: Record<string, number> = {
  jan:1, january:1, feb:2, february:2, mar:3, march:3, apr:4, april:4,
  may:5, jun:6, june:6, jul:7, july:7, aug:8, august:8,
  sep:9, sept:9, september:9, oct:10, october:10, nov:11, november:11, dec:12, december:12,
};

export function normalizeMonth(value: string | number | null | undefined): number | null {
  if (value == null) return null;
  if (typeof value === "number") return value >= 1 && value <= 12 ? value : null;
  const raw = value.trim().toLowerCase();
  if (!raw) return null;
  if (/^\d{1,2}$/.test(raw)) { const n = parseInt(raw, 10); return n >= 1 && n <= 12 ? n : null; }
  if (MONTH_LOOKUP[raw] != null) return MONTH_LOOKUP[raw];
  const alpha = raw.replace(/[^a-z]/g, "");
  if (MONTH_LOOKUP[alpha] != null) return MONTH_LOOKUP[alpha];
  for (const [token, num] of Object.entries(MONTH_LOOKUP)) {
    if (token.length >= 3 && alpha.includes(token)) return num;
  }
  if (alpha.length > 3) { const t = alpha.slice(1); if (MONTH_LOOKUP[t] != null) return MONTH_LOOKUP[t]; }
  return null;
}

export function monthName(month: number | null | undefined): string | null {
  if (month == null || month < 1 || month > 12) return null;
  return MONTH_NAMES[month - 1];
}

export function monthShort(month: number | null | undefined): string | null {
  const n = monthName(month);
  return n ? n.slice(0, 3) : null;
}

// ── Institution inference ────────────────────────────────────────────────────

export const INSTITUTION_DISPLAY: Record<string, string> = {
  amex: "American Express", american_express: "American Express",
  chase: "Chase", morgan_stanley: "Morgan Stanley",
  etrade: "E*TRADE", discover: "Discover",
  bofa: "Bank of America", marcus: "Marcus", unknown: "Unknown",
};

const INST_HINTS: Array<[string, RegExp]> = [
  ["amex", /(amex|american[\s_-]?express|blue[\s_-]?cash|gold[\s_-]?card|platinum)/i],
  ["chase", /(chase|sapphire|freedom)/i],
  ["morgan_stanley", /(morgan[\s_-]?stanley|morgan|stanley)/i],
  ["etrade", /(e[\s_*-]?trade)/i],
  ["discover", /(discover)/i],
];

export function inferInstitution(doc: DocumentSummary): string {
  const fromMeta = doc.institution?.trim().toLowerCase();
  if (fromMeta && fromMeta !== "unknown") return fromMeta;
  if (doc.account_product) {
    const lead = doc.account_product.split(/[—–\-|]/)[0]?.trim().toLowerCase();
    for (const [slug, label] of Object.entries(INSTITUTION_DISPLAY)) {
      if (lead && (lead === slug || lead === label.toLowerCase())) return slug;
    }
  }
  for (const [slug, re] of INST_HINTS) { if (re.test(doc.filename)) return slug; }
  return "unknown";
}

export function institutionLabel(slug: string): string {
  return INSTITUTION_DISPLAY[slug] ?? slug.replace(/_/g, " ");
}

// ── Account inference ────────────────────────────────────────────────────────

const ACCT_HINTS: Array<[string, RegExp]> = [
  ["Blue Cash", /blue[\s_-]?cash/i], ["Gold", /gold/i], ["Platinum", /platinum/i],
  ["Sapphire", /sapphire/i], ["Freedom", /freedom/i], ["Checking", /checking/i],
  ["Savings", /savings/i], ["Investment Account", /(investment|brokerage|ira|roth|advisory)/i],
];

const ACCT_TYPE_LABELS: Record<string, string> = {
  credit_card:"Credit Card", checking:"Checking", savings:"Savings",
  ira:"Investment Account", roth_ira:"Investment Account",
  advisory:"Investment Account", individual_brokerage:"Investment Account", "401k":"Investment Account",
};

export function inferAccount(doc: DocumentSummary): string {
  if (doc.account_product) {
    const parts = doc.account_product.split(/[—–|]/).map((p) => p.trim());
    const tail = parts.length > 1 ? parts[parts.length - 1] : "";
    if (tail) return tail;
  }
  for (const [label, re] of ACCT_HINTS) { if (re.test(doc.filename)) return label; }
  if (doc.account_type && ACCT_TYPE_LABELS[doc.account_type]) return ACCT_TYPE_LABELS[doc.account_type];
  return "Unknown Account";
}

// ── Year / month inference ───────────────────────────────────────────────────

export function inferYear(doc: DocumentSummary): number | null {
  const m = doc.filename.match(/(?:19|20)\d{2}/);
  if (m) return Number(m[0]);
  if (doc.statement_year) return doc.statement_year;
  if (doc.period_end) { const y = Number(doc.period_end.slice(0, 4)); if (y) return y; }
  return null;
}

export function inferMonth(doc: DocumentSummary): number | null {
  const tokens = doc.filename.replace(/\.pdf$/i, "").split(/[_\-\s.]+/);
  for (const tok of tokens) { const m = normalizeMonth(tok); if (m) return m; }
  if (doc.statement_month) return doc.statement_month;
  if (doc.period_end) { const mm = Number(doc.period_end.slice(5, 7)); if (mm >= 1 && mm <= 12) return mm; }
  return null;
}

// ── UI status type ───────────────────────────────────────────────────────────

export type LibraryStatus = "parsed"|"processing"|"uploaded"|"failed"|"needs_review"|"duplicate"|"unknown";

export function normalizeDocumentStatus(doc: DocumentSummary | null | undefined): LibraryStatus {
  if (!doc) return "unknown";
  return normalizeStatus(doc.status) as LibraryStatus;
}

export function normalizeDocumentInstitution(doc: DocumentSummary | null | undefined): string {
  if (!doc) return "Unknown";
  return institutionLabel(inferInstitution(doc));
}

export function normalizeDocumentAccount(doc: DocumentSummary | null | undefined): string {
  if (!doc) return "Unknown Account";
  return inferAccount(doc) || "Unknown Account";
}

export function normalizeDocumentYear(doc: DocumentSummary | null | undefined): number | null {
  if (!doc) return null;
  return inferYear(doc);
}

export function normalizeDocumentMonth(doc: DocumentSummary | null | undefined): number | null {
  if (!doc) return null;
  return inferMonth(doc);
}

// ── Grouping types ───────────────────────────────────────────────────────────

export interface MonthEntry { month: number | null; monthLabel: string; docs: DocumentSummary[]; }
export interface YearEntry  { year: number | null; yearLabel: string; months: MonthEntry[]; docs: DocumentSummary[]; }
export interface AccountEntry { account: string; years: YearEntry[]; totalDocs: number; latestDate: string | null; overallStatus: LibraryStatus; }
export interface InstitutionEntry { slug: string; label: string; accounts: AccountEntry[]; totalDocs: number; latestDate: string | null; overallStatus: LibraryStatus; }

function pickLatest(...dates: (string | null | undefined)[]): string | null {
  const valid = (dates.filter(Boolean) as string[]).sort().reverse();
  return valid[0] ?? null;
}

function rollupStatus(statuses: LibraryStatus[]): LibraryStatus {
  if (statuses.includes("failed")) return "failed";
  if (statuses.includes("needs_review")) return "needs_review";
  if (statuses.includes("processing")) return "processing";
  if (statuses.every((s) => s === "parsed")) return "parsed";
  if (statuses.includes("parsed")) return "parsed";
  return "uploaded";
}

export function groupDocumentsByInstitution(docs: DocumentSummary[]): InstitutionEntry[] {
  const byInst = new Map<string, Map<string, Map<number | null, Map<number | null, DocumentSummary[]>>>>();
  for (const doc of docs) {
    const inst = inferInstitution(doc), acct = inferAccount(doc);
    const year = inferYear(doc), month = inferMonth(doc);
    if (!byInst.has(inst)) byInst.set(inst, new Map());
    const acctMap = byInst.get(inst)!;
    if (!acctMap.has(acct)) acctMap.set(acct, new Map());
    const yearMap = acctMap.get(acct)!;
    if (!yearMap.has(year)) yearMap.set(year, new Map());
    const monthMap = yearMap.get(year)!;
    if (!monthMap.has(month)) monthMap.set(month, []);
    monthMap.get(month)!.push(doc);
  }

  const result: InstitutionEntry[] = [];
  for (const [slug, acctMap] of byInst) {
    const accounts: AccountEntry[] = [];
    for (const [account, yearMap] of acctMap) {
      const years: YearEntry[] = [];
      let acctLatest: string | null = null;
      const acctStatuses: LibraryStatus[] = [];
      for (const [year, monthMap] of yearMap) {
        const months: MonthEntry[] = [];
        const allDocs: DocumentSummary[] = [];
        for (const [month, mDocs] of monthMap) {
          months.push({ month, monthLabel: month != null ? (monthName(month) ?? String(month)) : "Unknown Month", docs: mDocs });
          allDocs.push(...mDocs);
        }
        months.sort((a, b) => (a.month == null ? 1 : b.month == null ? -1 : b.month - a.month));
        for (const doc of allDocs) {
          acctLatest = pickLatest(acctLatest, doc.upload_time, doc.processed_time);
          acctStatuses.push(normalizeDocumentStatus(doc));
        }
        years.push({ year, yearLabel: year != null ? String(year) : "Unknown Year", months, docs: allDocs });
      }
      years.sort((a, b) => (a.year == null ? 1 : b.year == null ? -1 : b.year - a.year));
      accounts.push({ account, years, totalDocs: years.reduce((n, y) => n + y.docs.length, 0), latestDate: acctLatest, overallStatus: rollupStatus(acctStatuses) });
    }
    accounts.sort((a, b) => a.account === "Unknown Account" ? 1 : b.account === "Unknown Account" ? -1 : a.account.localeCompare(b.account));
    const instLatest = accounts.reduce<string | null>((d, a) => pickLatest(d, a.latestDate), null);
    result.push({ slug, label: institutionLabel(slug), accounts, totalDocs: accounts.reduce((n, a) => n + a.totalDocs, 0), latestDate: instLatest, overallStatus: rollupStatus(accounts.map((a) => a.overallStatus)) });
  }
  result.sort((a, b) => a.slug === "unknown" ? 1 : b.slug === "unknown" ? -1 : a.label.localeCompare(b.label));
  return result;
}

// ── Coverage grid ────────────────────────────────────────────────────────────

export interface CoverageCell { status: "parsed"|"processing"|"failed"|"uploaded"|"missing"; docs: DocumentSummary[]; count: number; }
export interface CoverageRow  { account: string; institution: string; institutionSlug: string; cells: Record<number, CoverageCell>; }

export function buildStatementCoverage(docs: DocumentSummary[], year: number): CoverageRow[] {
  const yearDocs = docs.filter((d) => inferYear(d) === year);
  const byAcct = new Map<string, { inst: string; slug: string; byMonth: Map<number, DocumentSummary[]> }>();
  for (const doc of yearDocs) {
    const acct = inferAccount(doc), slug = inferInstitution(doc), month = inferMonth(doc);
    if (!byAcct.has(acct)) byAcct.set(acct, { inst: institutionLabel(slug), slug, byMonth: new Map() });
    if (month != null) {
      const m = byAcct.get(acct)!.byMonth;
      if (!m.has(month)) m.set(month, []);
      m.get(month)!.push(doc);
    }
  }
  const rows: CoverageRow[] = [];
  for (const [account, { inst, slug, byMonth }] of byAcct) {
    const cells: Record<number, CoverageCell> = {};
    for (let m = 1; m <= 12; m++) {
      const mDocs = byMonth.get(m) ?? [];
      if (mDocs.length === 0) { cells[m] = { status: "missing", docs: [], count: 0 }; continue; }
      const statuses = mDocs.map((d) => normalizeStatus(d.status));
      const status = statuses.includes("parsed") ? "parsed" : statuses.includes("processing") ? "processing" : statuses.includes("failed") ? "failed" : "uploaded";
      cells[m] = { status, docs: mDocs, count: mDocs.length };
    }
    rows.push({ account, institution: inst, institutionSlug: slug, cells });
  }
  rows.sort((a, b) => a.institution !== b.institution ? a.institution.localeCompare(b.institution) : a.account.localeCompare(b.account));
  return rows;
}

// ── Timeline ─────────────────────────────────────────────────────────────────

export interface TimelineMonth { month: number; monthLabel: string; docs: DocumentSummary[]; }
export interface TimelineYear  { year: number; months: TimelineMonth[]; totalDocs: number; }

export function buildTimeline(docs: DocumentSummary[]): TimelineYear[] {
  const byYear = new Map<number, Map<number, DocumentSummary[]>>();
  for (const doc of docs) {
    const year = inferYear(doc), month = inferMonth(doc);
    if (year == null) continue;
    if (!byYear.has(year)) byYear.set(year, new Map());
    const key = month ?? 0;
    const bm = byYear.get(year)!;
    if (!bm.has(key)) bm.set(key, []);
    bm.get(key)!.push(doc);
  }
  const years: TimelineYear[] = [];
  for (const [year, byMonth] of byYear) {
    const months: TimelineMonth[] = [];
    for (const [month, mDocs] of byMonth) {
      months.push({ month, monthLabel: month > 0 ? (monthName(month) ?? String(month)) : "Unknown Month", docs: mDocs });
    }
    months.sort((a, b) => b.month - a.month);
    years.push({ year, months, totalDocs: months.reduce((n, m) => n + m.docs.length, 0) });
  }
  years.sort((a, b) => b.year - a.year);
  return years;
}

// ── Needs attention ──────────────────────────────────────────────────────────

export interface AttentionItem { doc: DocumentSummary; reasons: string[]; recommendedAction: string; issue?: DocumentIssue; }

const STUCK_MS = 10 * 60_000;

export function findDocumentsNeedingAttention(docs: DocumentSummary[], issuesByDoc?: Record<string, DocumentIssue>): AttentionItem[] {
  const items: AttentionItem[] = [];
  for (const doc of docs) {
    const reasons: string[] = [];
    const s = normalizeStatus(doc.status);
    const issue = issuesByDoc?.[doc.id];
    if (s === "failed") reasons.push(doc.error ? `Parse failed: ${doc.error}` : "Parsing failed");
    if (s === "processing") {
      const t = doc.upload_time ? new Date(doc.upload_time).getTime() : null;
      if (t && Date.now() - t > STUCK_MS) reasons.push("Processing appears stuck (>10 min)");
    }
    if (issue?.issues.length) for (const code of issue.issues) reasons.push(issueCodeToLabel(code));
    if (inferInstitution(doc) === "unknown") reasons.push("Institution not recognized");
    if (inferAccount(doc) === "Unknown Account") reasons.push("Account not identified");
    if (s === "parsed" && inferYear(doc) === null) reasons.push("Statement year not detected");
    if (reasons.length > 0) items.push({ doc, reasons, recommendedAction: issue?.recommended_action ?? suggestAction(s, reasons), issue });
  }
  return items;
}

function suggestAction(status: string, reasons: string[]): string {
  if (status === "failed") return "Reprocess document";
  if (reasons.some((r) => r.includes("stuck"))) return "Reprocess document";
  if (reasons.some((r) => r.includes("Institution") || r.includes("Account"))) return "Check filename format";
  return "Review document";
}

function issueCodeToLabel(code: string): string {
  const map: Record<string, string> = {
    zero_transactions:"No transactions extracted", zero_chunks:"No text chunks indexed",
    missing_embeddings:"Missing embeddings", missing_institution:"Unknown institution",
    missing_month:"Statement month not detected", missing_year:"Statement year not detected",
    no_statement_persisted:"No statement record saved", stuck_processing:"Stuck in processing", failed:"Parsing failed",
  };
  return map[code] ?? code.replace(/_/g, " ");
}

// ── Helpers ──────────────────────────────────────────────────────────────────

export function relativeTime(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return "—";
  const diff = Date.now() - d.getTime();
  const mins = Math.floor(diff / 60_000);
  const hrs = Math.floor(diff / 3_600_000);
  const days = Math.floor(diff / 86_400_000);
  if (mins < 2) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (hrs < 24) return `${hrs}h ago`;
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString();
}

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function getRecentlyAddedDocuments(docs: DocumentSummary[], limit = 6): DocumentSummary[] {
  return [...docs].filter((d) => d.upload_time)
    .sort((a, b) => new Date(b.upload_time!).getTime() - new Date(a.upload_time!).getTime())
    .slice(0, limit);
}

export interface LibraryHealthSummary { totalParsed: number; needsReview: number; institutionCount: number; processingCount: number; }

export function computeLibraryHealth(docs: DocumentSummary[], health?: IngestionHealth | null): LibraryHealthSummary {
  const slugs = new Set(docs.map(inferInstitution)); slugs.delete("unknown");
  return {
    totalParsed: docs.filter((d) => normalizeStatus(d.status) === "parsed").length,
    needsReview: health?.summary.incomplete_documents ?? docs.filter((d) => normalizeStatus(d.status) === "failed").length,
    institutionCount: slugs.size,
    processingCount: docs.filter((d) => normalizeStatus(d.status) === "processing").length,
  };
}
