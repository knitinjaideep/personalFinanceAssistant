/**
 * UploadModal — structured upload with institution/account/year/month selection.
 *
 * Flow:
 *   1. Drop or pick a PDF (or multiple PDFs).
 *   2. Choose institution → account → year → month.
 *   3. Preview the destination path.
 *   4. Upload & ingest — shows live progress through ingestion stages.
 *   5. Done — per-file results with status.
 */

import { useState, useCallback, useEffect } from "react";
import { useDropzone } from "react-dropzone";
import {
  X, Upload, Loader2, CheckCircle2, AlertCircle, FileText,
  ChevronDown, FolderOpen, Sparkles,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import toast from "react-hot-toast";
import { catalogApi } from "../../api/catalog";
import type { InstitutionOption, MonthOption } from "../../api/catalog";
import { useAppStore } from "../../store/appStore";

const CURRENT_YEAR = new Date().getFullYear();
const YEAR_OPTIONS = [CURRENT_YEAR, CURRENT_YEAR - 1, CURRENT_YEAR - 2, CURRENT_YEAR - 3];

interface FileResult {
  filename: string;
  status: "ok" | "duplicate" | "error";
  message?: string;
  document_id?: string;
}

interface UploadModalProps {
  open: boolean;
  onClose: () => void;
  onUploaded: () => void;
}

type Phase = "pick" | "configure" | "uploading" | "done";

const INGESTION_STAGES = [
  "Saving file…",
  "Parsing PDF…",
  "Extracting data…",
  "Saving to database…",
  "Indexing text…",
  "Generating embeddings…",
  "Ready for chat ✓",
];

function StageIndicator({ active }: { active: boolean }) {
  const [stageIdx, setStageIdx] = useState(0);

  useEffect(() => {
    if (!active) return;
    setStageIdx(0);
    const id = setInterval(() => {
      setStageIdx((i) => Math.min(i + 1, INGESTION_STAGES.length - 1));
    }, 2200);
    return () => clearInterval(id);
  }, [active]);

  if (!active) return null;

  return (
    <AnimatePresence mode="wait">
      <motion.p
        key={stageIdx}
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -4 }}
        transition={{ duration: 0.25 }}
        className="text-xs text-ocean/55 text-center font-medium py-1"
      >
        {INGESTION_STAGES[stageIdx]}
      </motion.p>
    </AnimatePresence>
  );
}

export function UploadModal({ open, onClose, onUploaded }: UploadModalProps) {
  const { addIngestionJob } = useAppStore();

  const [phase, setPhase] = useState<Phase>("pick");
  const [files, setFiles] = useState<File[]>([]);
  const [institutions, setInstitutions] = useState<InstitutionOption[]>([]);
  const [months, setMonths] = useState<MonthOption[]>([]);
  const [institutionSlug, setInstitutionSlug] = useState("");
  const [accountSlug, setAccountSlug] = useState("");
  const [year, setYear] = useState(CURRENT_YEAR);
  const [month, setMonth] = useState(new Date().getMonth() + 1);
  const [destinationPreview, setDestinationPreview] = useState("");
  const [results, setResults] = useState<FileResult[]>([]);
  const [progress, setProgress] = useState(0);

  // Load catalog on mount
  useEffect(() => {
    catalogApi.institutions().then(setInstitutions).catch(() => {});
    catalogApi.months().then(setMonths).catch(() => {});
  }, []);

  // Reset when modal opens
  useEffect(() => {
    if (open) {
      setPhase("pick");
      setFiles([]);
      setInstitutionSlug("");
      setAccountSlug("");
      setYear(CURRENT_YEAR);
      setMonth(new Date().getMonth() + 1);
      setDestinationPreview("");
      setResults([]);
      setProgress(0);
    }
  }, [open]);

  // Escape to close
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  // Update destination preview when selections change
  useEffect(() => {
    if (!institutionSlug || !accountSlug || !year || !month) {
      setDestinationPreview("");
      return;
    }
    catalogApi.destinationPreview(institutionSlug, accountSlug, year, month)
      .then((p) => setDestinationPreview(p.rel_path))
      .catch(() => setDestinationPreview(""));
  }, [institutionSlug, accountSlug, year, month]);

  // Reset account when institution changes
  useEffect(() => { setAccountSlug(""); }, [institutionSlug]);

  const onDrop = useCallback((accepted: File[]) => {
    if (accepted.length > 0) {
      setFiles(accepted);
      setPhase("configure");
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    multiple: true,
    disabled: phase !== "pick",
  });

  const selectedInstitution = institutions.find((i) => i.institution_slug === institutionSlug);
  const accountOptions = selectedInstitution?.accounts ?? [];
  const selectedAccount = accountOptions.find((a) => a.account_slug === accountSlug);
  const yearOptions = selectedAccount
    ? selectedAccount.supported_years
    : YEAR_OPTIONS;

  const canUpload = !!institutionSlug && !!accountSlug && !!year && !!month && files.length > 0;

  async function handleUpload() {
    if (!canUpload) return;
    setPhase("uploading");
    setProgress(0);

    const collected: FileResult[] = [];

    for (const file of files) {
      const form = new FormData();
      form.append("file", file);
      form.append("institution_slug", institutionSlug);
      form.append("account_slug", accountSlug);
      form.append("year", String(year));
      form.append("month", String(month));

      try {
        const res = await fetch("/api/v1/documents/upload-local", { method: "POST", body: form });
        const data = await res.json();

        if (!res.ok) {
          collected.push({ filename: file.name, status: "error", message: data.detail || "Upload failed" });
        } else if (data.message?.toLowerCase().includes("duplicate")) {
          collected.push({ filename: file.name, status: "duplicate", document_id: data.document_id });
        } else {
          collected.push({ filename: file.name, status: "ok", document_id: data.document_id });
          // Track ingestion in global store
          addIngestionJob({
            document_id: data.document_id,
            filename: file.name,
            status: "processing",
            started_at: Date.now(),
          });
        }
      } catch (err: any) {
        collected.push({ filename: file.name, status: "error", message: err.message || "Network error" });
      }

      setProgress((p) => p + 1);
    }

    setResults(collected);
    setPhase("done");
    onUploaded();

    const ok    = collected.filter((r) => r.status === "ok").length;
    const dupes = collected.filter((r) => r.status === "duplicate").length;
    const errs  = collected.filter((r) => r.status === "error").length;

    if (ok > 0)    toast.success(`${ok} file${ok > 1 ? "s" : ""} saved — parsing in background`);
    if (dupes > 0) toast(`${dupes} already ingested — skipped`, { icon: "ℹ️" });
    if (errs > 0)  toast.error(`${errs} file${errs > 1 ? "s" : ""} failed`);
  }

  if (!open) return null;


  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(11,60,93,0.55)", backdropFilter: "blur(6px)" }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <AnimatePresence>
        <motion.div
          key="upload-modal"
          initial={{ opacity: 0, scale: 0.95, y: 12 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 12 }}
          transition={{ type: "spring", stiffness: 320, damping: 28 }}
          className="relative w-full max-w-md rounded-3xl overflow-hidden shadow-2xl"
          style={{
            background: "rgba(255,255,255,0.97)",
            border: "1px solid rgba(205,237,246,0.7)",
          }}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-6 pt-6 pb-4">
            <div>
              <h2 className="text-lg font-bold text-ocean-900">Add Statement{files.length > 1 ? "s" : ""}</h2>
              <p className="text-xs text-ocean/40 mt-0.5">Save to your Coral folder, parse &amp; index</p>
            </div>
            <button
              onClick={onClose}
              className="rounded-full p-1.5 text-ocean/30 hover:text-ocean/70 hover:bg-ocean-50 transition-colors"
            >
              <X size={18} />
            </button>
          </div>

          <div className="px-6 pb-6 space-y-4">

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
                <Upload size={28} className="mx-auto mb-3 text-ocean/30" />
                <p className="text-sm font-semibold text-ocean-700">
                  {isDragActive ? "Drop here" : "Drop PDFs or click to browse"}
                </p>
                <p className="text-xs text-ocean/40 mt-1">Multiple files OK · up to 50 MB each</p>
              </div>
            )}

            {/* Step 2 — Configure destination */}
            {(phase === "configure" || phase === "uploading") && files.length > 0 && (
              <>
                {/* File list */}
                <div className="rounded-xl border border-ocean-100 bg-ocean-50/60 divide-y divide-ocean-100 max-h-28 overflow-y-auto">
                  {files.map((f, i) => (
                    <div key={i} className="flex items-center gap-2 px-3 py-2">
                      <FileText size={13} className="text-ocean/40 shrink-0" />
                      <span className="text-xs text-ocean-800 truncate flex-1">{f.name}</span>
                      <span className="text-[10px] text-ocean/35 shrink-0 tabular-nums">
                        {(f.size / 1024 / 1024).toFixed(1)} MB
                      </span>
                    </div>
                  ))}
                </div>

                {/* Selectors */}
                <div className="space-y-2.5">
                  <label className="text-[11px] font-semibold text-ocean/50 uppercase tracking-wide">
                    Destination
                    <span className="text-coral ml-0.5">*</span>
                  </label>

                  {/* Institution */}
                  <SelectField
                    value={institutionSlug}
                    onChange={(v) => setInstitutionSlug(v)}
                    disabled={phase === "uploading"}
                    placeholder="— Institution —"
                  >
                    {institutions.map((inst) => (
                      <option key={inst.institution_slug} value={inst.institution_slug}>
                        {inst.institution_label}
                      </option>
                    ))}
                  </SelectField>

                  {/* Account */}
                  <SelectField
                    value={accountSlug}
                    onChange={(v) => setAccountSlug(v)}
                    disabled={phase === "uploading" || !institutionSlug}
                    placeholder="— Account —"
                  >
                    {accountOptions.map((a) => (
                      <option key={a.account_slug} value={a.account_slug}>
                        {a.account_label}
                        {!a.parseable ? " (text only)" : ""}
                      </option>
                    ))}
                  </SelectField>

                  {/* Year + Month row */}
                  <div className="grid grid-cols-2 gap-2">
                    <SelectField
                      value={String(year)}
                      onChange={(v) => setYear(Number(v))}
                      disabled={phase === "uploading"}
                      placeholder="Year"
                    >
                      {yearOptions.map((y) => (
                        <option key={y} value={y}>{y}</option>
                      ))}
                    </SelectField>

                    <SelectField
                      value={String(month)}
                      onChange={(v) => setMonth(Number(v))}
                      disabled={phase === "uploading"}
                      placeholder="Month"
                    >
                      {months.map((m) => (
                        <option key={m.month} value={m.month}>{m.label}</option>
                      ))}
                    </SelectField>
                  </div>

                  {/* Destination preview */}
                  {destinationPreview && (
                    <div
                      className="rounded-xl px-3 py-2.5 flex items-start gap-2"
                      style={{ background: "rgba(205,237,246,0.25)", border: "1px solid rgba(205,237,246,0.5)" }}
                    >
                      <FolderOpen size={13} className="text-ocean/40 shrink-0 mt-0.5" />
                      <p className="text-xs text-ocean/60 font-mono break-all leading-relaxed">
                        {destinationPreview}
                      </p>
                    </div>
                  )}
                </div>

                {/* Uploading progress */}
                {phase === "uploading" && (
                  <div className="space-y-2">
                    <div className="flex justify-between text-[10px] text-ocean/40 mb-1">
                      <span>Uploading &amp; processing…</span>
                      <span>{progress}/{files.length}</span>
                    </div>
                    <div className="h-1.5 rounded-full bg-ocean-100 overflow-hidden">
                      <motion.div
                        className="h-full bg-ocean rounded-full"
                        animate={{ width: `${files.length > 0 ? (progress / files.length) * 100 : 0}%` }}
                        transition={{ duration: 0.4 }}
                      />
                    </div>
                    <StageIndicator active={phase === "uploading"} />
                  </div>
                )}

                {/* Actions */}
                <div className="flex gap-3 pt-1">
                  <button
                    onClick={() => { setPhase("pick"); setFiles([]); setInstitutionSlug(""); setAccountSlug(""); }}
                    disabled={phase === "uploading"}
                    className="flex-1 rounded-xl border border-ocean-200 py-2.5 text-sm font-medium text-ocean-600 hover:bg-ocean-50 transition-colors disabled:opacity-40"
                  >
                    Back
                  </button>
                  <button
                    onClick={handleUpload}
                    disabled={!canUpload || phase === "uploading"}
                    className="flex-1 rounded-xl py-2.5 text-sm font-semibold text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                    style={{
                      background: canUpload && phase !== "uploading"
                        ? "linear-gradient(135deg, #0B3C5D, #1F6F8B)"
                        : undefined,
                    }}
                  >
                    {phase === "uploading" ? (
                      <>
                        <Loader2 size={15} className="animate-spin" />
                        Uploading…
                      </>
                    ) : (
                      <>
                        <Sparkles size={14} />
                        Save &amp; Process{files.length > 1 ? ` (${files.length})` : ""}
                      </>
                    )}
                  </button>
                </div>
              </>
            )}

            {/* Step 3 — Done */}
            {phase === "done" && (
              <div className="space-y-3">
                <div className="flex flex-col items-center gap-2 py-2">
                  <CheckCircle2 size={32} className="text-emerald-500" />
                  <p className="text-sm font-semibold text-ocean-800">Upload complete</p>
                  <p className="text-xs text-ocean/40 text-center">
                    Parsing continues in background — ask a question anytime.
                  </p>
                </div>

                <div className="rounded-xl border border-ocean-100 divide-y divide-ocean-100 max-h-40 overflow-y-auto">
                  {results.map((r, i) => (
                    <div key={i} className="flex items-center gap-2 px-3 py-2">
                      {r.status === "ok"        && <CheckCircle2 size={13} className="text-emerald-500 shrink-0" />}
                      {r.status === "duplicate" && <span className="text-[13px] shrink-0">ℹ️</span>}
                      {r.status === "error"     && <AlertCircle size={13} className="text-coral shrink-0" />}
                      <div className="min-w-0 flex-1">
                        <p className="text-xs text-ocean-800 truncate">{r.filename}</p>
                        {r.status === "duplicate" && (
                          <p className="text-[10px] text-ocean/40">Already ingested — skipped</p>
                        )}
                        {r.status === "error" && (
                          <p className="text-[10px] text-coral">{r.message}</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>

                <button
                  onClick={onClose}
                  className="w-full rounded-xl border border-ocean-200 py-2.5 text-sm font-medium text-ocean-600 hover:bg-ocean-50 transition-colors"
                >
                  Close
                </button>
              </div>
            )}
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

// ── SelectField ───────────────────────────────────────────────────────────────

function SelectField({
  value, onChange, disabled, placeholder, children,
}: {
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  placeholder?: string;
  children: React.ReactNode;
}) {
  const isEmpty = !value;
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className={[
          "w-full appearance-none rounded-xl border px-3.5 py-2.5 pr-9 text-sm",
          "focus:outline-none focus:ring-2 focus:ring-ocean/30 disabled:opacity-50 disabled:cursor-not-allowed",
          isEmpty
            ? "border-ocean-200 text-ocean/40 bg-ocean-50/40"
            : "border-ocean-200 text-ocean-800 bg-white",
        ].join(" ")}
      >
        {placeholder && (
          <option value="" disabled>{placeholder}</option>
        )}
        {children}
      </select>
      <ChevronDown size={14} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-ocean/40" />
    </div>
  );
}
