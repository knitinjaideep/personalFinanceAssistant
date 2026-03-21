/**
 * UploadModal — drop a PDF, choose the Coral destination folder, confirm.
 *
 * Flow:
 *   1. User drops (or clicks to pick) a PDF file.
 *   2. Modal shows the chosen file + a destination selector (source_id + year).
 *   3. On confirm → POST /api/v1/documents/upload with source_id and year form fields.
 *   4. On success → callback fires so the parent can refresh data.
 */

import { useState, useCallback, useEffect } from "react";
import { useDropzone } from "react-dropzone";
import {
  X, Upload, FolderOpen, Loader2, CheckCircle2, ChevronDown,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import toast from "react-hot-toast";

// ── Source definitions (mirrors statement_sources.py) ────────────────────────
// Kept in sync with STATEMENT_SOURCES. source_id must match the backend slug.

interface SourceOption {
  source_id: string;
  label: string;
  bucket: "investments" | "banking";
}

const SOURCE_OPTIONS: SourceOption[] = [
  // Banking
  { source_id: "chase_checking", label: "Chase Checking",           bucket: "banking" },
  { source_id: "chase_freedom",  label: "Chase Freedom Unlimited",  bucket: "banking" },
  { source_id: "chase_prime",    label: "Chase Prime",              bucket: "banking" },
  { source_id: "chase_sapphire", label: "Chase Sapphire Preferred", bucket: "banking" },
  { source_id: "amex",           label: "American Express",         bucket: "banking" },
  { source_id: "bofa",           label: "Bank of America",          bucket: "banking" },
  { source_id: "discover",       label: "Discover",                 bucket: "banking" },
  { source_id: "marcus",         label: "Marcus Goldman Sachs",     bucket: "banking" },
  // Investments
  { source_id: "etrade",             label: "E*TRADE",                      bucket: "investments" },
  { source_id: "morgan_stanley_ira", label: "Morgan Stanley IRA",           bucket: "investments" },
  { source_id: "morgan_stanley_joint", label: "Morgan Stanley Joint",       bucket: "investments" },
];

const CURRENT_YEAR = new Date().getFullYear();
const YEAR_OPTIONS = [CURRENT_YEAR, CURRENT_YEAR - 1, CURRENT_YEAR - 2, CURRENT_YEAR - 3];

// ── Component ─────────────────────────────────────────────────────────────────

interface UploadModalProps {
  open: boolean;
  onClose: () => void;
  onUploaded: () => void;
}

type Phase = "pick" | "configure" | "uploading" | "done";

export function UploadModal({ open, onClose, onUploaded }: UploadModalProps) {
  const [phase, setPhase] = useState<Phase>("pick");
  const [pickedFile, setPickedFile] = useState<File | null>(null);
  const [sourceId, setSourceId] = useState<string>(SOURCE_OPTIONS[0].source_id);
  const [year, setYear] = useState<number>(CURRENT_YEAR);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Reset state when modal opens
  useEffect(() => {
    if (open) {
      setPhase("pick");
      setPickedFile(null);
      setSourceId(SOURCE_OPTIONS[0].source_id);
      setYear(CURRENT_YEAR);
      setErrorMsg(null);
    }
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  const onDrop = useCallback((accepted: File[]) => {
    if (accepted.length > 0) {
      setPickedFile(accepted[0]);
      setPhase("configure");
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    multiple: false,
    disabled: phase !== "pick",
  });

  const selectedSource = SOURCE_OPTIONS.find(s => s.source_id === sourceId)!;

  async function handleUpload() {
    if (!pickedFile) return;
    setPhase("uploading");
    setErrorMsg(null);

    const form = new FormData();
    form.append("file", pickedFile);
    form.append("source_id", sourceId);
    form.append("year", String(year));

    try {
      const res = await fetch("/api/v1/documents/upload", { method: "POST", body: form });
      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Upload failed");
      }

      if (data.message?.includes("duplicate")) {
        toast("File already ingested — skipping.", { icon: "ℹ️" });
      } else {
        toast.success(`Saved to ${selectedSource.label} (${year}) — parsing in background`);
      }

      setPhase("done");
      onUploaded();
      setTimeout(onClose, 1200);
    } catch (err: any) {
      setErrorMsg(err.message || "Upload failed");
      setPhase("configure");
    }
  }

  if (!open) return null;

  // Group sources by bucket for the dropdown
  const banking    = SOURCE_OPTIONS.filter(s => s.bucket === "banking");
  const investment = SOURCE_OPTIONS.filter(s => s.bucket === "investments");

  return (
    // Backdrop
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(11,60,93,0.55)", backdropFilter: "blur(6px)" }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <AnimatePresence>
        <motion.div
          key="modal"
          initial={{ opacity: 0, scale: 0.95, y: 12 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 12 }}
          transition={{ type: "spring", stiffness: 320, damping: 28 }}
          className="relative w-full max-w-md rounded-3xl overflow-hidden shadow-2xl"
          style={{
            background: "rgba(255,255,255,0.96)",
            border: "1px solid rgba(205,237,246,0.7)",
          }}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-6 pt-6 pb-4">
            <div>
              <h2 className="text-lg font-bold text-ocean-900">Add Statement</h2>
              <p className="text-xs text-ocean-400 mt-0.5">Save to your Coral folder structure</p>
            </div>
            <button
              onClick={onClose}
              className="rounded-full p-1.5 text-ocean-300 hover:text-ocean-600 hover:bg-ocean-50 transition-colors"
            >
              <X size={18} />
            </button>
          </div>

          <div className="px-6 pb-6 space-y-5">

            {/* Step 1 — Drop zone */}
            {phase === "pick" && (
              <div
                {...(getRootProps() as any)}
                className={[
                  "rounded-2xl border-2 border-dashed p-10 text-center cursor-pointer transition-colors",
                  isDragActive
                    ? "border-coral bg-coral/5"
                    : "border-ocean-200 hover:border-ocean-400 bg-ocean-50/40",
                ].join(" ")}
              >
                <input {...getInputProps()} />
                <Upload size={28} className="mx-auto mb-3 text-ocean-300" />
                <p className="text-sm font-semibold text-ocean-700">
                  {isDragActive ? "Drop it here" : "Drop a PDF or click to browse"}
                </p>
                <p className="text-xs text-ocean-400 mt-1">Single PDF, up to 50 MB</p>
              </div>
            )}

            {/* Step 2 — Configure destination */}
            {(phase === "configure" || phase === "uploading") && pickedFile && (
              <>
                {/* Chosen file pill */}
                <div className="flex items-center gap-3 rounded-xl px-4 py-3 bg-ocean-50 border border-ocean-100">
                  <FolderOpen size={16} className="text-ocean shrink-0" />
                  <span className="text-sm font-medium text-ocean-800 truncate flex-1">
                    {pickedFile.name}
                  </span>
                  <span className="text-xs text-ocean-400 shrink-0">
                    {(pickedFile.size / 1024 / 1024).toFixed(1)} MB
                  </span>
                </div>

                {/* Destination selector */}
                <div className="space-y-3">
                  <label className="text-xs font-semibold text-ocean-500 uppercase tracking-wide">
                    Destination folder
                  </label>
                  <div className="relative">
                    <select
                      value={sourceId}
                      onChange={e => setSourceId(e.target.value)}
                      disabled={phase === "uploading"}
                      className="w-full appearance-none rounded-xl border border-ocean-200 bg-white px-4 py-2.5 pr-9 text-sm text-ocean-800 focus:outline-none focus:ring-2 focus:ring-ocean/30 disabled:opacity-50"
                    >
                      <optgroup label="Banking">
                        {banking.map(s => (
                          <option key={s.source_id} value={s.source_id}>{s.label}</option>
                        ))}
                      </optgroup>
                      <optgroup label="Investments">
                        {investment.map(s => (
                          <option key={s.source_id} value={s.source_id}>{s.label}</option>
                        ))}
                      </optgroup>
                    </select>
                    <ChevronDown size={15} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-ocean-400" />
                  </div>

                  {/* Year */}
                  <div className="relative">
                    <select
                      value={year}
                      onChange={e => setYear(Number(e.target.value))}
                      disabled={phase === "uploading"}
                      className="w-full appearance-none rounded-xl border border-ocean-200 bg-white px-4 py-2.5 pr-9 text-sm text-ocean-800 focus:outline-none focus:ring-2 focus:ring-ocean/30 disabled:opacity-50"
                    >
                      {YEAR_OPTIONS.map(y => (
                        <option key={y} value={y}>{y}</option>
                      ))}
                    </select>
                    <ChevronDown size={15} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-ocean-400" />
                  </div>

                  {/* Destination preview */}
                  <p className="text-xs text-ocean-400 font-mono bg-ocean-50 rounded-lg px-3 py-2 truncate">
                    Coral/{selectedSource.label.replace(/\s/g, " ")}/{year}/{pickedFile.name}
                  </p>
                </div>

                {/* Error */}
                {errorMsg && (
                  <p className="text-xs text-red-600 rounded-lg bg-red-50 px-3 py-2">{errorMsg}</p>
                )}

                {/* Actions */}
                <div className="flex gap-3 pt-1">
                  <button
                    onClick={() => { setPhase("pick"); setPickedFile(null); }}
                    disabled={phase === "uploading"}
                    className="flex-1 rounded-xl border border-ocean-200 py-2.5 text-sm font-medium text-ocean-600 hover:bg-ocean-50 transition-colors disabled:opacity-40"
                  >
                    Back
                  </button>
                  <button
                    onClick={handleUpload}
                    disabled={phase === "uploading"}
                    className="flex-1 rounded-xl bg-ocean py-2.5 text-sm font-semibold text-white hover:bg-ocean-700 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    {phase === "uploading" ? (
                      <>
                        <Loader2 size={15} className="animate-spin" />
                        Uploading…
                      </>
                    ) : (
                      <>
                        <Upload size={15} />
                        Save & Process
                      </>
                    )}
                  </button>
                </div>
              </>
            )}

            {/* Step 3 — Done */}
            {phase === "done" && (
              <div className="flex flex-col items-center gap-3 py-6">
                <CheckCircle2 size={36} className="text-emerald-500" />
                <p className="text-sm font-semibold text-ocean-800">File saved — parsing in background</p>
              </div>
            )}
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
