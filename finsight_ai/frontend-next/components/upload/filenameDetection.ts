/**
 * Filename auto-detection for bulk upload.
 *
 * Supports two patterns:
 *   Normalized:  {account_slug}_{year}_{month_number}_{month_name}.pdf
 *                e.g. blue_cash_2024_01_january.pdf
 *   Legacy:      {account_label_word}_{month_name}.pdf  (no year)
 *                e.g. Blue_Cash_January.pdf  /  Gold_February.pdf
 */

import type { InstitutionOption } from "@/features/upload/api";

export interface DetectedMetadata {
  institution_slug: string;
  account_slug: string;
  year: number | null;
  month: number | null;
  confidence: "high" | "low" | "none";
  warning?: string;
}

const MONTH_NAMES: Record<string, number> = {
  january: 1, february: 2, march: 3, april: 4,
  may: 5, june: 6, july: 7, august: 8,
  september: 9, october: 10, november: 11, december: 12,
  jan: 1, feb: 2, mar: 3, apr: 4,
  jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12,
};

function parseMonthName(s: string): number | null {
  return MONTH_NAMES[s.toLowerCase()] ?? null;
}

export function detectFromFilename(
  filename: string,
  institutions: InstitutionOption[],
): DetectedMetadata | null {
  const base = filename.replace(/\.pdf$/i, "").toLowerCase();
  const parts = base.split(/[_\-\s]+/);

  const allAccounts: Array<{ institution_slug: string; account_slug: string }> = [];
  for (const inst of institutions) {
    for (const acct of inst.accounts) {
      allAccounts.push({ institution_slug: inst.institution_slug, account_slug: acct.account_slug });
    }
  }

  // Pattern 1: normalized {account_slug}_{year}_{MM}_{month_name}.pdf
  for (const { institution_slug, account_slug } of allAccounts) {
    const slugParts = account_slug.split("_");
    const slugLen = slugParts.length;

    if (parts.length < slugLen + 3) continue;
    const candidateSlug = parts.slice(0, slugLen).join("_");
    if (candidateSlug !== account_slug) continue;

    const tail = parts.slice(slugLen);
    const year = parseInt(tail[0], 10);
    const monthNum = parseInt(tail[1], 10);

    if (year >= 2020 && year <= 2030 && monthNum >= 1 && monthNum <= 12) {
      return { institution_slug, account_slug, year, month: monthNum, confidence: "high" };
    }
    const altMonthName = parseMonthName(tail[1] ?? "");
    if (year >= 2020 && year <= 2030 && altMonthName !== null) {
      return { institution_slug, account_slug, year, month: altMonthName, confidence: "high" };
    }
  }

  // Pattern 2: legacy {label_word(s)}_{month_name}.pdf (no year)
  const lastPart = parts[parts.length - 1];
  const possibleMonth = parseMonthName(lastPart);
  if (possibleMonth !== null && parts.length >= 2) {
    const labelTokens = parts.slice(0, -1).join("_");

    const exactSlugMatch = allAccounts.find((a) => a.account_slug === labelTokens);
    if (exactSlugMatch) {
      return {
        institution_slug: exactSlugMatch.institution_slug,
        account_slug: exactSlugMatch.account_slug,
        year: null,
        month: possibleMonth,
        confidence: "low",
        warning: "No year in filename — please set year manually.",
      };
    }

    let bestScore = 0;
    let bestMatch: { institution_slug: string; account_slug: string } | null = null;
    for (const { institution_slug, account_slug } of allAccounts) {
      const slugTokens = new Set(account_slug.split("_"));
      const prefixTokens = new Set(labelTokens.split("_"));
      const shared = [...slugTokens].filter((t) => prefixTokens.has(t)).length;
      const score = shared / Math.max(slugTokens.size, prefixTokens.size);
      if (score > bestScore && score >= 0.5) {
        bestScore = score;
        bestMatch = { institution_slug, account_slug };
      }
    }
    if (bestMatch) {
      return {
        institution_slug: bestMatch.institution_slug,
        account_slug: bestMatch.account_slug,
        year: null,
        month: possibleMonth,
        confidence: "low",
        warning: "No year in filename — please set year manually.",
      };
    }
  }

  // Pattern 3: year + month anywhere in filename
  for (let i = 0; i < parts.length - 1; i++) {
    const y = parseInt(parts[i], 10);
    if (y >= 2020 && y <= 2030) {
      const m = parseInt(parts[i + 1], 10);
      if (m >= 1 && m <= 12) {
        return {
          institution_slug: "",
          account_slug: "",
          year: y,
          month: m,
          confidence: "none",
          warning: "Could not detect institution — please select manually.",
        };
      }
      const mName = parseMonthName(parts[i + 1] ?? "");
      if (mName !== null) {
        return {
          institution_slug: "",
          account_slug: "",
          year: y,
          month: mName,
          confidence: "none",
          warning: "Could not detect institution — please select manually.",
        };
      }
    }
  }

  return null;
}

export interface RowWarning {
  type: "missing_year" | "missing_month" | "unsupported_account" | "not_pdf" | "duplicate";
  message: string;
}

export function getRowWarnings(
  filename: string,
  institution_slug: string,
  account_slug: string,
  year: number | null,
  month: number | null,
  institutions: InstitutionOption[],
  existingPaths: Set<string>,
): RowWarning[] {
  const warnings: RowWarning[] = [];

  if (!filename.toLowerCase().endsWith(".pdf")) {
    warnings.push({ type: "not_pdf", message: "Not a PDF file." });
  }
  if (!year) {
    warnings.push({ type: "missing_year", message: "Year not set." });
  }
  if (!month) {
    warnings.push({ type: "missing_month", message: "Month not set." });
  }
  if (!institution_slug || !account_slug) {
    warnings.push({ type: "unsupported_account", message: "Institution / account not selected." });
  } else {
    const inst = institutions.find((i) => i.institution_slug === institution_slug);
    const acct = inst?.accounts.find((a) => a.account_slug === account_slug);
    if (!acct) {
      warnings.push({ type: "unsupported_account", message: "Account not in catalog." });
    }
  }

  if (institution_slug && account_slug && year && month) {
    const key = `${institution_slug}/${account_slug}/${year}/${month}`;
    if (existingPaths.has(key)) {
      warnings.push({ type: "duplicate", message: "Duplicate in this batch." });
    }
  }

  return warnings;
}
