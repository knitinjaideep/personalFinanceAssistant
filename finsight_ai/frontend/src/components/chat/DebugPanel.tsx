/// <reference types="vite/client" />
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
      className="mt-2 max-w-2xl rounded-xl text-[10px] font-mono overflow-hidden"
      style={{
        background: "rgba(3,17,31,0.70)",
        border: "1px solid rgba(34,211,238,0.14)",
      }}
    >
      {/* Toggle */}
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
          {query_path && <span style={{ color: "rgba(34,211,238,0.22)" }}> → {query_path}</span>}
        </span>
        {open
          ? <ChevronUp size={10} style={{ color: "rgba(34,211,238,0.30)" }} />
          : <ChevronDown size={10} style={{ color: "rgba(34,211,238,0.30)" }} />}
      </button>

      {/* Detail — scrollable */}
      {open && (
        <div
          className="px-3 pb-3 pt-1 grid grid-cols-2 gap-x-6 gap-y-0.5 overflow-y-auto"
          style={{ maxHeight: "320px", borderTop: "1px solid rgba(34,211,238,0.10)" }}
        >
          {/* Identity */}
          <SectionHeader label="Identity" />
          <Row label="request_id" value={request_id || "—"} full />
          <Row label="intent"     value={intent || "—"} />
          <Row label="route"      value={query_path || "—"} />
          <Row label="confidence" value={pct(confidence)} />

          {/* Data */}
          <SectionHeader label="Data" />
          <Row label="rows_used" value={String(rows_used ?? "—")} />
          <Row label="sources"   value={sources.length ? sources.join(", ") : "—"} />

          {/* Timings */}
          <SectionHeader label="Timings" />
          <Row label="intent" value={ms(timings?.intent_ms)} />
          <Row label="parse"  value={ms(timings?.parse_ms)} />
          <Row label="sql"    value={ms(timings?.sql_ms)} />
          <Row label="rag"    value={ms(timings?.rag_ms)} />
          <Row label="llm"    value={ms(timings?.llm_ms)} />
          <Row label="total"  value={ms(timings?.total_ms)} bold />

          {/* SQL */}
          {sql_used && sql_used.length > 0 && (
            <>
              <SectionHeader label="SQL used" />
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

          {/* Chart */}
          {chart_payload && (
            <>
              <SectionHeader label="Chart payload" />
              <Row label="type"   value={chart_payload.type} />
              <Row label="labels" value={`${chart_payload.labels?.length ?? 0} items`} />
            </>
          )}
        </div>
      )}
    </div>
  );
}

function SectionHeader({ label }: { label: string }) {
  return (
    <div className="col-span-2 mt-2 mb-0.5 uppercase tracking-widest text-[8px] font-semibold" style={{ color: "rgba(34,211,238,0.30)" }}>
      {label}
    </div>
  );
}

function Row({ label, value, full, bold }: {
  label: string;
  value: string;
  full?: boolean;
  bold?: boolean;
}) {
  return (
    <>
      <span className={`${full ? "col-span-2" : ""}`} style={{ color: "rgba(34,211,238,0.32)" }}>
        {label}:
      </span>
      <span
        className={`break-all ${full ? "col-span-2 -mt-0.5" : ""}`}
        style={{ color: bold ? "rgba(34,211,238,0.65)" : "rgba(34,211,238,0.50)" }}
      >
        {value}
      </span>
    </>
  );
}
