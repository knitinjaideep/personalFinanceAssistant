"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, Bug } from "lucide-react";
import type { StructuredAnswer } from "@/types/index";

interface DebugPanelProps {
  answer: StructuredAnswer;
}

// In Next.js we use NEXT_PUBLIC_ prefix instead of VITE_
const DEBUG_MODE = process.env.NEXT_PUBLIC_DEBUG === "true";

function ms(val: number | null | undefined): string {
  if (val == null) return "—";
  return `${val.toFixed(1)} ms`;
}

function pct(val: number | null | undefined): string {
  if (val == null) return "—";
  return `${(val * 100).toFixed(0)}%`;
}

export function DebugPanel({ answer }: DebugPanelProps) {
  const [open, setOpen] = useState(false);

  if (!DEBUG_MODE) return null;

  const { request_id, intent, query_path, confidence, sql_used, rows_used, timings, chart_payload, citations } = answer;
  const sources = citations?.map((c) => c.source).filter(Boolean) ?? [];

  return (
    <div
      className="mt-2 max-w-2xl rounded-xl text-[10px] font-mono overflow-hidden"
      style={{
        background: "rgba(3,17,31,0.70)",
        border: "1px solid rgba(34,211,238,0.14)",
      }}
    >
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-1.5 px-3 py-1.5 text-left transition-colors"
        style={{ color: "rgba(34,211,238,0.40)" }}
      >
        <Bug size={10} className="shrink-0" />
        <span className="flex-1">
          Show Debug Info
          {request_id && <span style={{ color: "rgba(34,211,238,0.28)" }}> · {request_id.slice(0, 8)}…</span>}
          {intent && <span style={{ color: "rgba(34,211,238,0.28)" }}> · {intent}</span>}
        </span>
        {open ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
      </button>

      {open && (
        <div
          className="px-3 pb-3 pt-1 grid grid-cols-2 gap-x-6 gap-y-0.5 overflow-y-auto"
          style={{ maxHeight: "320px", borderTop: "1px solid rgba(34,211,238,0.10)" }}
        >
          <div className="col-span-2 mt-2 mb-0.5 uppercase tracking-widest text-[8px] font-semibold" style={{ color: "rgba(34,211,238,0.30)" }}>Identity</div>
          <span style={{ color: "rgba(34,211,238,0.32)" }}>request_id:</span>
          <span className="break-all" style={{ color: "rgba(34,211,238,0.50)" }}>{request_id || "—"}</span>
          <span style={{ color: "rgba(34,211,238,0.32)" }}>intent:</span>
          <span style={{ color: "rgba(34,211,238,0.50)" }}>{intent || "—"}</span>
          <span style={{ color: "rgba(34,211,238,0.32)" }}>route:</span>
          <span style={{ color: "rgba(34,211,238,0.50)" }}>{query_path || "—"}</span>
          <span style={{ color: "rgba(34,211,238,0.32)" }}>confidence:</span>
          <span style={{ color: "rgba(34,211,238,0.50)" }}>{pct(confidence)}</span>

          <div className="col-span-2 mt-2 mb-0.5 uppercase tracking-widest text-[8px] font-semibold" style={{ color: "rgba(34,211,238,0.30)" }}>Timings</div>
          <span style={{ color: "rgba(34,211,238,0.32)" }}>total:</span>
          <span style={{ color: "rgba(34,211,238,0.65)" }}>{ms(timings?.total_ms)}</span>

          {sql_used && sql_used.length > 0 && (
            <>
              <div className="col-span-2 mt-2 mb-0.5 uppercase tracking-widest text-[8px] font-semibold" style={{ color: "rgba(34,211,238,0.30)" }}>SQL used</div>
              {sql_used.map((s, i) => (
                <pre
                  key={i}
                  className="col-span-2 text-[9px] whitespace-pre-wrap break-all rounded-lg px-2 py-1.5"
                  style={{
                    background: "rgba(3,17,31,0.60)",
                    border: "1px solid rgba(34,211,238,0.12)",
                    color: "rgba(34,211,238,0.55)",
                  }}
                >
                  {s}
                </pre>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}
