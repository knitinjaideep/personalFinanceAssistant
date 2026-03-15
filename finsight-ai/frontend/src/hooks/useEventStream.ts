/**
 * useEventStream — consumes a server-sent event stream for a given session.
 *
 * Two modes:
 * 1. SSE GET stream  — used for long-lived agent activity monitoring
 *    (connect to /api/v1/buckets/events/stream?session_id=X)
 * 2. POST stream     — used for chat queries that stream events inline
 *    (POST to /api/v1/chat/stream with ReadableStream response)
 *
 * The hook accumulates events in local state and calls onEvent for
 * each new event so callers can react in real time.
 */

import { useState, useCallback, useRef } from "react";
import type { ProcessingEvent } from "../types";

const BASE_URL = "/api/v1";

interface UseEventStreamOptions {
  onEvent?: (event: ProcessingEvent) => void;
  onDone?: () => void;
  onError?: (message: string) => void;
}

export function useEventStream(options: UseEventStreamOptions = {}) {
  const [events, setEvents] = useState<ProcessingEvent[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const esRef = useRef<EventSource | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const clearEvents = useCallback(() => setEvents([]), []);

  const _push = useCallback(
    (event: ProcessingEvent) => {
      setEvents((prev) => [...prev, event]);
      options.onEvent?.(event);
    },
    [options]
  );

  /**
   * Open a GET SSE stream for a session (used for long-lived ingestion monitoring).
   */
  const connectToSession = useCallback(
    (sessionId: string) => {
      // Close any existing connection
      esRef.current?.close();

      const url = `${BASE_URL}/buckets/events/stream?session_id=${encodeURIComponent(sessionId)}`;
      const es = new EventSource(url);
      esRef.current = es;
      setIsStreaming(true);

      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data) as ProcessingEvent & { type?: string };
          if (data.type === "stream_done") {
            es.close();
            esRef.current = null;
            setIsStreaming(false);
            options.onDone?.();
            return;
          }
          _push(data);
        } catch {
          // ignore malformed frames
        }
      };

      es.onerror = () => {
        es.close();
        esRef.current = null;
        setIsStreaming(false);
        options.onError?.("Event stream disconnected.");
      };
    },
    [_push, options]
  );

  /**
   * POST a chat question and stream SSE events from the response body.
   * Returns the full structured response_complete payload when the stream ends.
   */
  const streamChatQuery = useCallback(
    async (
      payload: object
    ): Promise<{
      answer: string;
      sources: unknown[];
      structured_answer: unknown | null;
      answer_type: string;
      confidence: number | null;
      caveats: string[];
      pipeline_meta: Record<string, unknown> | null;
    } | null> => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setIsStreaming(true);
      setEvents([]);

      try {
        const response = await fetch(`${BASE_URL}/chat/stream`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
          },
          body: JSON.stringify(payload),
          signal: controller.signal,
        });

        if (!response.ok || !response.body) {
          throw new Error(`HTTP ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let finalResult: {
          answer: string;
          sources: unknown[];
          structured_answer: unknown | null;
          answer_type: string;
          confidence: number | null;
          caveats: string[];
          pipeline_meta: Record<string, unknown> | null;
        } | null = null;

        // Track whether we received a response_complete before stream closed.
        // If the stream closes without a terminal event, we synthesize a failure.
        let receivedTerminal = false;

        while (true) {
          const { done, value } = await reader.read();

          if (done) {
            // Stream closed — check if we got a terminal event.
            // If not, synthesize a failure so the frontend can stop loading.
            if (!receivedTerminal) {
              _push({
                event_type: "stream_closed_without_terminal",
                step_name: "stream",
                stage: "stream",
                message: "Stream closed before answer arrived",
                status: "failed",
                timestamp: new Date().toISOString(),
              } as unknown as ProcessingEvent);
              options.onError?.("Stream closed before the answer was received.");
            }
            break;
          }

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const raw = line.slice(6).trim();
            if (!raw) continue;

            try {
              const data = JSON.parse(raw) as ProcessingEvent & {
                type?: string;
                metadata?: { answer?: string; sources?: unknown[] };
              };

              if (data.type === "stream_done") {
                options.onDone?.();
                // stream_done means server is done — no more reads needed.
                // We don't break here; we let the outer while loop naturally
                // reach `done = true` so cleanup is consistent.
                continue;
              }

              _push(data);

              // Extract answer from the response_complete event.
              // The backend sends payload (not metadata) per sse_schemas.py.
              const eventPayload = (data as unknown as Record<string, unknown>).payload as Record<string, unknown> | undefined;
              if (
                data.event_type === "response_complete" &&
                eventPayload?.answer != null
              ) {
                receivedTerminal = true;
                finalResult = {
                  answer: eventPayload.answer as string,
                  sources: (eventPayload.sources as unknown[]) ?? [],
                  structured_answer: eventPayload.structured_answer ?? null,
                  answer_type: (eventPayload.answer_type as string) ?? "prose",
                  confidence: (eventPayload.confidence as number | null) ?? null,
                  caveats: (eventPayload.caveats as string[]) ?? [],
                  // pipeline_meta carries fallback/warning context in one place
                  pipeline_meta: (eventPayload.pipeline_meta as Record<string, unknown> | null) ?? null,
                };
              }

              // Also count error events as terminal (prevents stuck state).
              if (data.event_type === "error") {
                receivedTerminal = true;
              }
            } catch {
              // ignore parse errors on individual frames
            }
          }
        }

        return finalResult;
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          options.onError?.(
            err instanceof Error ? err.message : "Stream error"
          );
        }
        return null;
      } finally {
        setIsStreaming(false);
        abortRef.current = null;
      }
    },
    [_push, options]
  );

  const disconnect = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
    abortRef.current?.abort();
    abortRef.current = null;
    setIsStreaming(false);
  }, []);

  return {
    events,
    isStreaming,
    clearEvents,
    connectToSession,
    streamChatQuery,
    disconnect,
  };
}
