/// <reference types="vite/client" />
/**
 * DebugPanel — collapsible observability panel shown under each assistant answer.
 *
 * Only rendered when import.meta.env.VITE_DEBUG === "true".
 * Shows request_id, intent, route, confidence, SQL, timings, sources, chart summary.
 */

import { useState } from "react";
import { ChevronDown, ChevronUp, Bug } from "lucide-react";
import type { StructuredAnswer } from "../../types";

interface DebugPanelProps {
  answer: StructuredAnswer;
}

const VITE_DEBUG = import.meta.env.VITE_DEBUG === "true";

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

  if (!VITE_DEBUG) return null;

  const { request_id, intent, query_path, confidence, sql_used, rows_used, timings, chart_payload, citations } = answer;

  const sources = citations?.map((c) => c.source).filter(Boolean) ?? [];

  return (
    <div
      className="mt-2 rounded-xl text-[10px] font-mono overflow-hidden"
      style={{
        background: "rgba(11,60,93,0.04)",
        border: "1px solid rgba(11,60,93,0.12)",
      }}
    >
      {/* Toggle */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-1.5 px-3 py-1.5 text-left hover:bg-black/5 transition-colors"
      >
        <Bug size={10} className="text-ocean/50 flex-shrink-0" />
        <span className="text-ocean/50 flex-1">
          Debug
          {request_id ? ` · ${request_id.slice(0, 8)}…` : ""}
          {intent ? ` · ${intent}` : ""}
          {query_path ? ` → ${query_path}` : ""}
        </span>
        {open ? <ChevronUp size={10} className="text-ocean/40" /> : <ChevronDown size={10} className="text-ocean/40" />}
      </button>

      {/* Detail */}
      {open && (
        <div className="px-3 pb-3 pt-1 grid grid-cols-2 gap-x-4 gap-y-1 text-ocean/60">

          {/* Identity */}
          <Row label="request_id" value={request_id || "—"} full />
          <Row label="intent"     value={intent || "—"} />
          <Row label="route"      value={query_path || "—"} />
          <Row label="confidence" value={pct(confidence)} />

          {/* Data */}
          <Row label="rows_used"  value={String(rows_used ?? "—")} />
          <Row label="sources"    value={sources.length ? sources.join(", ") : "—"} />

          {/* Timings */}
          <div className="col-span-2 mt-1 mb-0.5 font-semibold text-ocean/40 uppercase tracking-wide text-[9px]">
            Timings
          </div>
          <Row label="intent"  value={ms(timings?.intent_ms)} />
          <Row label="sql"     value={ms(timings?.sql_ms)} />
          <Row label="rag"     value={ms(timings?.rag_ms)} />
          <Row label="llm"     value={ms(timings?.llm_ms)} />
          <Row label="total"   value={ms(timings?.total_ms)} />

          {/* SQL */}
          {sql_used && sql_used.length > 0 && (
            <>
              <div className="col-span-2 mt-1 mb-0.5 font-semibold text-ocean/40 uppercase tracking-wide text-[9px]">
                SQL used
              </div>
              {sql_used.map((s, i) => (
                <pre key={i} className="col-span-2 text-[9px] whitespace-pre-wrap break-all text-ocean/50 bg-black/5 rounded px-2 py-1">
                  {s}
                </pre>
              ))}
            </>
          )}

          {/* Chart */}
          {chart_payload && (
            <>
              <div className="col-span-2 mt-1 mb-0.5 font-semibold text-ocean/40 uppercase tracking-wide text-[9px]">
                Chart payload
              </div>
              <Row label="type"   value={chart_payload.type} />
              <Row label="labels" value={`${chart_payload.labels?.length ?? 0} items`} />
            </>
          )}
        </div>
      )}
    </div>
  );
}

function Row({ label, value, full }: { label: string; value: string; full?: boolean }) {
  return (
    <>
      <span className={`text-ocean/40 ${full ? "col-span-2" : ""}`}>
        {label}
        {full ? "" : ":"}
      </span>
      {!full && (
        <span className="text-ocean/70 break-all">{value}</span>
      )}
      {full && (
        <span className="col-span-2 -mt-1 text-ocean/70 break-all">{value}</span>
      )}
    </>
  );
}
