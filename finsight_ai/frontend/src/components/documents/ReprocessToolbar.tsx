import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { RefreshCw, Loader2, AlertTriangle, Wand2, X } from "lucide-react";
import toast from "react-hot-toast";
import { documentsApi } from "../../api/documents";
import type { ReprocessJob } from "../../types";

type Scope = "all" | "failed" | "missing-data";

interface Props {
  onDone: () => void;
  missingCount?: number;
  failedCount?: number;
}

const POLL_MS = 1500;

export function ReprocessToolbar({ onDone, missingCount = 0, failedCount = 0 }: Props) {
  const [confirmScope, setConfirmScope] = useState<Scope | null>(null);
  const [job, setJob]           = useState<ReprocessJob | null>(null);
  const [starting, setStarting] = useState<Scope | null>(null);
  const pollRef  = useRef<ReturnType<typeof setInterval> | null>(null);
  const mounted  = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const running = job?.status === "running" || starting !== null;

  const startBatch = async (scope: Scope) => {
    setConfirmScope(null);
    setStarting(scope);
    try {
      const start =
        scope === "all"
          ? await documentsApi.reprocessAll()
          : scope === "failed"
          ? await documentsApi.reprocessFailed()
          : await documentsApi.reprocessMissingData();

      if (start.count === 0) {
        toast(scope === "failed" ? "No failed documents." : "Nothing to reprocess — all complete.");
        setStarting(null);
        return;
      }

      toast.success(`Reprocessing ${start.count} document${start.count !== 1 ? "s" : ""}…`);
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        try {
          const j = await documentsApi.reprocessJob(start.job_id);
          if (!mounted.current) return;
          setJob(j);
          if (j.status === "done") {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            setStarting(null);
            const msg = `Reprocessed ${j.succeeded}/${j.total}` + (j.failed ? `, ${j.failed} failed` : "");
            j.failed ? toast.error(msg) : toast.success(msg);
            onDone();
            setTimeout(() => mounted.current && setJob(null), 4000);
          }
        } catch {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setStarting(null);
          toast.error("Lost track of reprocess job");
        }
      }, POLL_MS);
    } catch (e) {
      setStarting(null);
      toast.error(e instanceof Error ? e.message : "Failed to start reprocessing");
    }
  };

  const btn = (scope: Scope, label: string, icon: React.ReactNode, badge?: number, accent?: boolean) => (
    <button
      onClick={() => (scope === "all" ? setConfirmScope("all") : startBatch(scope))}
      disabled={running}
      className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-[12px] font-semibold transition-all disabled:opacity-50 hover:scale-[1.02] card-shimmer-hover gradient-border-hover"
      style={{
        background: accent ? "rgba(255,122,90,0.10)" : "var(--panel-bg)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        border: `1px solid ${accent ? "rgba(255,122,90,0.30)" : "var(--panel-border-accent)"}`,
        color: accent ? "#FF9B85" : "var(--text-secondary)",
        transition: "all 0.22s ease",
      }}
    >
      {starting === scope ? <Loader2 size={13} className="animate-spin" /> : icon}
      {label}
      {badge != null && badge > 0 && (
        <span
          className="ml-0.5 px-1.5 rounded-full text-[10px] font-bold"
          style={{ background: accent ? "#FF7A5A" : "var(--border-accent)", color: accent ? "white" : "var(--text-on-accent)" }}
        >
          {badge}
        </span>
      )}
    </button>
  );

  return (
    <div className="flex flex-col gap-2 relative">
      <div className="flex flex-wrap items-center gap-2">
        {btn("missing-data", "Reprocess Missing Data", <Wand2 size={13} />, missingCount, true)}
        {btn("failed", "Reprocess Failed", <AlertTriangle size={13} />, failedCount)}
        {btn("all", "Reprocess All", <RefreshCw size={13} />)}
      </div>

      {/* Progress bar */}
      <AnimatePresence>
        {job && job.total > 0 && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="rounded-xl px-3 py-2"
            style={{
              background: "var(--panel-bg)",
              backdropFilter: "blur(12px)",
              WebkitBackdropFilter: "blur(12px)",
              border: "1px solid var(--panel-border-accent)",
            }}
          >
            <div className="flex items-center justify-between text-[11px] mb-1" style={{ color: "var(--text-muted)" }}>
              <span className="font-medium">
                {job.status === "running" ? "Reprocessing…" : "Reprocess complete"} ({job.scope})
              </span>
              <span className="tabular">
                {job.completed}/{job.total}
                {job.failed > 0 && <span style={{ color: "#E45757" }}> · {job.failed} failed</span>}
              </span>
            </div>
            <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "var(--insight-bg)" }}>
              <motion.div
                className="h-full rounded-full"
                style={{ background: "linear-gradient(90deg, rgba(34,211,238,0.80), rgba(95,168,211,0.90))" }}
                animate={{ width: `${job.total ? (job.completed / job.total) * 100 : 0}%` }}
                transition={{ duration: 0.3 }}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Confirm modal for Reprocess All */}
      <AnimatePresence>
        {confirmScope === "all" && (
          <motion.div
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            style={{ background: "var(--modal-overlay)", backdropFilter: "blur(8px)", WebkitBackdropFilter: "blur(8px)" }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setConfirmScope(null)}
          >
            <motion.div
              onClick={(e) => e.stopPropagation()}
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1,    opacity: 1 }}
              exit={{ scale: 0.95,   opacity: 0 }}
              className="rounded-2xl p-6 max-w-sm w-full"
              style={{
                background: "var(--modal-bg)",
                backdropFilter: "blur(24px)",
                WebkitBackdropFilter: "blur(24px)",
                border: "1px solid var(--modal-border)",
                boxShadow: "var(--modal-shadow)",
              }}
            >
              <div className="flex items-start justify-between mb-3">
                <h3 className="text-[15px] font-bold" style={{ color: "var(--text-primary)" }}>
                  Reprocess all documents?
                </h3>
                <button
                  onClick={() => setConfirmScope(null)}
                  className="p-1 rounded-lg transition-colors"
                  style={{ color: "var(--text-dim)" }}
                  onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text-secondary)")}
                  onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-dim)")}
                >
                  <X size={16} />
                </button>
              </div>
              <p className="text-[12.5px] leading-relaxed mb-5" style={{ color: "var(--text-muted)" }}>
                This re-runs extraction for every document. Existing PDFs are kept; each document's
                stale rows are replaced with freshly parsed data. This can take a while.
              </p>
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setConfirmScope(null)}
                  className="px-3.5 py-2 rounded-xl text-[12px] font-medium"
                  style={{
                    background: "var(--btn-glass-bg)",
                    border: "1px solid var(--btn-glass-border)",
                    color: "var(--btn-glass-color)",
                  }}
                >
                  Cancel
                </button>
                <button
                  onClick={() => startBatch("all")}
                  className="btn-coral px-3.5 py-2 rounded-xl text-[12px] font-semibold text-white"
                >
                  Reprocess All
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
