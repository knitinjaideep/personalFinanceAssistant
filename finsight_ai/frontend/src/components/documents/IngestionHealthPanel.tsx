import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronRight, ShieldCheck, ShieldAlert } from "lucide-react";
import type { IngestionHealth } from "../../types";
import { issueLabel } from "../../utils/documentUtils";

interface Props {
  health: IngestionHealth | null;
  loading: boolean;
}

const METRICS: Array<{ key: keyof IngestionHealth["summary"]; label: string; bad?: boolean }> = [
  { key: "complete_documents", label: "Complete" },
  { key: "incomplete_documents", label: "Incomplete", bad: true },
  { key: "missing_transactions", label: "No transactions", bad: true },
  { key: "missing_chunks", label: "No chunks", bad: true },
  { key: "missing_embeddings", label: "No embeddings", bad: true },
  { key: "missing_metadata", label: "Missing metadata", bad: true },
  { key: "stuck_processing", label: "Stuck", bad: true },
  { key: "failed", label: "Failed", bad: true },
];

export function IngestionHealthPanel({ health, loading }: Props) {
  const [open, setOpen] = useState(false);

  if (loading && !health) {
    return (
      <div className="rounded-2xl h-14 animate-pulse" style={{ background: "rgba(205,237,246,0.20)" }} />
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
        background: "rgba(255,255,255,0.85)",
        border: `1px solid ${healthy ? "rgba(76,175,147,0.35)" : "rgba(255,209,102,0.5)"}`,
        boxShadow: "0 4px 24px rgba(11,60,93,0.06)",
      }}
    >
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2.5 px-4 py-3 hover:bg-ocean-50/25 transition-colors"
      >
        <motion.span animate={{ rotate: open ? 90 : 0 }} transition={{ duration: 0.18 }} className="text-ocean/40">
          <ChevronRight size={15} />
        </motion.span>
        <span style={{ color: healthy ? "#4CAF93" : "#c89a00" }}>
          {healthy ? <ShieldCheck size={16} /> : <ShieldAlert size={16} />}
        </span>
        <span className="text-[13.5px] font-bold text-ocean-deep">Ingestion Health</span>
        <span className="text-[11.5px] font-medium" style={{ color: healthy ? "#4CAF93" : "#c89a00" }}>
          {healthy
            ? "All documents complete"
            : `${s.incomplete_documents} need attention`}
        </span>
        <span className="ml-auto text-[11px] text-ocean/40">
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
                background: m.bad ? "rgba(255,209,102,0.18)" : "rgba(76,175,147,0.12)",
                color: m.bad ? "#a07700" : "#4CAF93",
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
            <div className="border-t border-ocean-50/50">
              {docs.map((d) => (
                <div
                  key={d.document_id}
                  className="flex items-center justify-between px-4 py-2.5 border-b border-ocean-50/40 last:border-0"
                >
                  <div className="min-w-0">
                    <p className="text-[12px] font-medium text-ocean-deep truncate">{d.filename}</p>
                    <div className="flex flex-wrap gap-1.5 mt-1">
                      {d.issues.map((iss) => (
                        <span
                          key={iss}
                          className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                          style={{ background: "rgba(228,87,87,0.10)", color: "#E45757" }}
                        >
                          {issueLabel(iss)}
                        </span>
                      ))}
                    </div>
                  </div>
                  <span className="text-[10px] text-ocean/35 shrink-0 ml-3">{d.recommended_action}</span>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
