/**
 * documentUtils — pure, testable business logic for the Documents dashboard.
 *
 * Responsibilities:
 *   - status normalization (tolerate casing/synonyms from any source)
 *   - month/year inference + normalization from metadata or filename
 *   - institution / account inference
 *   - grouping into Institution → Account → Year buckets
 *   - count aggregation derived from the document list (single source of truth)
 *
 * Keep this free of React so it can be unit-tested in isolation.
 */

import type { DocumentStats, DocumentStatus, DocumentSummary } from "../types";

// ── Status normalization ──────────────────────────────────────────────────────

const STATUS_ALIASES: Record<string, DocumentStatus> = {
  parsed: "parsed",
  completed: "parsed",
  processed: "parsed",
  success: "parsed",
  done: "parsed",
  processing: "processing",
  in_progress: "processing",
  inprogress: "processing",
  running: "processing",
  uploaded: "uploaded",
  pending: "uploaded",
  queued: "uploaded",
  failed: "failed",
  error: "failed",
};

/** Map any status spelling/casing to one of: parsed | processing | uploaded | failed. */
export function normalizeStatus(value: string | null | undefined): DocumentStatus {
  if (!value) return "uploaded";
  return STATUS_ALIASES[value.trim().toLowerCase()] ?? "uploaded";
}

export const STATUS_LABELS: Record<DocumentStatus, string> = {
  parsed: "Parsed",
  processing: "Processing",
  uploaded: "Uploaded",
  failed: "Failed",
};

// ── Month normalization ─────────────────────────────────────────────────────--

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const MONTH_LOOKUP: Record<string, number> = {
  jan: 1, january: 1,
  feb: 2, february: 2,
  mar: 3, march: 3,
  apr: 4, april: 4,
  may: 5,
  jun: 6, june: 6,
  jul: 7, july: 7,
  aug: 8, august: 8,
  sep: 9, sept: 9, september: 9,
  oct: 10, october: 10,
  nov: 11, november: 11,
  dec: 12, december: 12,
};

/**
 * Normalize a fuzzy month value (number, name, abbreviation, or messy token like
 * "AJan" / "sept") to a 1–12 month number, or null if unrecognized.
 *
 * Tolerates a leading stray letter from filename glitches (e.g. "AJan" → "Jan").
 */
export function normalizeMonth(value: string | number | null | undefined): number | null {
  if (value == null) return null;

  if (typeof value === "number") {
    return value >= 1 && value <= 12 ? value : null;
  }

  const raw = value.trim().toLowerCase();
  if (!raw) return null;

  // Pure numeric ("01", "9")
  if (/^\d{1,2}$/.test(raw)) {
    const n = parseInt(raw, 10);
    return n >= 1 && n <= 12 ? n : null;
  }

  // Direct lookup
  if (MONTH_LOOKUP[raw] != null) return MONTH_LOOKUP[raw];

  // Strip non-alpha then try again ("sept." → "sept")
  const alpha = raw.replace(/[^a-z]/g, "");
  if (MONTH_LOOKUP[alpha] != null) return MONTH_LOOKUP[alpha];

  // Find any known month token as a substring (handles "ajan", "xfeb", "mar2025")
  for (const [token, num] of Object.entries(MONTH_LOOKUP)) {
    if (token.length >= 3 && alpha.includes(token)) return num;
  }

  // Last resort: drop a single leading stray char ("ajan" → "jan")
  if (alpha.length > 3) {
    const trimmed = alpha.slice(1);
    if (MONTH_LOOKUP[trimmed] != null) return MONTH_LOOKUP[trimmed];
  }

  return null;
}

export function monthName(month: number | null | undefined): string | null {
  if (month == null || month < 1 || month > 12) return null;
  return MONTH_NAMES[month - 1];
}

export function monthShort(month: number | null | undefined): string | null {
  const name = monthName(month);
  return name ? name.slice(0, 3) : null;
}

// ── Filename cleanup ────────────────────────────────────────────────────────--

/** Turn "Blue_cash_Jan_2025.pdf" → "Blue cash Jan 2025" (display only). */
export function cleanFilename(filename: string): string {
  return filename
    .replace(/\.pdf$/i, "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// ── Institution inference ──────────────────────────────────────────────────--

export const INSTITUTION_DISPLAY: Record<string, string> = {
  amex: "American Express",
  american_express: "American Express",
  chase: "Chase",
  morgan_stanley: "Morgan Stanley",
  etrade: "E*TRADE",
  discover: "Discover",
  bofa: "Bank of America",
  marcus: "Marcus",
  unknown: "Unknown",
};

// Underscores are word chars, so `\b` won't break on them. Match these tokens
// anywhere within the filename (case-insensitive); separators are treated loosely.
const INSTITUTION_FILENAME_HINTS: Array<[string, RegExp]> = [
  ["amex", /(amex|american[\s_-]?express|blue[\s_-]?cash|gold[\s_-]?card|platinum)/i],
  ["chase", /(chase|sapphire|freedom)/i],
  ["morgan_stanley", /(morgan[\s_-]?stanley|morgan|stanley)/i],
  ["etrade", /(e[\s_*-]?trade)/i],
  ["discover", /(discover)/i],
];

/** Canonical institution slug from metadata first, then filename hints. */
export function inferInstitution(doc: DocumentSummary): string {
  const fromMeta = doc.institution?.trim().toLowerCase();
  if (fromMeta && fromMeta !== "unknown") return fromMeta;

  // account_product like "American Express — Blue Cash"
  if (doc.account_product) {
    const lead = doc.account_product.split(/[—–\-|]/)[0]?.trim().toLowerCase();
    for (const [slug, label] of Object.entries(INSTITUTION_DISPLAY)) {
      if (lead && (lead === slug || lead === label.toLowerCase())) return slug;
    }
  }

  for (const [slug, re] of INSTITUTION_FILENAME_HINTS) {
    if (re.test(doc.filename)) return slug;
  }
  return "unknown";
}

export function institutionLabel(slug: string): string {
  return INSTITUTION_DISPLAY[slug] ?? cleanFilename(slug);
}

// ── Account inference ──────────────────────────────────────────────────────--

const ACCOUNT_FILENAME_HINTS: Array<[string, RegExp]> = [
  ["Blue Cash", /blue[\s_-]?cash/i],
  ["Gold", /gold/i],
  ["Platinum", /platinum/i],
  ["Sapphire", /sapphire/i],
  ["Freedom", /freedom/i],
  ["Checking", /checking/i],
  ["Savings", /savings/i],
  ["Investment Account", /(investment|brokerage|ira|roth|advisory)/i],
];

const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  credit_card: "Credit Card",
  checking: "Checking",
  savings: "Savings",
  ira: "Investment Account",
  roth_ira: "Investment Account",
  advisory: "Investment Account",
  individual_brokerage: "Investment Account",
  "401k": "Investment Account",
};

/** Human-readable account/card label from account_product, account_type, or filename. */
export function inferAccount(doc: DocumentSummary): string {
  // account_product trailing segment: "American Express — Blue Cash" → "Blue Cash"
  if (doc.account_product) {
    const parts = doc.account_product.split(/[—–|]/).map((p) => p.trim());
    const tail = parts.length > 1 ? parts[parts.length - 1] : "";
    if (tail) return tail;
  }

  for (const [label, re] of ACCOUNT_FILENAME_HINTS) {
    if (re.test(doc.filename)) return label;
  }

  if (doc.account_type && ACCOUNT_TYPE_LABELS[doc.account_type]) {
    return ACCOUNT_TYPE_LABELS[doc.account_type];
  }

  return "Unknown Account";
}

// ── Year / month inference ─────────────────────────────────────────────────--

/** Year for display/grouping.
 *
 * Prefers an explicit 4-digit year in the filename (what the user named the file),
 * then explicit upload metadata, then the parsed statement period. The parsed
 * period can be misaligned (e.g. a statement covering a billing cycle that ends in
 * the following month), so the filename token wins when present.
 */
export function inferYear(doc: DocumentSummary): number | null {
  const fromName = doc.filename.match(/(?:19|20)\d{2}/);
  if (fromName) return Number(fromName[0]);
  if (doc.statement_year) return doc.statement_year;
  if (doc.period_end) {
    const y = Number(doc.period_end.slice(0, 4));
    if (y) return y;
  }
  return null;
}

/** Month (1–12) for display/grouping. Filename token first, then metadata, then period. */
export function inferMonth(doc: DocumentSummary): number | null {
  // Scan filename tokens for a month name/abbreviation (tolerates "AJan", "sept").
  const tokens = doc.filename.replace(/\.pdf$/i, "").split(/[_\-\s.]+/);
  for (const tok of tokens) {
    const m = normalizeMonth(tok);
    if (m) return m;
  }
  if (doc.statement_month) return doc.statement_month;
  if (doc.period_end) {
    const mm = Number(doc.period_end.slice(5, 7));
    if (mm >= 1 && mm <= 12) return mm;
  }
  return null;
}

/** Friendly "Jan 2025" / "2025" / "—" label for a document row. */
export function periodLabel(doc: DocumentSummary): string {
  const y = inferYear(doc);
  const m = inferMonth(doc);
  if (y && m) return `${monthShort(m)} ${y}`;
  if (y) return String(y);
  return "—";
}

// ── Counts (derived from the list — single source of truth) ──────────────────--

export function computeStats(docs: DocumentSummary[]): DocumentStats {
  const stats: DocumentStats = { total: docs.length, parsed: 0, processing: 0, uploaded: 0, failed: 0 };
  for (const doc of docs) {
    stats[normalizeStatus(doc.status)] += 1;
  }
  return stats;
}

/** True when at least one document is genuinely in the processing state. */
export function hasProcessing(docs: DocumentSummary[]): boolean {
  return docs.some((d) => normalizeStatus(d.status) === "processing");
}

// ── Grouping: Institution → Account → Year ───────────────────────────────────--

export interface YearGroup {
  year: number | null;
  yearLabel: string;
  docs: DocumentSummary[];
}

export interface AccountGroup {
  account: string;
  count: number;
  years: YearGroup[];
}

export interface InstitutionGroup {
  slug: string;
  label: string;
  count: number;
  accounts: AccountGroup[];
}

function compareMonthDesc(a: DocumentSummary, b: DocumentSummary): number {
  const ma = inferMonth(a) ?? 0;
  const mb = inferMonth(b) ?? 0;
  if (ma !== mb) return mb - ma;
  return a.filename.localeCompare(b.filename);
}

/**
 * Build the nested accordion model, sorted:
 *   institution (label asc) → account (label asc) → year (desc) → month (desc) → filename.
 */
export function groupDocuments(docs: DocumentSummary[]): InstitutionGroup[] {
  const byInst = new Map<string, Map<string, Map<number | null, DocumentSummary[]>>>();

  for (const doc of docs) {
    const inst = inferInstitution(doc);
    const acct = inferAccount(doc);
    const year = inferYear(doc);

    if (!byInst.has(inst)) byInst.set(inst, new Map());
    const accounts = byInst.get(inst)!;
    if (!accounts.has(acct)) accounts.set(acct, new Map());
    const years = accounts.get(acct)!;
    if (!years.has(year)) years.set(year, []);
    years.get(year)!.push(doc);
  }

  const result: InstitutionGroup[] = [];

  for (const [slug, accounts] of byInst) {
    const accountGroups: AccountGroup[] = [];
    let instCount = 0;

    for (const [account, years] of accounts) {
      const yearGroups: YearGroup[] = [];
      let acctCount = 0;

      for (const [year, yearDocs] of years) {
        yearDocs.sort(compareMonthDesc);
        acctCount += yearDocs.length;
        yearGroups.push({ year, yearLabel: year == null ? "Unknown Year" : String(year), docs: yearDocs });
      }

      // Year descending; nulls (Unknown Year) last.
      yearGroups.sort((a, b) => {
        if (a.year == null) return 1;
        if (b.year == null) return -1;
        return b.year - a.year;
      });

      instCount += acctCount;
      accountGroups.push({ account, count: acctCount, years: yearGroups });
    }

    // Account label ascending; "Unknown Account" last.
    accountGroups.sort((a, b) => {
      if (a.account === "Unknown Account") return 1;
      if (b.account === "Unknown Account") return -1;
      return a.account.localeCompare(b.account);
    });

    result.push({ slug, label: institutionLabel(slug), count: instCount, accounts: accountGroups });
  }

  // Institution label ascending; "Unknown" last.
  result.sort((a, b) => {
    if (a.slug === "unknown") return 1;
    if (b.slug === "unknown") return -1;
    return a.label.localeCompare(b.label);
  });

  return result;
}

// ── Filtering ────────────────────────────────────────────────────────────────

export interface DocumentFilterState {
  search: string;
  institution: string; // "all" or slug
  year: string;        // "all" or year string
  status: string;      // "all" or status
}

export const EMPTY_FILTERS: DocumentFilterState = {
  search: "",
  institution: "all",
  year: "all",
  status: "all",
};

export function filterDocuments(docs: DocumentSummary[], f: DocumentFilterState): DocumentSummary[] {
  const q = f.search.trim().toLowerCase();
  return docs.filter((doc) => {
    if (f.status !== "all" && normalizeStatus(doc.status) !== f.status) return false;
    if (f.institution !== "all" && inferInstitution(doc) !== f.institution) return false;
    if (f.year !== "all" && String(inferYear(doc) ?? "") !== f.year) return false;
    if (q) {
      const haystack = [
        doc.filename,
        institutionLabel(inferInstitution(doc)),
        inferAccount(doc),
        doc.account_product ?? "",
      ]
        .join(" ")
        .toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    return true;
  });
}

/** Distinct institution options (slug + label) present in the document set. */
export function institutionOptions(docs: DocumentSummary[]): Array<{ value: string; label: string }> {
  const slugs = new Set(docs.map(inferInstitution));
  return [...slugs]
    .map((slug) => ({ value: slug, label: institutionLabel(slug) }))
    .sort((a, b) => {
      if (a.value === "unknown") return 1;
      if (b.value === "unknown") return -1;
      return a.label.localeCompare(b.label);
    });
}

/** Distinct years present, descending. */
export function yearOptions(docs: DocumentSummary[]): number[] {
  const years = new Set<number>();
  for (const doc of docs) {
    const y = inferYear(doc);
    if (y) years.add(y);
  }
  return [...years].sort((a, b) => b - a);
}
