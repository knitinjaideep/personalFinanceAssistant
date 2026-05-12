/**
 * BulkUploadModal — select many PDFs (or a folder), auto-detect metadata,
 * review + correct per-file, then ingest all in one batch request.
 *
 * Flow:
 *   1. "pick"   — Dropzone (multi-file, webkitdirectory fallback, folder drag)
 *   2. "review" — Editable table: filename / institution / account / year / month /
 *                 destination / warnings.  Bulk-apply controls at the top.
 *   3. "uploading" — Per-file progress rows.
 *   4. "done"   — Summary: uploaded / duplicates / ingested / failed / partial.
 */

import { useState, useCallback, useEffect, useRef } from "react";
import { useDropzone } from "react-dropzone";
import {
  X, Upload, Loader2, CheckCircle2, AlertCircle, FileText,
  ChevronDown, FolderOpen, Layers, AlertTriangle, SkipForward,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import toast from "react-hot-toast";
import { catalogApi } from "../../api/catalog";
import type { InstitutionOption, MonthOption } from "../../api/catalog";
import { useAppStore } from "../../store/appStore";
import {
  detectFromFilename,
  getRowWarnings,
  type RowWarning,
} from "./filenameDetection";

// ── Types ──────────────────────────────────────────────────────────────────────

interface BulkRow {
  id: string;
  file: File;
  institution_slug: string;
  account_slug: string;
  year: number | null;
  month: number | null;
  dest_preview: string;
  detection_confidence: "high" | "low" | "none" | "manual";
  warnings: RowWarning[];
}

type UploadOutcome = "saved" | "duplicate_skipped" | "failed";

interface RowResult {
  filename: string;
  outcome: UploadOutcome;
  document_id?: string;
  destination_path?: string;
  error_message?: string;
}

interface BulkSummaryData {
  uploaded: number;
  duplicates_skipped: number;
  successfully_ingested: number;
  failed: number;
  partial_parses: number;
  results: RowResult[];
}

type Phase = "pick" | "review" | "uploading" | "done";

interface BulkUploadModalProps {
  open: boolean;
  onClose: () => void;
  onUploaded: () => void;
}

const CURRENT_YEAR = new Date().getFullYear();
const YEAR_OPTIONS = [CURRENT_YEAR, CURRENT_YEAR - 1, CURRENT_YEAR - 2, CURRENT_YEAR - 3];

// ── Small helpers ──────────────────────────────────────────────────────────────

function nanoid() {
  return Math.random().toString(36).slice(2, 10);
}

function RowStatusIcon({ outcome }: { outcome: UploadOutcome | "pending" | "uploading" }) {
  if (outcome === "uploading") return <Loader2 size={13} className="animate-spin text-ocean/50 shrink-0" />;
  if (outcome === "saved") return <CheckCircle2 size={13} className="text-emerald-500 shrink-0" />;
  if (outcome === "duplicate_skipped") return <SkipForward size={13} className="text-amber-400 shrink-0" />;
  if (outcome === "failed") return <AlertCircle size={13} className="text-coral shrink-0" />;
  return <span className="w-3 h-3 rounded-full bg-ocean-100 shrink-0 inline-block" />;
}

// ── Main component ─────────────────────────────────────────────────────────────

export function BulkUploadModal({ open, onClose, onUploaded }: BulkUploadModalProps) {
  const { addIngestionJob } = useAppStore();

  const [phase, setPhase] = useState<Phase>("pick");
  const [rows, setRows] = useState<BulkRow[]>([]);
  const [institutions, setInstitutions] = useState<InstitutionOption[]>([]);
  const [months, setMonths] = useState<MonthOption[]>([]);

  // Bulk-apply state
  const [bulkInstitution, setBulkInstitution] = useState("");
  const [bulkAccount, setBulkAccount] = useState("");
  const [bulkYear, setBulkYear] = useState<number | "">("");

  // Upload progress
  const [rowStatuses, setRowStatuses] = useState<Map<string, UploadOutcome | "uploading" | "pending">>(new Map());
  const [summary, setSummary] = useState<BulkSummaryData | null>(null);

  // Load catalog
  useEffect(() => {
    catalogApi.institutions().then(setInstitutions).catch(() => {});
    catalogApi.months().then(setMonths).catch(() => {});
  }, []);

  // Reset on open
  useEffect(() => {
    if (open) {
      setPhase("pick");
      setRows([]);
      setBulkInstitution("");
      setBulkAccount("");
      setBulkYear("");
      setRowStatuses(new Map());
      setSummary(null);
    }
  }, [open]);

  // Escape to close
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  // ── Dropzone ────────────────────────────────────────────────────────────────

  const buildRows = useCallback((files: File[]) => {
    const pdfs = files.filter((f) => f.name.toLowerCase().endsWith(".pdf"));
    const skipped = files.length - pdfs.length;
    if (skipped > 0) toast(`${skipped} non-PDF file${skipped > 1 ? "s" : ""} skipped`, { icon: "ℹ️" });
    if (pdfs.length === 0) return;

    const newRows: BulkRow[] = pdfs.map((f) => {
      const detected = detectFromFilename(f.name, institutions);
      return {
        id: nanoid(),
        file: f,
        institution_slug: detected?.institution_slug ?? "",
        account_slug: detected?.account_slug ?? "",
        year: detected?.year ?? null,
        month: detected?.month ?? null,
        dest_preview: "",
        detection_confidence: detected?.confidence ?? "none",
        warnings: [],
      };
    });

    setRows(recomputeWarnings(newRows, institutions));
    setPhase("review");
  }, [institutions]);

  const onDrop = useCallback((accepted: File[]) => {
    buildRows(accepted);
  }, [buildRows]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    multiple: true,
    disabled: phase !== "pick",
    noClick: false,
  });

  // Folder input ref (webkitdirectory)
  const folderInputRef = useRef<HTMLInputElement>(null);
  function handleFolderInput(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    buildRows(files);
    // Reset so the same folder can be selected again
    if (folderInputRef.current) folderInputRef.current.value = "";
  }

  // ── Row editing ─────────────────────────────────────────────────────────────

  function updateRow(id: string, patch: Partial<Omit<BulkRow, "id" | "file">>) {
    setRows((prev) => {
      const updated = prev.map((r) =>
        r.id === id
          ? { ...r, ...patch, detection_confidence: "manual" as const }
          : r
      );
      return recomputeWarnings(updated, institutions);
    });
  }

  function removeRow(id: string) {
    setRows((prev) => prev.filter((r) => r.id !== id));
  }

  // ── Bulk-apply ──────────────────────────────────────────────────────────────

  const bulkInstOption = institutions.find((i) => i.institution_slug === bulkInstitution);
  const bulkAcctOptions = bulkInstOption?.accounts ?? [];

  function applyBulkInstitution() {
    if (!bulkInstitution) return;
    setRows((prev) => {
      const updated = prev.map((r) => ({
        ...r,
        institution_slug: bulkInstitution,
        account_slug: bulkAccount || r.account_slug,
        detection_confidence: "manual" as const,
      }));
      return recomputeWarnings(updated, institutions);
    });
  }

  function applyBulkYear() {
    if (!bulkYear) return;
    setRows((prev) => {
      const updated = prev.map((r) => ({ ...r, year: Number(bulkYear), detection_confidence: "manual" as const }));
      return recomputeWarnings(updated, institutions);
    });
  }

  // ── Upload ──────────────────────────────────────────────────────────────────

  const validRows = rows.filter((r) => r.warnings.every((w) => w.type !== "not_pdf"));
  const readyCount = validRows.filter(
    (r) => r.institution_slug && r.account_slug && r.year && r.month
  ).length;
  const canIngest = readyCount > 0;

  async function handleIngestAll() {
    if (!canIngest) return;
    setPhase("uploading");

    // Only submit rows that have all required fields
    const toUpload = rows.filter(
      (r) => r.institution_slug && r.account_slug && r.year && r.month && r.file.name.toLowerCase().endsWith(".pdf")
    );

    const initialStatuses = new Map<string, UploadOutcome | "uploading" | "pending">();
    for (const r of rows) initialStatuses.set(r.id, toUpload.includes(r) ? "uploading" : "pending");
    setRowStatuses(new Map(initialStatuses));

    const form = new FormData();
    const instList: string[] = [];
    const acctList: string[] = [];
    const yearList: number[] = [];
    const monthList: number[] = [];

    for (const r of toUpload) {
      form.append("files", r.file);
      instList.push(r.institution_slug);
      acctList.push(r.account_slug);
      yearList.push(r.year!);
      monthList.push(r.month!);
    }

    form.append("institution_slugs", JSON.stringify(instList));
    form.append("account_slugs", JSON.stringify(acctList));
    form.append("years", JSON.stringify(yearList));
    form.append("months", JSON.stringify(monthList));

    try {
      const res = await fetch("/api/v1/documents/bulk-upload-local", {
        method: "POST",
        body: form,
      });
      const data: BulkSummaryData = await res.json();

      if (!res.ok) {
        toast.error("Bulk upload failed: " + ((data as any).detail || "Unknown error"));
        setPhase("review");
        return;
      }

      // Map filename → row id for status updates
      const nameToId = new Map(toUpload.map((r) => [r.file.name, r.id]));
      const finalStatuses = new Map(initialStatuses);

      for (const result of data.results) {
        const rowId = nameToId.get(result.filename);
        if (rowId) {
          finalStatuses.set(rowId, result.outcome as UploadOutcome);
        }
        if (result.outcome === "saved" && result.document_id) {
          addIngestionJob({
            document_id: result.document_id,
            filename: result.filename,
            status: "processing",
            started_at: Date.now(),
          });
        }
      }
      setRowStatuses(finalStatuses);
      setSummary(data);
      setPhase("done");
      onUploaded();

      const ok    = data.uploaded;
      const dupes = data.duplicates_skipped;
      const errs  = data.failed;
      if (ok > 0)    toast.success(`${ok} file${ok > 1 ? "s" : ""} saved — parsing in background`);
      if (dupes > 0) toast(`${dupes} already ingested — skipped`, { icon: "ℹ️" });
      if (errs > 0)  toast.error(`${errs} file${errs > 1 ? "s" : ""} failed`);
    } catch (err: any) {
      toast.error(`Network error: ${err.message}`);
      setPhase("review");
    }
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
          key="bulk-upload-modal"
          initial={{ opacity: 0, scale: 0.95, y: 12 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 12 }}
          transition={{ type: "spring", stiffness: 320, damping: 28 }}
          className="relative w-full rounded-3xl overflow-hidden shadow-2xl flex flex-col"
          style={{
            maxWidth: phase === "pick" ? "28rem" : "62rem",
            maxHeight: "90vh",
            background: "rgba(255,255,255,0.97)",
            border: "1px solid rgba(205,237,246,0.7)",
          }}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-6 pt-6 pb-4 shrink-0">
            <div>
              <h2 className="text-lg font-bold text-ocean-900">Bulk Upload</h2>
              <p className="text-xs text-ocean/40 mt-0.5">
                {phase === "pick" && "Drop many PDFs or a folder"}
                {phase === "review" && `${rows.length} file${rows.length !== 1 ? "s" : ""} selected — review & correct`}
                {phase === "uploading" && "Uploading…"}
                {phase === "done" && "Done"}
              </p>
            </div>
            <button
              onClick={onClose}
              className="rounded-full p-1.5 text-ocean/30 hover:text-ocean/70 hover:bg-ocean-50 transition-colors"
            >
              <X size={18} />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto px-6 pb-6 space-y-4">

            {/* ── Phase: pick ─────────────────────────────────────────────── */}
            {phase === "pick" && (
              <div className="space-y-3">
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
                  <Layers size={28} className="mx-auto mb-3 text-ocean/30" />
                  <p className="text-sm font-semibold text-ocean-700">
                    {isDragActive ? "Drop here" : "Drop PDFs or a folder, or click to browse"}
                  </p>
                  <p className="text-xs text-ocean/40 mt-1">Multiple files OK · up to 50 MB each</p>
                </div>

                {/* Folder upload button */}
                <div className="flex items-center justify-center gap-2">
                  <div className="h-px flex-1 bg-ocean-100" />
                  <span className="text-xs text-ocean/30 px-2">or</span>
                  <div className="h-px flex-1 bg-ocean-100" />
                </div>
                <label className="flex items-center justify-center gap-2 w-full rounded-xl border border-ocean-200 py-2.5 text-sm font-medium text-ocean/60 hover:bg-ocean-50 transition-colors cursor-pointer">
                  <FolderOpen size={14} />
                  Browse folder
                  <input
                    ref={folderInputRef}
                    type="file"
                    className="hidden"
                    accept=".pdf"
                    multiple
                    // @ts-ignore — webkitdirectory is not in standard TS types
                    webkitdirectory=""
                    onChange={handleFolderInput}
                  />
                </label>
              </div>
            )}

            {/* ── Phase: review ───────────────────────────────────────────── */}
            {phase === "review" && (
              <div className="space-y-4">
                {/* Bulk-apply bar */}
                <div
                  className="rounded-2xl px-4 py-3 flex flex-wrap gap-2 items-end"
                  style={{ background: "rgba(205,237,246,0.25)", border: "1px solid rgba(205,237,246,0.5)" }}
                >
                  <span className="text-[11px] font-semibold text-ocean/50 uppercase tracking-wide w-full mb-0.5">
                    Bulk apply to all rows
                  </span>

                  <div className="flex gap-2 flex-wrap flex-1">
                    <MiniSelect
                      value={bulkInstitution}
                      onChange={(v) => { setBulkInstitution(v); setBulkAccount(""); }}
                      placeholder="Institution"
                    >
                      {institutions.map((i) => (
                        <option key={i.institution_slug} value={i.institution_slug}>
                          {i.institution_label}
                        </option>
                      ))}
                    </MiniSelect>

                    <MiniSelect
                      value={bulkAccount}
                      onChange={setBulkAccount}
                      disabled={!bulkInstitution}
                      placeholder="Account"
                    >
                      {bulkAcctOptions.map((a) => (
                        <option key={a.account_slug} value={a.account_slug}>
                          {a.account_label}
                        </option>
                      ))}
                    </MiniSelect>

                    <button
                      onClick={applyBulkInstitution}
                      disabled={!bulkInstitution}
                      className="px-3 py-1.5 rounded-lg text-xs font-medium text-white disabled:opacity-40 transition-colors"
                      style={{ background: "linear-gradient(135deg, #0B3C5D, #1F6F8B)" }}
                    >
                      Apply institution
                    </button>
                  </div>

                  <div className="flex gap-2 items-center">
                    <MiniSelect
                      value={String(bulkYear)}
                      onChange={(v) => setBulkYear(v ? Number(v) : "")}
                      placeholder="Year"
                    >
                      {YEAR_OPTIONS.map((y) => (
                        <option key={y} value={y}>{y}</option>
                      ))}
                    </MiniSelect>
                    <button
                      onClick={applyBulkYear}
                      disabled={!bulkYear}
                      className="px-3 py-1.5 rounded-lg text-xs font-medium text-white disabled:opacity-40 transition-colors"
                      style={{ background: "linear-gradient(135deg, #0B3C5D, #1F6F8B)" }}
                    >
                      Apply year
                    </button>
                  </div>
                </div>

                {/* Stats bar */}
                <div className="flex gap-3 text-xs text-ocean/50">
                  <span>{rows.length} file{rows.length !== 1 ? "s" : ""}</span>
                  <span>·</span>
                  <span className="text-emerald-600 font-medium">{readyCount} ready</span>
                  {rows.length - readyCount > 0 && (
                    <>
                      <span>·</span>
                      <span className="text-amber-500 font-medium">{rows.length - readyCount} need attention</span>
                    </>
                  )}
                </div>

                {/* Review table */}
                <div className="rounded-xl border border-ocean-100 overflow-hidden">
                  <div
                    className="grid text-[10px] font-semibold uppercase tracking-wide text-ocean/40 px-3 py-2 border-b border-ocean-100"
                    style={{ gridTemplateColumns: "1fr 140px 140px 70px 100px 16px" }}
                  >
                    <span>File</span>
                    <span>Institution</span>
                    <span>Account</span>
                    <span>Year</span>
                    <span>Month</span>
                    <span />
                  </div>
                  <div className="divide-y divide-ocean-50 max-h-[40vh] overflow-y-auto">
                    {rows.map((row) => (
                      <ReviewRow
                        key={row.id}
                        row={row}
                        institutions={institutions}
                        months={months}
                        onUpdate={(patch) => updateRow(row.id, patch)}
                        onRemove={() => removeRow(row.id)}
                      />
                    ))}
                  </div>
                </div>

                {/* Actions */}
                <div className="flex gap-3 pt-1">
                  <button
                    onClick={() => { setRows([]); setPhase("pick"); }}
                    className="flex-1 rounded-xl border border-ocean-200 py-2.5 text-sm font-medium text-ocean-600 hover:bg-ocean-50 transition-colors"
                  >
                    Back
                  </button>
                  <button
                    onClick={handleIngestAll}
                    disabled={!canIngest}
                    className="flex-1 rounded-xl py-2.5 text-sm font-semibold text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                    style={{
                      background: canIngest
                        ? "linear-gradient(135deg, #FF7A5A, #FFA38F)"
                        : undefined,
                      boxShadow: canIngest ? "0 4px 12px rgba(255,122,90,0.30)" : undefined,
                    }}
                  >
                    <Upload size={14} />
                    Ingest {readyCount} file{readyCount !== 1 ? "s" : ""}
                  </button>
                </div>
              </div>
            )}

            {/* ── Phase: uploading ─────────────────────────────────────────── */}
            {phase === "uploading" && (
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-sm text-ocean/60">
                  <Loader2 size={15} className="animate-spin" />
                  Uploading {rows.length} file{rows.length !== 1 ? "s" : ""}…
                </div>
                <div className="rounded-xl border border-ocean-100 divide-y divide-ocean-50 max-h-[50vh] overflow-y-auto">
                  {rows.map((row) => {
                    const status = rowStatuses.get(row.id) ?? "uploading";
                    return (
                      <div key={row.id} className="flex items-center gap-2 px-3 py-2.5">
                        <RowStatusIcon outcome={status} />
                        <div className="flex-1 min-w-0">
                          <p className="text-xs text-ocean-800 truncate">{row.file.name}</p>
                          <p className="text-[10px] text-ocean/40">
                            {row.institution_slug} / {row.account_slug}
                          </p>
                        </div>
                        <span className="text-[10px] text-ocean/35 tabular-nums">
                          {(row.file.size / 1024 / 1024).toFixed(1)} MB
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* ── Phase: done ──────────────────────────────────────────────── */}
            {phase === "done" && summary && (
              <div className="space-y-4">
                {/* Summary chips */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  <SummaryChip label="Saved" value={summary.uploaded} color="emerald" />
                  <SummaryChip label="Duplicates skipped" value={summary.duplicates_skipped} color="amber" />
                  <SummaryChip label="Failed" value={summary.failed} color="coral" />
                  <SummaryChip label="Partial parses" value={summary.partial_parses} color="ocean" />
                </div>

                <p className="text-xs text-ocean/40">
                  Ingestion runs in background — ask a question anytime.
                </p>

                {/* Per-file results */}
                <div className="rounded-xl border border-ocean-100 divide-y divide-ocean-50 max-h-[40vh] overflow-y-auto">
                  {summary.results.map((r, i) => (
                    <div key={i} className="flex items-center gap-2 px-3 py-2">
                      <RowStatusIcon outcome={r.outcome} />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-ocean-800 truncate">{r.filename}</p>
                        {r.outcome === "duplicate_skipped" && (
                          <p className="text-[10px] text-amber-500">Already ingested — skipped</p>
                        )}
                        {r.outcome === "failed" && r.error_message && (
                          <p className="text-[10px] text-coral truncate">{r.error_message}</p>
                        )}
                        {r.destination_path && (
                          <p className="text-[10px] text-ocean/35 font-mono truncate">{r.destination_path}</p>
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

// ── ReviewRow ─────────────────────────────────────────────────────────────────

function ReviewRow({
  row,
  institutions,
  months,
  onUpdate,
  onRemove,
}: {
  row: BulkRow;
  institutions: InstitutionOption[];
  months: MonthOption[];
  onUpdate: (patch: Partial<Omit<BulkRow, "id" | "file">>) => void;
  onRemove: () => void;
}) {
  const inst = institutions.find((i) => i.institution_slug === row.institution_slug);
  const acctOptions = inst?.accounts ?? [];
  const hasWarning = row.warnings.length > 0;
  const selectedAcct = acctOptions.find((a) => a.account_slug === row.account_slug);
  const yearOptions = selectedAcct?.supported_years ?? YEAR_OPTIONS;

  return (
    <div
      className={[
        "grid items-center gap-1.5 px-3 py-2",
        hasWarning ? "bg-amber-50/30" : "",
      ].join(" ")}
      style={{ gridTemplateColumns: "1fr 140px 140px 70px 100px 16px" }}
    >
      {/* Filename + warnings */}
      <div className="min-w-0">
        <div className="flex items-center gap-1.5">
          <FileText size={11} className="text-ocean/30 shrink-0" />
          <span className="text-xs text-ocean-800 truncate">{row.file.name}</span>
          {row.detection_confidence === "high" && (
            <span className="text-[9px] px-1 rounded bg-emerald-100 text-emerald-600 font-medium shrink-0">auto</span>
          )}
          {row.detection_confidence === "low" && (
            <span className="text-[9px] px-1 rounded bg-amber-100 text-amber-600 font-medium shrink-0">partial</span>
          )}
        </div>
        {row.warnings.map((w, i) => (
          <div key={i} className="flex items-center gap-1 mt-0.5">
            <AlertTriangle size={9} className="text-amber-400 shrink-0" />
            <span className="text-[9px] text-amber-600">{w.message}</span>
          </div>
        ))}
      </div>

      {/* Institution */}
      <MiniSelect
        value={row.institution_slug}
        onChange={(v) => onUpdate({ institution_slug: v, account_slug: "" })}
        placeholder="Institution"
        compact
      >
        {institutions.map((i) => (
          <option key={i.institution_slug} value={i.institution_slug}>
            {i.institution_label}
          </option>
        ))}
      </MiniSelect>

      {/* Account */}
      <MiniSelect
        value={row.account_slug}
        onChange={(v) => onUpdate({ account_slug: v })}
        disabled={!row.institution_slug}
        placeholder="Account"
        compact
      >
        {acctOptions.map((a) => (
          <option key={a.account_slug} value={a.account_slug}>
            {a.account_label}
          </option>
        ))}
      </MiniSelect>

      {/* Year */}
      <MiniSelect
        value={row.year ? String(row.year) : ""}
        onChange={(v) => onUpdate({ year: v ? Number(v) : null })}
        placeholder="Year"
        compact
      >
        {yearOptions.map((y) => (
          <option key={y} value={y}>{y}</option>
        ))}
      </MiniSelect>

      {/* Month */}
      <MiniSelect
        value={row.month ? String(row.month) : ""}
        onChange={(v) => onUpdate({ month: v ? Number(v) : null })}
        placeholder="Month"
        compact
      >
        {months.map((m) => (
          <option key={m.month} value={m.month}>{m.label}</option>
        ))}
      </MiniSelect>

      {/* Remove */}
      <button
        onClick={onRemove}
        className="text-ocean/20 hover:text-coral transition-colors"
        title="Remove"
      >
        <X size={12} />
      </button>
    </div>
  );
}

// ── SummaryChip ───────────────────────────────────────────────────────────────

function SummaryChip({ label, value, color }: { label: string; value: number; color: string }) {
  const colors: Record<string, string> = {
    emerald: "bg-emerald-50 border-emerald-100 text-emerald-700",
    amber: "bg-amber-50 border-amber-100 text-amber-700",
    coral: "bg-red-50 border-red-100 text-red-600",
    ocean: "bg-ocean-50 border-ocean-100 text-ocean-600",
  };
  return (
    <div className={`rounded-xl border px-3 py-2 text-center ${colors[color] ?? colors.ocean}`}>
      <p className="text-lg font-bold tabular-nums">{value}</p>
      <p className="text-[10px] font-medium leading-tight mt-0.5">{label}</p>
    </div>
  );
}

// ── MiniSelect ────────────────────────────────────────────────────────────────

function MiniSelect({
  value,
  onChange,
  disabled,
  placeholder,
  children,
  compact,
}: {
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  placeholder?: string;
  children: React.ReactNode;
  compact?: boolean;
}) {
  const isEmpty = !value;
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className={[
          "w-full appearance-none rounded-lg border pr-6 focus:outline-none focus:ring-1 focus:ring-ocean/30",
          "disabled:opacity-40 disabled:cursor-not-allowed",
          compact ? "px-2 py-1.5 text-[11px]" : "px-3 py-2 text-sm",
          isEmpty
            ? "border-ocean-200 text-ocean/40 bg-ocean-50/40"
            : "border-ocean-200 text-ocean-800 bg-white",
        ].join(" ")}
      >
        {placeholder && <option value="">{placeholder}</option>}
        {children}
      </select>
      <ChevronDown
        size={10}
        className="pointer-events-none absolute right-1.5 top-1/2 -translate-y-1/2 text-ocean/40"
      />
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function recomputeWarnings(rows: BulkRow[], institutions: InstitutionOption[]): BulkRow[] {
  // Build set of inst/account/year/month keys seen so far to detect intra-batch dupes
  const seen = new Set<string>();
  return rows.map((r) => {
    const key = `${r.institution_slug}/${r.account_slug}/${r.year}/${r.month}`;
    const warnings = getRowWarnings(
      r.file.name,
      r.institution_slug,
      r.account_slug,
      r.year,
      r.month,
      institutions,
      seen,
    );
    if (r.institution_slug && r.account_slug && r.year && r.month) {
      seen.add(key);
    }
    return { ...r, warnings };
  });
}
