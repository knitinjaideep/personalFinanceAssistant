/**
 * AgentTrace — collapsible live agent activity panel for the chat screen.
 *
 * Shows the same structured events as EventStreamPanel but styled for
 * the chat context: more compact, collapsible, and positioned above the answer.
 */

import React, { useState } from "react";
import { clsx } from "clsx";
import {
  ChevronDown,
  ChevronUp,
  CheckCircle,
  XCircle,
  Loader2,
  AlertTriangle,
  Cpu,
} from "lucide-react";
import type { ProcessingEvent } from "../../types";

interface AgentTraceProps {
  events: ProcessingEvent[];
  isStreaming: boolean;
}

function statusDot(status: string) {
  switch (status) {
    case "complete":
      return <CheckCircle size={11} className="text-green-500 shrink-0" />;
    case "failed":
      return <XCircle size={11} className="text-red-400 shrink-0" />;
    case "warning":
      return <AlertTriangle size={11} className="text-yellow-400 shrink-0" />;
    case "started":
    case "in_progress":
      return <Loader2 size={11} className="text-blue-400 animate-spin shrink-0" />;
    default:
      return <span className="w-2 h-2 rounded-full bg-gray-300 shrink-0 inline-block" />;
  }
}

export function AgentTrace({ events, isStreaming }: AgentTraceProps) {
  const [collapsed, setCollapsed] = useState(false);

  if (events.length === 0 && !isStreaming) return null;

  const lastEvent = events[events.length - 1];

  return (
    <div className="rounded-xl border border-gray-200 bg-gray-50 text-xs overflow-hidden mb-3">
      {/* Header — always visible */}
      <button
        type="button"
        onClick={() => setCollapsed((c) => !c)}
        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-gray-100 transition-colors text-left"
      >
        <Cpu size={12} className={clsx("shrink-0", isStreaming ? "text-blue-500" : "text-gray-400")} />
        <span className="font-medium text-gray-600 flex-1">
          {isStreaming
            ? lastEvent?.message ?? "Processing…"
            : `Done · ${events.length} step${events.length !== 1 ? "s" : ""}`}
        </span>
        {isStreaming && <Loader2 size={11} className="text-blue-400 animate-spin shrink-0" />}
        {collapsed ? (
          <ChevronDown size={12} className="text-gray-400 shrink-0" />
        ) : (
          <ChevronUp size={12} className="text-gray-400 shrink-0" />
        )}
      </button>

      {/* Event list */}
      {!collapsed && (
        <div className="border-t border-gray-200 max-h-48 overflow-y-auto divide-y divide-gray-100">
          {events.map((event, i) => (
            <div
              key={i}
              className={clsx(
                "flex items-start gap-2 px-3 py-1.5",
                event.status === "failed" && "bg-red-50",
                event.status === "warning" && "bg-yellow-50"
              )}
            >
              {statusDot(event.status)}
              <span
                className={clsx(
                  "flex-1",
                  event.status === "failed" ? "text-red-700" : "text-gray-700"
                )}
              >
                {event.message}
              </span>
              <span className="text-gray-400 text-[10px] shrink-0 font-mono">
                {event.agent_name}
              </span>
              {event.progress != null && event.status !== "complete" && (
                <span className="text-blue-500 text-[10px] shrink-0">
                  {Math.round(event.progress * 100)}%
                </span>
              )}
            </div>
          ))}

          {isStreaming && (
            <div className="px-3 py-1.5 flex items-center gap-2 text-gray-400">
              <Loader2 size={10} className="animate-spin" />
              <span>Waiting…</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
