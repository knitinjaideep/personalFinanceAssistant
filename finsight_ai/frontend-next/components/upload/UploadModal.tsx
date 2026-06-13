"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Upload, Layers, Shield } from "lucide-react";
import { useAppStore } from "@/store/appStore";
import UploadPanel from "./UploadPanel";
import BulkUploadPanel from "./BulkUploadPanel";

type Mode = "single" | "bulk";

/**
 * GlobalUploadModal — the single upload surface for the whole app.
 *
 * Opened from the top-nav "Upload documents" button and from page CTAs via the
 * Zustand store (openUploadModal). Large, premium layout with a fixed header,
 * tabbed body, and a scrollable content area. The single/bulk panels keep their
 * exact backend wiring (upload-local / bulk-upload-local) — this component only
 * owns the shell and mode switching.
 */
export default function UploadModal() {
  const open = useAppStore((s) => s.uploadModalOpen);
  const close = useAppStore((s) => s.closeUploadModal);
  const [mode, setMode] = useState<Mode>("single");

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, close]);

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [open]);

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.22 }}
            className="fixed inset-0 z-50"
            style={{ background: "var(--modal-overlay)", backdropFilter: "blur(6px)", WebkitBackdropFilter: "blur(6px)" }}
            onClick={close}
          />

          <motion.div
            key="modal"
            initial={{ opacity: 0, scale: 0.97, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 8 }}
            transition={{ type: "spring", stiffness: 340, damping: 32 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 pointer-events-none"
          >
            <div
              className="relative flex flex-col pointer-events-auto overflow-hidden rounded-[28px]"
              style={{
                width: "min(1100px, calc(100vw - 32px))",
                height: "min(820px, calc(100vh - 32px))",
                background: "var(--modal-bg)",
                border: "1px solid var(--modal-border)",
                boxShadow: "var(--modal-shadow)",
                backdropFilter: "blur(28px)",
                WebkitBackdropFilter: "blur(28px)",
              }}
            >
              {/* ── Fixed header ─────────────────────────────────────────── */}
              <div
                className="shrink-0 flex items-center justify-between gap-4 px-6 sm:px-8 pt-6 pb-5"
                style={{ borderBottom: "1px solid var(--border-subtle)" }}
              >
                <div className="flex items-center gap-3.5 min-w-0">
                  <div
                    className="w-11 h-11 rounded-2xl flex items-center justify-center shrink-0"
                    style={{
                      background: "var(--coral-soft)",
                      border: "1px solid var(--coral-border)",
                    }}
                  >
                    <Upload size={19} style={{ color: "var(--accent-coral-solid)" }} />
                  </div>
                  <div className="min-w-0">
                    <h2 className="card-title-lg leading-tight" style={{ color: "var(--text-primary)" }}>
                      Upload documents
                    </h2>
                    <p className="small-text mt-0.5 flex items-center gap-1.5" style={{ color: "var(--text-muted)" }}>
                      <Shield size={11} style={{ color: "var(--accent-strong)" }} />
                      Processed locally — nothing leaves your device
                    </p>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={close}
                  className="w-9 h-9 rounded-xl flex items-center justify-center transition-colors shrink-0 hover:scale-105"
                  style={{
                    background: "var(--btn-glass-bg)",
                    border: "1px solid var(--btn-glass-border)",
                    color: "var(--text-muted)",
                  }}
                  aria-label="Close"
                >
                  <X size={16} />
                </button>
              </div>

              {/* ── Tabs ─────────────────────────────────────────────────── */}
              <div className="shrink-0 flex gap-2 px-6 sm:px-8 pt-5">
                {(["single", "bulk"] as Mode[]).map((m) => {
                  const activeTab = mode === m;
                  return (
                    <button
                      key={m}
                      type="button"
                      onClick={() => setMode(m)}
                      className="relative flex items-center gap-2 px-4 py-2.5 rounded-2xl text-[13px] font-semibold transition-all"
                      style={{
                        color: activeTab ? "white" : "var(--text-secondary)",
                        background: activeTab ? "var(--accent-coral-grad)" : "var(--btn-glass-bg)",
                        border: activeTab ? "none" : "1px solid var(--btn-glass-border)",
                        boxShadow: activeTab ? "0 4px 16px var(--coral-glow)" : "none",
                      }}
                    >
                      {m === "single" ? <Upload size={14} /> : <Layers size={14} />}
                      {m === "single" ? "Single upload" : "Bulk upload"}
                    </button>
                  );
                })}
              </div>

              {/* ── Scrollable body ──────────────────────────────────────── */}
              <div className="flex-1 min-h-0 overflow-y-auto px-6 sm:px-8 py-6">
                {mode === "single" ? (
                  <UploadPanel onUploaded={close} />
                ) : (
                  <BulkUploadPanel onUploaded={close} />
                )}
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
