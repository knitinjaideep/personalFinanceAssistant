/**
 * EventStreamPanel — live agent activity feed.
 *
 * Displays structured processing events streamed from the backend.
 * Shows a safe execution trace (not raw LLM chain-of-thought).
 */

import React from "react";
import { clsx } from "clsx";
import { CheckCircle, XCircle, Loader2, AlertTriangle, Info } from "lucide-react";
import type { ProcessingEvent } from "../../types";

interface EventStreamPanelProps {
  events: ProcessingEvent[];
  isStreaming: boolean;
  className?: string;
}

function statusIcon(status: string, size = 14) {
  switch (status) {
    case "complete":
      return <CheckCircle size={size} className="text-green-500 shrink-0" />;
    case "failed":
      return <XCircle size={size} className="text-red-500 shrink-0" />;
    case "warning":
      return <AlertTriangle size={size} className="text-yellow-500 shrink-0" />;
    case "started":
    case "in_progress":
      return <Loader2 size={size} className="text-blue-500 animate-spin shrink-0" />;
    default:
      return <Info size={size} className="text-gray-400 shrink-0" />;
  }
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return "";
  }
}

function ProgressBar({ value }: { value: number }) {
  return (
    <div className="mt-1 h-1 bg-gray-100 rounded-full overflow-hidden">
      <div
        className="h-full bg-blue-400 rounded-full transition-all duration-300"
        style={{ width: `${Math.round(value * 100)}%` }}
      />
    </div>
  );
}

export function EventStreamPanel({
  events,
  isStreaming,
  className,
}: EventStreamPanelProps) {
  if (events.length === 0 && !isStreaming) return null;

  return (
    <div
      className={clsx(
        "rounded-xl border border-gray-200 bg-gray-50 overflow-hidden",
        className
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-200 bg-white">
        {isStreaming ? (
          <Loader2 size={13} className="text-blue-500 animate-spin" />
        ) : (
          <CheckCircle size={13} className="text-green-500" />
        )}
        <span className="text-xs font-medium text-gray-700">
          {isStreaming ? "Processing…" : "Complete"}
        </span>
        <span className="ml-auto text-xs text-gray-400">
          {events.length} event{events.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Event list */}
      <div className="max-h-64 overflow-y-auto divide-y divide-gray-100">
        {events.map((event, i) => (
          <div
            key={i}
            className={clsx(
              "px-3 py-2 text-xs",
              event.status === "failed" && "bg-red-50",
              event.status === "warning" && "bg-yellow-50"
            )}
          >
            <div className="flex items-start gap-2">
              {statusIcon(event.status)}
              <div className="flex-1 min-w-0">
                <div className="flex items-baseline gap-2">
                  <span
                    className={clsx(
                      "font-medium",
                      event.status === "failed"
                        ? "text-red-700"
                        : event.status === "warning"
                        ? "text-yellow-700"
                        : "text-gray-800"
                    )}
                  >
                    {event.message}
                  </span>
                  <span className="text-gray-400 text-[10px] shrink-0">
                    {formatTime(event.timestamp)}
                  </span>
                </div>

                <div className="flex items-center gap-2 mt-0.5 text-gray-400 text-[10px]">
                  <span className="font-mono">{event.agent_name}</span>
                  {event.bucket_name && (
                    <>
                      <span>·</span>
                      <span>{event.bucket_name}</span>
                    </>
                  )}
                  {event.document_name && (
                    <>
                      <span>·</span>
                      <span className="truncate max-w-[120px]">
                        {event.document_name}
                      </span>
                    </>
                  )}
                </div>

                {event.progress != null && event.status !== "complete" && (
                  <ProgressBar value={event.progress} />
                )}
              </div>
            </div>
          </div>
        ))}

        {isStreaming && (
          <div className="px-3 py-2 flex items-center gap-2 text-xs text-gray-400">
            <Loader2 size={12} className="animate-spin" />
            <span>Waiting for next event…</span>
          </div>
        )}
      </div>
    </div>
  );
}
