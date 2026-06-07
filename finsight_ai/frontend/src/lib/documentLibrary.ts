/**
 * documentLibrary.ts — Financial Library data utilities.
 *
 * All functions are defensive: handle null/undefined, never throw on malformed
 * documents, return "Unknown" where metadata is missing.
 */

import type { DocumentSummary, DocumentIssue, IngestionHealth } from "../types";
import {
  normalizeStatus,
  inferInstitution,
  institutionLabel,
  inferAccount,
  inferYear,
  inferMonth,
  monthName,
  monthShort,
} from "../utils/documentUtils";

// ── Re-export helpers so consumers only need one import ──────────────────────

export { normalizeStatus, inferInstitution, institutionLabel, inferAccount, inferYear, inferMonth, monthName, monthShort };

// ── UI status type (superset of DocumentStatus) ──────────────────────────────

export type LibraryStatus =
  | "parsed"
  | "processing"
  | "uploaded"
  | "failed"
  | "needs_review"
  | "duplicate"
  | "unknown";

export function normalizeDocumentStatus(doc: DocumentSummary | null | undefined): LibraryStatus {
  if (!doc) return "unknown";
  const s = normalizeStatus(doc.status);
  return s;
}

// ── Display helpers ───────────────────────────────────────────────────────────

export function normalizeDocumentInstitution(doc: DocumentSummary | null | undefined): string {
  if (!doc) return "Unknown";
  const slug = inferInstitution(doc);
  return institutionLabel(slug);
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

export function getDocumentDisplayName(doc: DocumentSummary | null | undefined): string {
  if (!doc) return "Unknown Document";
  const inst = normalizeDocumentInstitution(doc);
  const acct = normalizeDocumentAccount(doc);
  const year = normalizeDocumentYear(doc);
  const month = normalizeDocumentMonth(doc);
  const parts: string[] = [];
  if (inst !== "Unknown") parts.push(inst);
  if (acct !== "Unknown Account") parts.push(acct);
  if (month) parts.push(monthShort(month) ?? "");
  if (year) parts.push(String(year));
  return parts.length > 0 ? parts.filter(Boolean).join(" · ") : doc.filename;
}

// ── Health status ─────────────────────────────────────────────────────────────

export type DocumentHealthStatus = "healthy" | "needs_attention" | "processing" | "unknown";

export function getDocumentHealthStatus(
  doc: DocumentSummary | null | undefined,
  issue?: DocumentIssue,
): DocumentHealthStatus {
  if (!doc) return "unknown";
  const s = normalizeStatus(doc.status);
  if (s === "processing") return "processing";
  if (s === "failed") return "needs_attention";
  if (issue && issue.issues.length > 0) return "needs_attention";
  if (s === "parsed") return "healthy";
  return "unknown";
}

// ── Needs attention ───────────────────────────────────────────────────────────

export interface AttentionItem {
  doc: DocumentSummary;
  reasons: string[];
  recommendedAction: string;
  issue?: DocumentIssue;
}

const STUCK_THRESHOLD_MS = 10 * 60 * 1000; // 10 minutes

export function findDocumentsNeedingAttention(
  docs: DocumentSummary[],
  issuesByDoc?: Record<string, DocumentIssue>,
): AttentionItem[] {
  const items: AttentionItem[] = [];

  for (const doc of docs) {
    if (!doc) continue;
    const reasons: string[] = [];
    const s = normalizeStatus(doc.status);
    const issue = issuesByDoc?.[doc.id];

    if (s === "failed") {
      reasons.push(doc.error ? `Parse failed: ${doc.error}` : "Parsing failed");
    }

    if (s === "processing") {
      const uploadedAt = doc.upload_time ? new Date(doc.upload_time).getTime() : null;
      const now = Date.now();
      if (uploadedAt && now - uploadedAt > STUCK_THRESHOLD_MS) {
        reasons.push("Processing appears stuck (>10 min)");
      }
    }

    if (issue && issue.issues.length > 0) {
      for (const code of issue.issues) {
        reasons.push(issueCodeToLabel(code));
      }
    }

    const inst = inferInstitution(doc);
    if (inst === "unknown") reasons.push("Institution not recognized");

    const acct = inferAccount(doc);
    if (acct === "Unknown Account") reasons.push("Account not identified");

    if (s === "parsed" && normalizeDocumentYear(doc) === null) {
      reasons.push("Statement year not detected");
    }

    if (reasons.length > 0) {
      items.push({
        doc,
        reasons,
        recommendedAction: issue?.recommended_action ?? suggestAction(s, reasons),
        issue,
      });
    }
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
    zero_transactions: "No transactions extracted",
    zero_chunks: "No text chunks indexed",
    missing_embeddings: "Missing embeddings",
    missing_institution: "Unknown institution",
    missing_month: "Statement month not detected",
    missing_year: "Statement year not detected",
    no_statement_persisted: "No statement record saved",
    stuck_processing: "Stuck in processing",
    failed: "Parsing failed",
  };
  return map[code] ?? code.replace(/_/g, " ");
}

// ── Grouping ──────────────────────────────────────────────────────────────────

export interface MonthEntry {
  month: number | null;
  monthLabel: string;
  docs: DocumentSummary[];
}

export interface YearEntry {
  year: number | null;
  yearLabel: string;
  months: MonthEntry[];
  docs: DocumentSummary[];
}

export interface AccountEntry {
  account: string;
  years: YearEntry[];
  totalDocs: number;
  latestDate: string | null;
  overallStatus: LibraryStatus;
}

export interface InstitutionEntry {
  slug: string;
  label: string;
  accounts: AccountEntry[];
  totalDocs: number;
  latestDate: string | null;
  overallStatus: LibraryStatus;
}

function pickLatestDate(...dates: (string | null | undefined)[]): string | null {
  const valid = dates.filter(Boolean) as string[];
  if (valid.length === 0) return null;
  return valid.sort().reverse()[0];
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
    if (!doc) continue;
    const inst = inferInstitution(doc);
    const acct = inferAccount(doc);
    const year = inferYear(doc);
    const month = inferMonth(doc);

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
        const allYearDocs: DocumentSummary[] = [];

        for (const [month, mDocs] of monthMap) {
          months.push({
            month,
            monthLabel: month != null ? (monthName(month) ?? String(month)) : "Unknown Month",
            docs: mDocs,
          });
          allYearDocs.push(...mDocs);
        }

        months.sort((a, b) => {
          if (a.month == null) return 1;
          if (b.month == null) return -1;
          return b.month - a.month;
        });

        for (const doc of allYearDocs) {
          acctLatest = pickLatestDate(acctLatest, doc.upload_time, doc.processed_time);
          acctStatuses.push(normalizeDocumentStatus(doc));
        }

        years.push({
          year,
          yearLabel: year != null ? String(year) : "Unknown Year",
          months,
          docs: allYearDocs,
        });
      }

      years.sort((a, b) => {
        if (a.year == null) return 1;
        if (b.year == null) return -1;
        return b.year - a.year;
      });

      accounts.push({
        account,
        years,
        totalDocs: years.reduce((n, y) => n + y.docs.length, 0),
        latestDate: acctLatest,
        overallStatus: rollupStatus(acctStatuses),
      });
    }

    accounts.sort((a, b) => {
      if (a.account === "Unknown Account") return 1;
      if (b.account === "Unknown Account") return -1;
      return a.account.localeCompare(b.account);
    });

    const instLatest = accounts.reduce<string | null>((d, a) => pickLatestDate(d, a.latestDate), null);
    const instStatuses = accounts.map((a) => a.overallStatus);

    result.push({
      slug,
      label: institutionLabel(slug),
      accounts,
      totalDocs: accounts.reduce((n, a) => n + a.totalDocs, 0),
      latestDate: instLatest,
      overallStatus: rollupStatus(instStatuses),
    });
  }

  result.sort((a, b) => {
    if (a.slug === "unknown") return 1;
    if (b.slug === "unknown") return -1;
    return a.label.localeCompare(b.label);
  });

  return result;
}

export function groupDocumentsByAccount(docs: DocumentSummary[]): Record<string, DocumentSummary[]> {
  const map: Record<string, DocumentSummary[]> = {};
  for (const doc of docs) {
    const key = inferAccount(doc);
    if (!map[key]) map[key] = [];
    map[key].push(doc);
  }
  return map;
}

export function groupDocumentsByYear(docs: DocumentSummary[]): Record<number | string, DocumentSummary[]> {
  const map: Record<string, DocumentSummary[]> = {};
  for (const doc of docs) {
    const key = String(inferYear(doc) ?? "Unknown");
    if (!map[key]) map[key] = [];
    map[key].push(doc);
  }
  return map;
}

// ── Statement coverage grid ───────────────────────────────────────────────────

export interface CoverageCell {
  status: "parsed" | "processing" | "failed" | "uploaded" | "missing";
  docs: DocumentSummary[];
  count: number;
}

export interface CoverageRow {
  account: string;
  institution: string;
  institutionSlug: string;
  cells: Record<number, CoverageCell>; // month 1-12
}

export function buildStatementCoverage(docs: DocumentSummary[], year: number): CoverageRow[] {
  const yearDocs = docs.filter((d) => inferYear(d) === year);
  const byAcct = new Map<string, { inst: string; slug: string; byMonth: Map<number, DocumentSummary[]> }>();

  for (const doc of yearDocs) {
    const acct = inferAccount(doc);
    const month = inferMonth(doc);
    const slug = inferInstitution(doc);
    const inst = institutionLabel(slug);

    if (!byAcct.has(acct)) {
      byAcct.set(acct, { inst, slug, byMonth: new Map() });
    }
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
      if (mDocs.length === 0) {
        cells[m] = { status: "missing", docs: [], count: 0 };
      } else {
        const statuses = mDocs.map((d) => normalizeStatus(d.status));
        const status = statuses.includes("parsed")
          ? "parsed"
          : statuses.includes("processing")
          ? "processing"
          : statuses.includes("failed")
          ? "failed"
          : "uploaded";
        cells[m] = { status, docs: mDocs, count: mDocs.length };
      }
    }
    rows.push({ account, institution: inst, institutionSlug: slug, cells });
  }

  rows.sort((a, b) => {
    if (a.institution !== b.institution) return a.institution.localeCompare(b.institution);
    return a.account.localeCompare(b.account);
  });

  return rows;
}

// ── Recently added ────────────────────────────────────────────────────────────

export function getRecentlyAddedDocuments(docs: DocumentSummary[], limit = 6): DocumentSummary[] {
  return [...docs]
    .filter((d) => d.upload_time)
    .sort((a, b) => {
      const ta = a.upload_time ? new Date(a.upload_time).getTime() : 0;
      const tb = b.upload_time ? new Date(b.upload_time).getTime() : 0;
      return tb - ta;
    })
    .slice(0, limit);
}

// ── Data health summary ───────────────────────────────────────────────────────

export interface LibraryHealthSummary {
  totalParsed: number;
  needsReview: number;
  institutionCount: number;
  processingCount: number;
}

export function computeLibraryHealth(
  docs: DocumentSummary[],
  health?: IngestionHealth | null,
): LibraryHealthSummary {
  const slugs = new Set(docs.map((d) => inferInstitution(d)));
  slugs.delete("unknown");

  const totalParsed = docs.filter((d) => normalizeStatus(d.status) === "parsed").length;
  const processingCount = docs.filter((d) => normalizeStatus(d.status) === "processing").length;
  const needsReview = health?.summary.incomplete_documents
    ?? docs.filter((d) => {
      const s = normalizeStatus(d.status);
      return s === "failed";
    }).length;

  return {
    totalParsed,
    needsReview,
    institutionCount: slugs.size,
    processingCount,
  };
}

// ── Timeline grouping ─────────────────────────────────────────────────────────

export interface TimelineMonth {
  month: number;
  monthLabel: string;
  docs: DocumentSummary[];
}

export interface TimelineYear {
  year: number;
  months: TimelineMonth[];
  totalDocs: number;
}

export function buildTimeline(docs: DocumentSummary[]): TimelineYear[] {
  const byYear = new Map<number, Map<number, DocumentSummary[]>>();

  for (const doc of docs) {
    const year = inferYear(doc);
    const month = inferMonth(doc);
    if (year == null) continue;
    if (!byYear.has(year)) byYear.set(year, new Map());
    const byMonth = byYear.get(year)!;
    const key = month ?? 0;
    if (!byMonth.has(key)) byMonth.set(key, []);
    byMonth.get(key)!.push(doc);
  }

  const years: TimelineYear[] = [];

  for (const [year, byMonth] of byYear) {
    const months: TimelineMonth[] = [];
    for (const [month, mDocs] of byMonth) {
      months.push({
        month,
        monthLabel: month > 0 ? (monthName(month) ?? String(month)) : "Unknown Month",
        docs: mDocs,
      });
    }
    months.sort((a, b) => b.month - a.month);
    years.push({ year, months, totalDocs: months.reduce((n, m) => n + m.docs.length, 0) });
  }

  years.sort((a, b) => b.year - a.year);
  return years;
}

// ── Relative time helpers ─────────────────────────────────────────────────────

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
