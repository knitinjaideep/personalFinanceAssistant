import { api } from "./client";
import type { ChatRequest, ChatResponse, StructuredAnswer } from "../types";

// ── SSE event types emitted by /chat/stream ──────────────────────────────────

export type StreamEventType =
  | "status"
  | "intent"
  | "tool_start"
  | "tool_result"
  | "answer_token"
  | "table"
  | "chart"
  | "error"
  | "done";

export interface StreamCallbacks {
  onStatus?: (message: string) => void;
  onIntent?: (intent: string, confidence: number) => void;
  onToolStart?: (tool: string, intent: string) => void;
  onToolResult?: (rowCount: number, summary: string) => void;
  onToken?: (text: string) => void;
  onTable?: (columns: string[], rows: Record<string, unknown>[]) => void;
  onChart?: (chart: Record<string, unknown>) => void;
  onError?: (message: string) => void;
  onDone?: (requestId: string, answer?: StructuredAnswer) => void;
}

/**
 * Stream a chat response using Server-Sent Events.
 * Returns a cleanup function that aborts the request when called.
 */
export function streamChat(
  request: ChatRequest,
  callbacks: StreamCallbacks
): () => void {
  const controller = new AbortController();

  (async () => {
    try {
      const response = await fetch("/api/v1/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        callbacks.onError?.(`Request failed: ${response.statusText}`);
        callbacks.onDone?.("");
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() ?? "";

        for (const chunk of chunks) {
          if (!chunk.trim()) continue;

          let eventType: StreamEventType = "status";
          let dataLine = "";

          for (const line of chunk.split("\n")) {
            if (line.startsWith("event: ")) {
              eventType = line.slice(7).trim() as StreamEventType;
            } else if (line.startsWith("data: ")) {
              dataLine = line.slice(6).trim();
            }
          }

          if (!dataLine) continue;
          let data: Record<string, unknown>;
          try {
            data = JSON.parse(dataLine);
          } catch {
            continue;
          }

          switch (eventType) {
            case "status":
              callbacks.onStatus?.(data.message as string);
              break;
            case "intent":
              callbacks.onIntent?.(data.intent as string, data.confidence as number);
              break;
            case "tool_start":
              callbacks.onToolStart?.(data.tool as string, data.intent as string);
              break;
            case "tool_result":
              callbacks.onToolResult?.(data.row_count as number, data.summary as string);
              break;
            case "answer_token":
              callbacks.onToken?.(data.text as string);
              break;
            case "table":
              callbacks.onTable?.(
                data.columns as string[],
                data.rows as Record<string, unknown>[]
              );
              break;
            case "chart":
              callbacks.onChart?.(data);
              break;
            case "error":
              callbacks.onError?.(data.message as string);
              break;
            case "done":
              callbacks.onDone?.(
                (data.request_id as string) ?? "",
                data.answer as StructuredAnswer | undefined,
              );
              break;
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        callbacks.onError?.("Connection lost. Please try again.");
        callbacks.onDone?.("");
      }
    }
  })();

  return () => controller.abort();
}

export const chatApi = {
  query: (request: ChatRequest): Promise<ChatResponse> =>
    api.post<ChatResponse>("/chat/query", request),
  stream: streamChat,
};
