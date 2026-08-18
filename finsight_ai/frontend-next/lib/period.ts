/**
 * Global Period Filter — pure date-range resolution (PR 05).
 *
 * This is the single place that decides what "Current Month" / "1M" / "3M" /
 * "6M" / "YTD" / "1Y" / "Custom" actually mean as concrete calendar dates.
 * Kept as plain, dependency-free functions (no React, no fetch) so it is
 * easy to reason about and exercise directly — see the note in the PR 05
 * work order about there being no frontend test runner in this repo yet;
 * this module is deliberately small and pure specifically so its logic can
 * be read and manually verified in one pass, and gains a test runner "for
 * free" as soon as one is introduced (no rewrite required).
 *
 * Timezone/date-boundary policy: every date is manipulated as plain
 * (year, month, day) integers and formatted directly to "YYYY-MM-DD" — never
 * round-tripped through `Date#toISOString()` (which converts to UTC and can
 * silently shift the calendar date by one day for negative-offset
 * timezones). "Today" is read from the browser's local wall-clock date
 * (`getFullYear()`/`getMonth()`/`getDate()`, not the UTC variants) because a
 * personal-finance app should reflect the user's own local "today", not
 * UTC's. `Date` objects are only ever used for their local day-of-month
 * arithmetic (e.g. "how many days are in April 2026"), never serialized.
 */

export type PeriodMode = "current_month" | "1m" | "3m" | "6m" | "ytd" | "1y" | "custom";

export const PERIOD_MODES: PeriodMode[] = ["current_month", "1m", "3m", "6m", "ytd", "1y", "custom"];

export const PERIOD_MODE_LABELS: Record<PeriodMode, string> = {
  current_month: "Month",
  "1m": "1M",
  "3m": "3M",
  "6m": "6M",
  ytd: "YTD",
  "1y": "1Y",
  custom: "Custom",
};

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

export interface PeriodSelection {
  mode: PeriodMode;
  /** Selected calendar month (1-12) — only meaningful/used for "current_month". */
  month?: number;
  /** Selected calendar year — only meaningful/used for "current_month". */
  year?: number;
  /** Explicit "YYYY-MM-DD" bounds — required (and only used) for "custom". */
  customStart?: string;
  customEnd?: string;
}

export interface ResolvedPeriod extends PeriodSelection {
  startDate: string; // "YYYY-MM-DD", inclusive
  endDate: string;   // "YYYY-MM-DD", inclusive
  label: string;
  /** True when navigating forward (next month) would move past the current real-world month. */
  isAtLatestMonth: boolean;
}

interface YMD {
  y: number;
  m: number; // 1-12
  d: number;
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function formatYMD({ y, m, d }: YMD): string {
  return `${y}-${pad2(m)}-${pad2(d)}`;
}

/** Days in calendar month `m` (1-12) of year `y`. Local-time day-count math
 * only — never used to produce a serialized date, so it is timezone-safe. */
function daysInMonth(y: number, m: number): number {
  return new Date(y, m, 0).getDate();
}

/** Today's local wall-clock date as plain integers (not UTC). */
export function todayYMD(): YMD {
  const now = new Date();
  return { y: now.getFullYear(), m: now.getMonth() + 1, d: now.getDate() };
}

/** Calendar-month subtraction with day clamping (e.g. Mar 31 - 1 month =
 * Feb 28/29, not an overflow into March). Mirrors how humans read "3 months
 * ago" — a trailing rolling window, not a fixed 90-day offset. */
function subtractMonths({ y, m, d }: YMD, months: number): YMD {
  const totalMonths = y * 12 + (m - 1) - months;
  const newY = Math.floor(totalMonths / 12);
  const newM = (totalMonths % 12) + 1;
  const clampedDay = Math.min(d, daysInMonth(newY, newM));
  return { y: newY, m: newM, d: clampedDay };
}

function monthLabel(y: number, m: number): string {
  return `${MONTH_NAMES[m - 1]} ${y}`;
}

/**
 * Resolve a PeriodSelection into concrete inclusive start/end dates.
 *
 * `referenceToday` is injectable for deterministic reasoning/manual testing
 * (defaults to the real local today).
 */
export function resolvePeriod(
  selection: PeriodSelection,
  referenceToday: YMD = todayYMD(),
): ResolvedPeriod {
  const { mode } = selection;

  switch (mode) {
    case "current_month": {
      const year = selection.year ?? referenceToday.y;
      const month = selection.month ?? referenceToday.m;
      const isCurrentRealMonth = year === referenceToday.y && month === referenceToday.m;
      const start: YMD = { y: year, m: month, d: 1 };
      // Never show days in the future: the real current month is clipped to
      // today; any other (past) month runs to its natural last day.
      const end: YMD = isCurrentRealMonth
        ? { ...referenceToday }
        : { y: year, m: month, d: daysInMonth(year, month) };
      const isAtLatestMonth = isCurrentRealMonth;
      return {
        ...selection,
        year,
        month,
        startDate: formatYMD(start),
        endDate: formatYMD(end),
        label: monthLabel(year, month),
        isAtLatestMonth,
      };
    }

    case "1m":
    case "3m":
    case "6m":
    case "1y": {
      const monthsBack = mode === "1m" ? 1 : mode === "3m" ? 3 : mode === "6m" ? 6 : 12;
      const start = subtractMonths(referenceToday, monthsBack);
      return {
        ...selection,
        startDate: formatYMD(start),
        endDate: formatYMD(referenceToday),
        label: PERIOD_MODE_LABELS[mode],
        isAtLatestMonth: true,
      };
    }

    case "ytd": {
      const start: YMD = { y: referenceToday.y, m: 1, d: 1 };
      return {
        ...selection,
        startDate: formatYMD(start),
        endDate: formatYMD(referenceToday),
        label: "Year to Date",
        isAtLatestMonth: true,
      };
    }

    case "custom": {
      // Fall back to today for a not-yet-fully-specified custom range so
      // callers always get a valid, orderable range rather than undefined
      // behavior while the user is mid-pick.
      const startDate = selection.customStart ?? formatYMD(referenceToday);
      let endDate = selection.customEnd ?? formatYMD(referenceToday);
      if (endDate < startDate) endDate = startDate; // never emit an inverted range
      return {
        ...selection,
        customStart: startDate,
        customEnd: endDate,
        startDate,
        endDate,
        label: startDate === endDate ? startDate : `${startDate} – ${endDate}`,
        isAtLatestMonth: true,
      };
    }

    default: {
      // Exhaustiveness guard — should be unreachable given PeriodMode.
      const _exhaustive: never = mode;
      throw new Error(`Unknown period mode: ${_exhaustive}`);
    }
  }
}

/** Move a "current_month" selection to the previous calendar month. No-op
 * (returns the input unchanged) for non-"current_month" modes. */
export function goToPreviousMonth(
  selection: PeriodSelection,
  referenceToday: YMD = todayYMD(),
): PeriodSelection {
  if (selection.mode !== "current_month") return selection;
  const year = selection.year ?? referenceToday.y;
  const month = selection.month ?? referenceToday.m;
  const prev = subtractMonths({ y: year, m: month, d: 1 }, 1);
  return { ...selection, year: prev.y, month: prev.m };
}

/** Move a "current_month" selection to the next calendar month, clamped so
 * it never moves past the real current month. No-op for other modes. */
export function goToNextMonth(
  selection: PeriodSelection,
  referenceToday: YMD = todayYMD(),
): PeriodSelection {
  if (selection.mode !== "current_month") return selection;
  const year = selection.year ?? referenceToday.y;
  const month = selection.month ?? referenceToday.m;
  if (year === referenceToday.y && month === referenceToday.m) return selection; // already latest
  const totalMonths = year * 12 + (month - 1) + 1;
  const nextY = Math.floor(totalMonths / 12);
  const nextM = (totalMonths % 12) + 1;
  // Clamp forward navigation so it can never overshoot the real current month.
  if (nextY > referenceToday.y || (nextY === referenceToday.y && nextM > referenceToday.m)) {
    return { ...selection, year: referenceToday.y, month: referenceToday.m };
  }
  return { ...selection, year: nextY, month: nextM };
}

// ── URL <-> PeriodSelection ─────────────────────────────────────────────────
//
// Query param contract: `?period=<mode>` always; `&month=<1-12>&year=<yyyy>`
// only for "current_month" (so a bookmarked specific past month survives a
// reload); `&start=YYYY-MM-DD&end=YYYY-MM-DD` only for "custom". Rolling
// modes (1M/3M/6M/YTD/1Y) intentionally do NOT persist explicit dates in the
// URL — reopening a "3m" link always means "3 months back from whenever you
// open it", which is the expected dynamic behavior for a rolling window.

const DEFAULT_SELECTION: PeriodSelection = { mode: "6m" };

export function periodSelectionFromSearchParams(params: URLSearchParams): PeriodSelection {
  const modeParam = params.get("period");
  const mode: PeriodMode = (PERIOD_MODES as string[]).includes(modeParam ?? "")
    ? (modeParam as PeriodMode)
    : DEFAULT_SELECTION.mode;

  if (mode === "current_month") {
    const month = Number(params.get("month"));
    const year = Number(params.get("year"));
    return {
      mode,
      month: Number.isInteger(month) && month >= 1 && month <= 12 ? month : undefined,
      year: Number.isInteger(year) && year >= 2000 && year <= 2100 ? year : undefined,
    };
  }

  if (mode === "custom") {
    const start = params.get("start");
    const end = params.get("end");
    return {
      mode,
      customStart: start ?? undefined,
      customEnd: end ?? undefined,
    };
  }

  return { mode };
}

export function periodSelectionToSearchParams(selection: PeriodSelection): Record<string, string> {
  const out: Record<string, string> = { period: selection.mode };
  if (selection.mode === "current_month") {
    if (selection.month) out.month = String(selection.month);
    if (selection.year) out.year = String(selection.year);
  }
  if (selection.mode === "custom") {
    if (selection.customStart) out.start = selection.customStart;
    if (selection.customEnd) out.end = selection.customEnd;
  }
  return out;
}

export const DEFAULT_PERIOD_SELECTION: PeriodSelection = DEFAULT_SELECTION;
