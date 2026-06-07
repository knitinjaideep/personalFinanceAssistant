"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { documentsApi } from "./api";
import type { DocumentSummary } from "@/types/index";

const FETCH_TIMEOUT_MS = 12_000;
const POLL_INTERVAL_MS = 4_000;
const MAX_POLL_DURATION_MS = 5 * 60_000;

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("Request timed out")), ms);
    promise.then(
      (v) => { clearTimeout(timer); resolve(v); },
      (e) => { clearTimeout(timer); reject(e); }
    );
  });
}

function hasProcessing(docs: DocumentSummary[]): boolean {
  return docs.some((d) => d.status === "processing");
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
      const msg = e instanceof Error ? e.message : "Failed to load documents";
      const isNetworkErr = msg.toLowerCase().includes("fetch") || msg.toLowerCase().includes("network") || msg.toLowerCase().includes("failed to fetch");
      setError(
        isNetworkErr
          ? "Coral backend is not reachable. Make sure FastAPI is running on http://localhost:8000."
          : msg
      );
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    fetchDocs();
    return () => {
      mounted.current = false;
      stopPolling();
    };
  }, [fetchDocs, stopPolling]);

  useEffect(() => {
    const processing = hasProcessing(docs);

    if (processing && !intervalRef.current) {
      pollStartRef.current = Date.now();
      setPolling(true);
      intervalRef.current = setInterval(() => {
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
