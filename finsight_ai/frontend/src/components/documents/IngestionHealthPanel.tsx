import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronRight, ShieldCheck, ShieldAlert } from "lucide-react";
import type { IngestionHealth } from "../../types";
import { issueLabel } from "../../utils/documentUtils";
import { CoralMascot } from "../CoralMascot";

interface Props {
  health: IngestionHealth | null;
  loading: boolean;
}

const METRICS: Array<{ key: keyof IngestionHealth["summary"]; label: string; bad?: boolean }> = [
  { key: "complete_documents",  label: "Complete" },
  { key: "incomplete_documents", label: "Incomplete",        bad: true },
  { key: "missing_transactions", label: "No transactions",   bad: true },
  { key: "missing_chunks",       label: "No chunks",         bad: true },
  { key: "missing_embeddings",   label: "No embeddings",     bad: true },
  { key: "missing_metadata",     label: "Missing metadata",  bad: true },
  { key: "stuck_processing",     label: "Stuck",             bad: true },
  { key: "failed",               label: "Failed",            bad: true },
];

export function IngestionHealthPanel({ health, loading }: Props) {
  const [open, setOpen] = useState(false);

  if (loading && !health) {
    return (
      <div
        className="rounded-2xl h-14 animate-pulse"
        style={{ background: "rgba(34,211,238,0.06)" }}
      />
    );
  }
  if (!health) return null;

  const s = health.summary;
  const healthy = s.incomplete_documents === 0 && s.failed === 0 && s.stuck_processing === 0;
  const docs = health.documents;

  return (
    <div
      className="rounded-2xl overflow-hidden"
      style={{
        background: "rgba(3,17,31,0.55)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        border: `1px solid ${healthy ? "rgba(76,175,147,0.22)" : "rgba(255,209,102,0.25)"}`,
        boxShadow: "0 8px 32px rgba(3,17,31,0.30)",
      }}
    >
      {/* Warning banner when not healthy */}
      {!healthy && (
        <div
          className="flex items-center gap-3 px-4 py-3"
          style={{
            borderBottom: "1px solid rgba(255,209,102,0.18)",
            background: "rgba(255,209,102,0.06)",
          }}
        >
          <CoralMascot variant="security" size="sm" className="shrink-0" />
          <p className="text-[12px] leading-snug" style={{ color: "rgba(255,255,255,0.65)" }}>
            Some documents need reprocessing before I can answer accurately.
          </p>
        </div>
      )}

      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2.5 px-4 py-3 transition-colors"
        style={{ background: open ? "rgba(34,211,238,0.04)" : "transparent" }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(34,211,238,0.06)")}
        onMouseLeave={(e) => (e.currentTarget.style.background = open ? "rgba(34,211,238,0.04)" : "transparent")}
      >
        <motion.span animate={{ rotate: open ? 90 : 0 }} transition={{ duration: 0.18 }} style={{ color: "rgba(34,211,238,0.45)" }}>
          <ChevronRight size={15} />
        </motion.span>
        <span style={{ color: healthy ? "#4CAF93" : "#c89a00" }}>
          {healthy ? <ShieldCheck size={16} /> : <ShieldAlert size={16} />}
        </span>
        <span className="text-[13.5px] font-bold text-white">Ingestion Health</span>
        <span className="text-[11.5px] font-medium" style={{ color: healthy ? "#4CAF93" : "#c89a00" }}>
          {healthy ? "All documents complete" : `${s.incomplete_documents} need attention`}
        </span>
        <span className="ml-auto text-[11px]" style={{ color: "rgba(255,255,255,0.30)" }}>
          {s.complete_documents}/{s.total_documents} complete
        </span>
      </button>

      {/* Metric chips */}
      <div className="px-4 pb-3 flex flex-wrap gap-2">
        {METRICS.map((m) => {
          const value = s[m.key];
          if (m.bad && value === 0) return null;
          return (
            <span
              key={m.key}
              className="px-2.5 py-1 rounded-full text-[11px] font-medium"
              style={{
                background: m.bad ? "rgba(255,209,102,0.12)" : "rgba(76,175,147,0.12)",
                color: m.bad ? "#c89a00" : "#4CAF93",
              }}
            >
              {m.label}: {value}
            </span>
          );
        })}
      </div>

      <AnimatePresence initial={false}>
        {open && docs.length > 0 && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22 }}
            style={{ overflow: "hidden" }}
          >
            <div style={{ borderTop: "1px solid rgba(34,211,238,0.08)" }}>
              {docs.map((d) => (
                <div
                  key={d.document_id}
                  className="flex items-center justify-between px-4 py-2.5"
                  style={{ borderBottom: "1px solid rgba(34,211,238,0.06)" }}
                >
                  <div className="min-w-0">
                    <p className="text-[12px] font-medium text-white truncate">{d.filename}</p>
                    <div className="flex flex-wrap gap-1.5 mt-1">
                      {d.issues.map((iss) => (
                        <span
                          key={iss}
                          className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                          style={{ background: "rgba(228,87,87,0.12)", color: "#E45757" }}
                        >
                          {issueLabel(iss)}
                        </span>
                      ))}
                    </div>
                  </div>
                  <span className="text-[10px] shrink-0 ml-3" style={{ color: "rgba(255,255,255,0.30)" }}>
                    {d.recommended_action}
                  </span>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
