/**
 * useDocuments — single source of truth for the Documents dashboard.
 *
 * Owns: fetching the document list, a fetch timeout guard (so the spinner can
 * never hang forever), and adaptive polling that only runs while documents are
 * genuinely processing. The interval is cleaned up on unmount and stops once
 * nothing is processing or a hard time cap is reached.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { documentsApi } from "../api/documents";
import type { DocumentSummary } from "../types";
import { hasProcessing } from "../utils/documentUtils";

const FETCH_TIMEOUT_MS = 12_000;     // give up on a single fetch after this
const POLL_INTERVAL_MS = 4_000;      // while something is processing
const MAX_POLL_DURATION_MS = 5 * 60_000; // stop polling after 5 min no matter what

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("Request timed out")), ms);
    promise.then(
      (v) => {
        clearTimeout(timer);
        resolve(v);
      },
      (e) => {
        clearTimeout(timer);
        reject(e);
      }
    );
  });
}

export interface UseDocumentsResult {
  docs: DocumentSummary[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  polling: boolean;
}

export function useDocuments(): UseDocumentsResult {
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);

  const mounted = useRef(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollStartRef = useRef<number>(0);

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    if (mounted.current) setPolling(false);
  }, []);

  const fetchDocs = useCallback(async () => {
    try {
      const next = await withTimeout(documentsApi.list(200), FETCH_TIMEOUT_MS);
      if (!mounted.current) return;
      setDocs(next);
      setError(null);
    } catch (e) {
      if (!mounted.current) return;
      setError(e instanceof Error ? e.message : "Failed to load documents");
    } finally {
      // Critical: always clear loading so the spinner never hangs forever.
      if (mounted.current) setLoading(false);
    }
  }, []);

  // Initial load.
  useEffect(() => {
    mounted.current = true;
    fetchDocs();
    return () => {
      mounted.current = false;
      stopPolling();
    };
  }, [fetchDocs, stopPolling]);

  // Adaptive polling: start when something is processing, stop when nothing is.
  useEffect(() => {
    const processing = hasProcessing(docs);

    if (processing && !intervalRef.current) {
      pollStartRef.current = Date.now();
      setPolling(true);
      intervalRef.current = setInterval(() => {
        // Hard safety cap: never poll beyond the max duration.
        if (Date.now() - pollStartRef.current > MAX_POLL_DURATION_MS) {
          stopPolling();
          return;
        }
        fetchDocs();
      }, POLL_INTERVAL_MS);
    } else if (!processing && intervalRef.current) {
      stopPolling();
    }
  }, [docs, fetchDocs, stopPolling]);

  return { docs, loading, error, refetch: fetchDocs, polling };
}
