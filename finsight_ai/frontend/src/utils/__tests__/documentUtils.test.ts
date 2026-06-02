import { describe, it, expect } from "vitest";
import type { DocumentSummary } from "../../types";
import {
  normalizeStatus,
  normalizeMonth,
  monthName,
  inferInstitution,
  inferAccount,
  inferYear,
  inferMonth,
  periodLabel,
  computeStats,
  hasProcessing,
  groupDocuments,
  filterDocuments,
  EMPTY_FILTERS,
} from "../documentUtils";

function doc(partial: Partial<DocumentSummary>): DocumentSummary {
  return {
    id: Math.random().toString(36).slice(2),
    filename: "file.pdf",
    institution: "unknown",
    status: "parsed",
    page_count: 1,
    statement_count: 1,
    upload_time: null,
    error: null,
    ...partial,
  };
}

// ── status normalization ───────────────────────────────────────────────────--

describe("normalizeStatus", () => {
  it("maps parsed synonyms", () => {
    for (const v of ["parsed", "PARSED", "completed", "processed", "success", "Done"]) {
      expect(normalizeStatus(v)).toBe("parsed");
    }
  });
  it("maps processing synonyms", () => {
    for (const v of ["processing", "PROCESSING", "in_progress", "running"]) {
      expect(normalizeStatus(v)).toBe("processing");
    }
  });
  it("maps uploaded/pending", () => {
    for (const v of ["uploaded", "pending", "queued"]) {
      expect(normalizeStatus(v)).toBe("uploaded");
    }
  });
  it("maps failed/error", () => {
    expect(normalizeStatus("failed")).toBe("failed");
    expect(normalizeStatus("error")).toBe("failed");
  });
  it("defaults unknown/empty to uploaded", () => {
    expect(normalizeStatus(null)).toBe("uploaded");
    expect(normalizeStatus(undefined)).toBe("uploaded");
    expect(normalizeStatus("weird")).toBe("uploaded");
  });
});

// ── month inference / normalization ─────────────────────────────────────────--

describe("normalizeMonth", () => {
  it("handles names, abbreviations, and casing", () => {
    expect(normalizeMonth("January")).toBe(1);
    expect(normalizeMonth("jan")).toBe(1);
    expect(normalizeMonth("SEPT")).toBe(9);
    expect(normalizeMonth("sept")).toBe(9);
    expect(monthName(normalizeMonth("sept"))).toBe("September");
  });
  it("handles numbers", () => {
    expect(normalizeMonth(3)).toBe(3);
    expect(normalizeMonth("09")).toBe(9);
    expect(normalizeMonth(13)).toBeNull();
  });
  it("recovers from a stray leading char (AJan → Jan)", () => {
    expect(normalizeMonth("AJan")).toBe(1);
    expect(normalizeMonth("xfeb")).toBe(2);
  });
  it("returns null for garbage", () => {
    expect(normalizeMonth("zzz")).toBeNull();
    expect(normalizeMonth("")).toBeNull();
  });
});

describe("inferMonth / inferYear from filename", () => {
  it("parses Blue_cash_Jan_2025.pdf", () => {
    const d = doc({ filename: "Blue_cash_Jan_2025.pdf" });
    expect(inferMonth(d)).toBe(1);
    expect(inferYear(d)).toBe(2025);
    expect(periodLabel(d)).toBe("Jan 2025");
  });
  it("parses Blue_cash_AJan_2025.pdf (glitch) as Jan 2025", () => {
    const d = doc({ filename: "Blue_cash_AJan_2025.pdf" });
    expect(inferMonth(d)).toBe(1);
    expect(periodLabel(d)).toBe("Jan 2025");
  });
  it("parses Blue_cash_sept_2025.pdf as Sep 2025", () => {
    const d = doc({ filename: "Blue_cash_sept_2025.pdf" });
    expect(inferMonth(d)).toBe(9);
    expect(periodLabel(d)).toBe("Sep 2025");
  });
  it("prefers metadata over filename", () => {
    const d = doc({ filename: "weird.pdf", statement_year: 2026, statement_month: 4 });
    expect(inferYear(d)).toBe(2026);
    expect(inferMonth(d)).toBe(4);
  });
  it("derives year/month from period_end", () => {
    const d = doc({ filename: "x.pdf", period_end: "2025-07-31" });
    expect(inferYear(d)).toBe(2025);
    expect(inferMonth(d)).toBe(7);
  });
  it("filename token wins over misaligned parsed period", () => {
    // Statement period bled into the next month; the filename is what the user named it.
    const d = doc({ filename: "Blue_cash_Nov_2025.pdf", statement_year: 2026, statement_month: 5, period_end: "2026-05-02" });
    expect(inferYear(d)).toBe(2025);
    expect(inferMonth(d)).toBe(11);
    expect(periodLabel(d)).toBe("Nov 2025");
  });
});

// ── institution / account inference ─────────────────────────────────────────--

describe("inferInstitution", () => {
  it("uses metadata institution when present", () => {
    expect(inferInstitution(doc({ institution: "chase" }))).toBe("chase");
  });
  it("falls back to filename hints", () => {
    expect(inferInstitution(doc({ institution: "unknown", filename: "Blue_cash_Jan_2025.pdf" }))).toBe("amex");
    expect(inferInstitution(doc({ institution: "unknown", filename: "Sapphire_2025.pdf" }))).toBe("chase");
  });
  it("reads from account_product", () => {
    expect(inferInstitution(doc({ institution: "unknown", account_product: "American Express — Blue Cash" }))).toBe("amex");
  });
  it("defaults to unknown", () => {
    expect(inferInstitution(doc({ institution: "unknown", filename: "mystery.pdf" }))).toBe("unknown");
  });
});

describe("inferAccount", () => {
  it("reads trailing segment of account_product", () => {
    expect(inferAccount(doc({ account_product: "American Express — Blue Cash" }))).toBe("Blue Cash");
  });
  it("falls back to filename hints", () => {
    expect(inferAccount(doc({ filename: "Blue_cash_Jan_2025.pdf" }))).toBe("Blue Cash");
    expect(inferAccount(doc({ filename: "checking_2025.pdf" }))).toBe("Checking");
  });
  it("uses account_type label", () => {
    expect(inferAccount(doc({ filename: "x.pdf", account_type: "credit_card" }))).toBe("Credit Card");
    expect(inferAccount(doc({ filename: "x.pdf", account_type: "roth_ira" }))).toBe("Investment Account");
  });
  it("defaults to Unknown Account", () => {
    expect(inferAccount(doc({ filename: "mystery.pdf" }))).toBe("Unknown Account");
  });
});

// ── counts aggregation ───────────────────────────────────────────────────────

describe("computeStats", () => {
  it("derives counts from the list with normalization", () => {
    const docs = [
      doc({ status: "parsed" }),
      doc({ status: "PARSED" as DocumentSummary["status"] }),
      doc({ status: "completed" as DocumentSummary["status"] }),
      doc({ status: "processing" }),
      doc({ status: "uploaded" }),
      doc({ status: "failed" }),
    ];
    const stats = computeStats(docs);
    expect(stats.total).toBe(6);
    expect(stats.parsed).toBe(3);
    expect(stats.processing).toBe(1);
    expect(stats.uploaded).toBe(1);
    expect(stats.failed).toBe(1);
  });

  it("processing is 0 when nothing is processing", () => {
    const docs = [doc({ status: "parsed" }), doc({ status: "uploaded" }), doc({ status: "failed" })];
    expect(computeStats(docs).processing).toBe(0);
    expect(hasProcessing(docs)).toBe(false);
  });

  it("hasProcessing true only with a real processing doc", () => {
    expect(hasProcessing([doc({ status: "processing" }), doc({ status: "parsed" })])).toBe(true);
  });
});

// ── grouping ──────────────────────────────────────────────────────────────────

describe("groupDocuments", () => {
  const docs = [
    doc({ institution: "amex", account_product: "American Express — Blue Cash", filename: "Blue_cash_Jan_2025.pdf", statement_year: 2025, statement_month: 1 }),
    doc({ institution: "amex", account_product: "American Express — Blue Cash", filename: "Blue_cash_Feb_2025.pdf", statement_year: 2025, statement_month: 2 }),
    doc({ institution: "amex", account_product: "American Express — Blue Cash", filename: "Blue_cash_Feb_2026.pdf", statement_year: 2026, statement_month: 2 }),
    doc({ institution: "amex", account_product: "American Express — Gold", filename: "Gold_Mar_2026.pdf", statement_year: 2026, statement_month: 3 }),
    doc({ institution: "chase", account_type: "checking", filename: "Checking_Jan_2026.pdf", statement_year: 2026, statement_month: 1 }),
  ];

  it("nests Institution → Account → Year", () => {
    const groups = groupDocuments(docs);
    // Chase (C) sorts before American Express? No — alphabetical: "American Express" < "Chase"
    expect(groups.map((g) => g.label)).toEqual(["American Express", "Chase"]);

    const amex = groups[0];
    expect(amex.count).toBe(4);
    expect(amex.accounts.map((a) => a.account)).toEqual(["Blue Cash", "Gold"]);

    const blueCash = amex.accounts[0];
    // years descending
    expect(blueCash.years.map((y) => y.year)).toEqual([2026, 2025]);
    // 2025 has Jan + Feb, month descending → Feb first
    const y2025 = blueCash.years.find((y) => y.year === 2025)!;
    expect(y2025.docs.map((d) => inferMonth(d))).toEqual([2, 1]);
  });

  it("sorts Unknown institution/account/year last", () => {
    const withUnknown = [
      ...docs,
      doc({ institution: "unknown", filename: "mystery.pdf" }),
    ];
    const groups = groupDocuments(withUnknown);
    expect(groups[groups.length - 1].slug).toBe("unknown");
  });
});

// ── filtering ────────────────────────────────────────────────────────────────

describe("filterDocuments", () => {
  const docs = [
    doc({ institution: "amex", filename: "Blue_cash_Jan_2025.pdf", status: "parsed", statement_year: 2025 }),
    doc({ institution: "chase", filename: "Checking_Jan_2026.pdf", status: "processing", statement_year: 2026 }),
  ];

  it("returns all with empty filters", () => {
    expect(filterDocuments(docs, EMPTY_FILTERS)).toHaveLength(2);
  });
  it("filters by status", () => {
    expect(filterDocuments(docs, { ...EMPTY_FILTERS, status: "processing" })).toHaveLength(1);
  });
  it("filters by institution", () => {
    expect(filterDocuments(docs, { ...EMPTY_FILTERS, institution: "amex" })).toHaveLength(1);
  });
  it("filters by year", () => {
    expect(filterDocuments(docs, { ...EMPTY_FILTERS, year: "2026" })).toHaveLength(1);
  });
  it("searches filename and institution label", () => {
    expect(filterDocuments(docs, { ...EMPTY_FILTERS, search: "blue" })).toHaveLength(1);
    expect(filterDocuments(docs, { ...EMPTY_FILTERS, search: "chase" })).toHaveLength(1);
  });
});
