/**
 * useIngestionHealth — fetches the ingestion-health report and exposes a
 * document_id → issues map for per-row "incomplete" badges.
 *
 * Has its own fetch timeout so it can never hang the page, and a `refetch` the
 * page calls after a reprocess completes.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { documentsApi } from "../api/documents";
import type { DocumentIssue, IngestionHealth } from "../types";

const FETCH_TIMEOUT_MS = 15_000;

function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("Request timed out")), ms);
    p.then(
      (v) => { clearTimeout(t); resolve(v); },
      (e) => { clearTimeout(t); reject(e); }
    );
  });
}

export interface UseIngestionHealthResult {
  health: IngestionHealth | null;
  issuesByDoc: Record<string, DocumentIssue>;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export function useIngestionHealth(): UseIngestionHealthResult {
  const [health, setHealth] = useState<IngestionHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);

  const refetch = useCallback(async () => {
    try {
      const next = await withTimeout(documentsApi.ingestionHealth(), FETCH_TIMEOUT_MS);
      if (!mounted.current) return;
      setHealth(next);
      setError(null);
    } catch (e) {
      if (!mounted.current) return;
      setError(e instanceof Error ? e.message : "Failed to load ingestion health");
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    refetch();
    return () => { mounted.current = false; };
  }, [refetch]);

  const issuesByDoc: Record<string, DocumentIssue> = {};
  for (const d of health?.documents ?? []) issuesByDoc[d.document_id] = d;

  return { health, issuesByDoc, loading, error, refetch };
}
