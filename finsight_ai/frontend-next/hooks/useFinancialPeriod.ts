"use client";

/**
 * Global Period Filter state (PR 05) — shared by Overview, Banking, and
 * Investments.
 *
 * Source of truth precedence:
 *   1. The current page's URL `?period=...` query params, if present
 *      (shareable/bookmarkable links always win).
 *   2. Otherwise, whatever was last selected on any page this session
 *      (Zustand `periodSelection`) — this is what makes the selection
 *      "survive page navigation" when a link to /banking or /investments
 *      doesn't itself carry period params (e.g. the top-nav links).
 *   3. Otherwise, 6M (see lib/period.ts DEFAULT_PERIOD_SELECTION).
 *
 * Every selection change updates both the store (cross-page memory) and the
 * current page's URL (shareability), per the PR 05 work order's preference
 * for URL/query state over local-only state.
 */

import { useCallback, useEffect, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAppStore } from "@/store/appStore";
import {
  type PeriodSelection,
  type ResolvedPeriod,
  goToNextMonth,
  goToPreviousMonth,
  periodSelectionFromSearchParams,
  periodSelectionToSearchParams,
  resolvePeriod,
} from "@/lib/period";

export interface UseFinancialPeriodResult {
  selection: PeriodSelection;
  resolved: ResolvedPeriod;
  setSelection: (next: PeriodSelection) => void;
  goToPreviousMonth: () => void;
  goToNextMonth: () => void;
}

export function useFinancialPeriod(): UseFinancialPeriodResult {
  const router = useRouter();
  const pathname = usePathname() ?? "/";
  const searchParams = useSearchParams();
  const storeSelection = useAppStore((s) => s.periodSelection);
  const setStoreSelection = useAppStore((s) => s.setPeriodSelection);

  const searchParamsKey = searchParams.toString();

  // The URL is read SYNCHRONOUSLY during render, not only inside the effect
  // below. Deriving it in an effect alone would mean the very first render
  // after a hard refresh / pasted link (e.g. `?period=3m`) still used the
  // store's default Current Month, firing one wasted backend request for the
  // wrong range and briefly painting the wrong period's numbers before the
  // effect corrected it.
  // Keyed on `searchParamsKey`, the stable string identity of `searchParams`
  // (the object itself is a fresh instance on every render).
  const urlSelection = useMemo(
    () => (searchParams.has("period") ? periodSelectionFromSearchParams(searchParams) : null),
    [searchParamsKey]
  );
  const selection = urlSelection ?? storeSelection;

  // Reconcile URL <-> store on mount and whenever the URL changes underneath
  // us (back/forward navigation, or landing on a page via a shared link).
  useEffect(() => {
    if (searchParams.has("period")) {
      const fromUrl = periodSelectionFromSearchParams(searchParams);
      setStoreSelection(fromUrl);
      return;
    }
    // This page's URL has no period params yet — stamp the store's current
    // selection into it so the URL always reflects the active filter.
    const params = new URLSearchParams(searchParamsKey);
    Object.entries(periodSelectionToSearchParams(storeSelection)).forEach(([k, v]) => {
      params.set(k, v);
    });
    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    // Deliberately keyed only on the URL (searchParamsKey), not on
    // storeSelection/router/pathname/setStoreSelection: this effect exists
    // to reconcile the URL from an external change (navigation), not to
    // re-run every time the store changes as a side effect of its own
    // `router.replace` call above (which would self-trigger a loop). This
    // repo does not have the `eslint-plugin-react-hooks` exhaustive-deps
    // rule configured (see eslint.config.mjs), so no suppression comment is
    // needed/possible here.
  }, [searchParamsKey]);

  const setSelection = useCallback(
    (next: PeriodSelection) => {
      setStoreSelection(next);
      const params = new URLSearchParams(searchParamsKey);
      ["month", "year", "start", "end"].forEach((k) => params.delete(k));
      Object.entries(periodSelectionToSearchParams(next)).forEach(([k, v]) => {
        params.set(k, v);
      });
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    },
    [pathname, router, searchParamsKey, setStoreSelection]
  );

  // Keyed on the selection's VALUES, not its object identity: `urlSelection`
  // is rebuilt whenever the query string changes, so an identity-keyed memo
  // would recompute (and hand callers a new `resolved` object, retriggering
  // their fetch effects) for unrelated query-param changes.
  const resolved = useMemo(
    () => resolvePeriod(selection),
    [selection.mode, selection.year, selection.month, selection.customStart, selection.customEnd]
  );

  const handlePrevMonth = useCallback(() => {
    setSelection(goToPreviousMonth(selection));
  }, [setSelection, selection]);

  const handleNextMonth = useCallback(() => {
    setSelection(goToNextMonth(selection));
  }, [setSelection, selection]);

  return {
    selection,
    resolved,
    setSelection,
    goToPreviousMonth: handlePrevMonth,
    goToNextMonth: handleNextMonth,
  };
}
