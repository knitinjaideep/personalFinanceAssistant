"use client";

import { useState, useCallback, useEffect } from "react";
import { useDropzone } from "react-dropzone";
import {
  Upload, Loader2, CheckCircle2, AlertCircle, FileText,
  ChevronDown, FolderOpen, Sparkles,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import toast from "react-hot-toast";
import { catalogApi } from "@/features/upload/api";
import type { InstitutionOption, MonthOption } from "@/features/upload/api";
import { useAppStore } from "@/store/appStore";

const CURRENT_YEAR = new Date().getFullYear();
const YEAR_OPTIONS = [CURRENT_YEAR, CURRENT_YEAR - 1, CURRENT_YEAR - 2, CURRENT_YEAR - 3];

interface FileResult {
  filename: string;
  status: "ok" | "duplicate" | "error";
  message?: string;
  document_id?: string;
}

interface UploadPanelProps {
  onUploaded?: () => void;
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
        className="text-xs text-center font-medium py-1"
        style={{ color: "var(--text-muted)" }}
      >
        {INGESTION_STAGES[stageIdx]}
      </motion.p>
    </AnimatePresence>
  );
}

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
        className="w-full appearance-none rounded-xl border px-3.5 py-2.5 pr-9 text-sm focus:outline-none focus:ring-2 disabled:opacity-50 disabled:cursor-not-allowed"
        style={{
          background: isEmpty ? "var(--panel-bg)" : "var(--panel-bg-alt)",
          borderColor: isEmpty ? "var(--border-subtle)" : "var(--border-accent)",
          color: isEmpty ? "var(--text-muted)" : "var(--text-primary)",
        }}
      >
        {placeholder && <option value="" disabled>{placeholder}</option>}
        {children}
      </select>
      <ChevronDown size={14} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }} />
    </div>
  );
}

export default function UploadPanel({ onUploaded }: UploadPanelProps) {
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

  useEffect(() => {
    catalogApi.institutions().then(setInstitutions).catch(() => {});
    catalogApi.months().then(setMonths).catch(() => {});
  }, []);

  useEffect(() => {
    if (!institutionSlug || !accountSlug || !year || !month) {
      setDestinationPreview("");
      return;
    }
    catalogApi.destinationPreview(institutionSlug, accountSlug, year, month)
      .then((p) => setDestinationPreview(p.rel_path))
      .catch(() => setDestinationPreview(""));
  }, [institutionSlug, accountSlug, year, month]);

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
  const yearOptions = selectedAccount ? selectedAccount.supported_years : YEAR_OPTIONS;
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
          addIngestionJob({
            document_id: data.document_id,
            filename: file.name,
            status: "processing",
            started_at: Date.now(),
          });
        }
      } catch (err: unknown) {
        collected.push({ filename: file.name, status: "error", message: err instanceof Error ? err.message : "Network error" });
      }

      setProgress((p) => p + 1);
    }

    setResults(collected);
    setPhase("done");
    onUploaded?.();

    const ok = collected.filter((r) => r.status === "ok").length;
    const dupes = collected.filter((r) => r.status === "duplicate").length;
    const errs = collected.filter((r) => r.status === "error").length;

    if (ok > 0) toast.success(`${ok} file${ok > 1 ? "s" : ""} saved — parsing in background`);
    if (dupes > 0) toast(`${dupes} already ingested — skipped`, { icon: "ℹ️" });
    if (errs > 0) toast.error(`${errs} file${errs > 1 ? "s" : ""} failed`);
  }

  return (
    <div className="space-y-4">
      {phase === "pick" && (
        <div
          {...(getRootProps() as React.HTMLAttributes<HTMLDivElement>)}
          className="rounded-2xl border-2 border-dashed p-10 text-center cursor-pointer transition-all"
          style={{
            borderColor: isDragActive ? "#FF7A5A" : "var(--border-accent)",
            background: isDragActive ? "rgba(255,122,90,0.05)" : "var(--upload-bg)",
          }}
        >
          <input {...getInputProps()} />
          <Upload size={28} className="mx-auto mb-3" style={{ color: "var(--text-muted)" }} />
          <p className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
            {isDragActive ? "Drop here" : "Drop PDFs or click to browse"}
          </p>
          <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>Multiple files OK · up to 50 MB each</p>
        </div>
      )}

      {(phase === "configure" || phase === "uploading") && files.length > 0 && (
        <>
          <div className="rounded-xl border divide-y max-h-48 overflow-y-auto" style={{ borderColor: "var(--border-subtle)" }}>
            {files.map((f, i) => (
              <div key={i} className="flex items-center gap-2.5 px-4 py-2.5">
                <FileText size={14} style={{ color: "var(--text-muted)" }} className="shrink-0" />
                <span className="text-[13px] truncate flex-1" style={{ color: "var(--text-primary)" }} title={f.name}>{f.name}</span>
                <span className="text-[11px] shrink-0 tabular-nums" style={{ color: "var(--text-dim)" }}>
                  {(f.size / 1024 / 1024).toFixed(1)} MB
                </span>
              </div>
            ))}
          </div>

          <div className="space-y-2.5">
            <label className="text-[11px] font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
              Destination <span style={{ color: "#FF7A5A" }}>*</span>
            </label>

            <SelectField value={institutionSlug} onChange={setInstitutionSlug} disabled={phase === "uploading"} placeholder="— Institution —">
              {institutions.map((inst) => (
                <option key={inst.institution_slug} value={inst.institution_slug}>{inst.institution_label}</option>
              ))}
            </SelectField>

            <SelectField value={accountSlug} onChange={setAccountSlug} disabled={phase === "uploading" || !institutionSlug} placeholder="— Account —">
              {accountOptions.map((a) => (
                <option key={a.account_slug} value={a.account_slug}>{a.account_label}{!a.parseable ? " (text only)" : ""}</option>
              ))}
            </SelectField>

            <div className="grid grid-cols-2 gap-2">
              <SelectField value={String(year)} onChange={(v) => setYear(Number(v))} disabled={phase === "uploading"} placeholder="Year">
                {yearOptions.map((y) => <option key={y} value={y}>{y}</option>)}
              </SelectField>
              <SelectField value={String(month)} onChange={(v) => setMonth(Number(v))} disabled={phase === "uploading"} placeholder="Month">
                {months.map((m) => <option key={m.month} value={m.month}>{m.label}</option>)}
              </SelectField>
            </div>

            {destinationPreview && (
              <div className="rounded-xl px-3 py-2.5 flex items-start gap-2" style={{ background: "var(--panel-bg)", border: "1px solid var(--border-subtle)" }}>
                <FolderOpen size={13} style={{ color: "var(--text-muted)" }} className="shrink-0 mt-0.5" />
                <p className="text-xs font-mono break-all leading-relaxed" style={{ color: "var(--text-muted)" }}>{destinationPreview}</p>
              </div>
            )}
          </div>

          {phase === "uploading" && (
            <div className="space-y-2">
              <div className="flex justify-between text-[10px]" style={{ color: "var(--text-muted)" }}>
                <span>Uploading &amp; processing…</span>
                <span>{progress}/{files.length}</span>
              </div>
              <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "var(--border-subtle)" }}>
                <motion.div
                  className="h-full rounded-full"
                  style={{ background: "var(--accent-coral-grad)" }}
                  animate={{ width: `${files.length > 0 ? (progress / files.length) * 100 : 0}%` }}
                  transition={{ duration: 0.4 }}
                />
              </div>
              <StageIndicator active={phase === "uploading"} />
            </div>
          )}

          <div className="flex gap-3 pt-1">
            <button
              onClick={() => { setPhase("pick"); setFiles([]); setInstitutionSlug(""); setAccountSlug(""); }}
              disabled={phase === "uploading"}
              className="flex-1 rounded-xl border py-2.5 text-sm font-medium transition-colors disabled:opacity-40"
              style={{ borderColor: "var(--border-accent)", color: "var(--text-secondary)" }}
            >
              Back
            </button>
            <button
              onClick={handleUpload}
              disabled={!canUpload || phase === "uploading"}
              className="flex-1 rounded-xl py-2.5 text-sm font-semibold text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              style={{ background: canUpload && phase !== "uploading" ? "var(--accent-coral-grad)" : "var(--btn-glass-bg)" }}
            >
              {phase === "uploading" ? (
                <><Loader2 size={15} className="animate-spin" /> Uploading…</>
              ) : (
                <><Sparkles size={14} /> Save &amp; Process{files.length > 1 ? ` (${files.length})` : ""}</>
              )}
            </button>
          </div>
        </>
      )}

      {phase === "done" && (
        <div className="space-y-3">
          <div className="flex flex-col items-center gap-2 py-2">
            <CheckCircle2 size={32} className="text-emerald-500" />
            <p className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>Upload complete</p>
            <p className="text-xs text-center" style={{ color: "var(--text-muted)" }}>
              Parsing continues in background — ask a question anytime.
            </p>
          </div>

          <div className="rounded-xl border divide-y max-h-40 overflow-y-auto" style={{ borderColor: "var(--border-subtle)" }}>
            {results.map((r, i) => (
              <div key={i} className="flex items-center gap-2 px-3 py-2">
                {r.status === "ok" && <CheckCircle2 size={13} className="text-emerald-500 shrink-0" />}
                {r.status === "duplicate" && <span className="text-[13px] shrink-0">ℹ️</span>}
                {r.status === "error" && <AlertCircle size={13} className="shrink-0" style={{ color: "#FF7A5A" }} />}
                <div className="min-w-0 flex-1">
                  <p className="text-xs truncate" style={{ color: "var(--text-secondary)" }}>{r.filename}</p>
                  {r.status === "duplicate" && <p className="text-[10px]" style={{ color: "var(--text-dim)" }}>Already ingested — skipped</p>}
                  {r.status === "error" && <p className="text-[10px]" style={{ color: "#FF7A5A" }}>{r.message}</p>}
                </div>
              </div>
            ))}
          </div>

          <button
            onClick={() => { setPhase("pick"); setFiles([]); setResults([]); }}
            className="w-full rounded-xl border py-2.5 text-sm font-medium transition-colors"
            style={{ borderColor: "var(--border-accent)", color: "var(--text-secondary)" }}
          >
            Upload more
          </button>
        </div>
      )}
    </div>
  );
}
