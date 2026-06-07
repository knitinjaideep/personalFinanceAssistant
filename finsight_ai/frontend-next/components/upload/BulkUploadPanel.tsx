"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { useDropzone } from "react-dropzone";
import {
  Upload, Loader2, CheckCircle2, AlertCircle, FileText,
  ChevronDown, FolderOpen, Layers, AlertTriangle, X, SkipForward,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import toast from "react-hot-toast";
import { catalogApi } from "@/features/upload/api";
import type { InstitutionOption, MonthOption } from "@/features/upload/api";
import { useAppStore } from "@/store/appStore";
import {
  detectFromFilename,
  getRowWarnings,
  type RowWarning,
} from "./filenameDetection";

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

interface BulkUploadPanelProps {
  onUploaded?: () => void;
}

const CURRENT_YEAR = new Date().getFullYear();
const YEAR_OPTIONS = [CURRENT_YEAR, CURRENT_YEAR - 1, CURRENT_YEAR - 2, CURRENT_YEAR - 3];

function nanoid() {
  return Math.random().toString(36).slice(2, 10);
}

function RowStatusIcon({ outcome }: { outcome: UploadOutcome | "pending" | "uploading" }) {
  if (outcome === "uploading") return <Loader2 size={13} className="animate-spin shrink-0" style={{ color: "var(--text-muted)" }} />;
  if (outcome === "saved") return <CheckCircle2 size={13} className="text-emerald-500 shrink-0" />;
  if (outcome === "duplicate_skipped") return <SkipForward size={13} className="text-amber-400 shrink-0" />;
  if (outcome === "failed") return <AlertCircle size={13} className="shrink-0" style={{ color: "#FF7A5A" }} />;
  return <span className="w-3 h-3 rounded-full shrink-0 inline-block" style={{ background: "var(--border-subtle)" }} />;
}

function MiniSelect({
  value, onChange, disabled, placeholder, children, compact,
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
          "w-full appearance-none rounded-lg border pr-6 focus:outline-none focus:ring-1",
          "disabled:opacity-40 disabled:cursor-not-allowed",
          compact ? "px-2 py-1.5 text-[11px]" : "px-3 py-2 text-sm",
        ].join(" ")}
        style={{
          background: isEmpty ? "var(--panel-bg)" : "var(--panel-bg-alt)",
          borderColor: isEmpty ? "var(--border-subtle)" : "var(--border-accent)",
          color: isEmpty ? "var(--text-muted)" : "var(--text-primary)",
        }}
      >
        {placeholder && <option value="">{placeholder}</option>}
        {children}
      </select>
      <ChevronDown size={10} className="pointer-events-none absolute right-1.5 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }} />
    </div>
  );
}

function recomputeWarnings(rows: BulkRow[], institutions: InstitutionOption[]): BulkRow[] {
  const seen = new Set<string>();
  return rows.map((r) => {
    const key = `${r.institution_slug}/${r.account_slug}/${r.year}/${r.month}`;
    const warnings = getRowWarnings(
      r.file.name, r.institution_slug, r.account_slug, r.year, r.month, institutions, seen,
    );
    if (r.institution_slug && r.account_slug && r.year && r.month) seen.add(key);
    return { ...r, warnings };
  });
}

function ReviewRow({
  row, institutions, months, onUpdate, onRemove,
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

  const warningText = row.warnings.map((w) => w.message).join(" · ");

  return (
    <div
      className="grid items-center gap-2.5 px-4 py-3"
      style={{
        gridTemplateColumns: BULK_GRID,
        background: hasWarning ? "var(--warn-bg)" : undefined,
      }}
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <FileText size={13} style={{ color: "var(--text-muted)" }} className="shrink-0" />
          <span className="text-[13px] font-medium truncate" style={{ color: "var(--text-primary)" }} title={row.file.name}>
            {row.file.name}
          </span>
          {row.detection_confidence === "high" && (
            <span className="text-[10px] px-1.5 py-0.5 rounded font-semibold shrink-0" style={{ background: "var(--success-soft)", color: "var(--success-text)" }}>auto</span>
          )}
          {row.detection_confidence === "low" && (
            <span className="text-[10px] px-1.5 py-0.5 rounded font-semibold shrink-0" style={{ background: "var(--warn-bg)", color: "var(--warn-text)" }}>partial</span>
          )}
        </div>
        {warningText && (
          <div className="flex items-center gap-1 mt-1" title={warningText}>
            <AlertTriangle size={10} className="shrink-0" style={{ color: "var(--warn-text)" }} />
            <span className="text-[10.5px] truncate" style={{ color: "var(--warn-text)" }}>{warningText}</span>
          </div>
        )}
      </div>

      <MiniSelect value={row.institution_slug} onChange={(v) => onUpdate({ institution_slug: v, account_slug: "" })} placeholder="Institution" compact>
        {institutions.map((i) => <option key={i.institution_slug} value={i.institution_slug}>{i.institution_label}</option>)}
      </MiniSelect>

      <MiniSelect value={row.account_slug} onChange={(v) => onUpdate({ account_slug: v })} disabled={!row.institution_slug} placeholder="Account" compact>
        {acctOptions.map((a) => <option key={a.account_slug} value={a.account_slug}>{a.account_label}</option>)}
      </MiniSelect>

      <MiniSelect value={row.year ? String(row.year) : ""} onChange={(v) => onUpdate({ year: v ? Number(v) : null })} placeholder="Year" compact>
        {yearOptions.map((y) => <option key={y} value={y}>{y}</option>)}
      </MiniSelect>

      <MiniSelect value={row.month ? String(row.month) : ""} onChange={(v) => onUpdate({ month: v ? Number(v) : null })} placeholder="Month" compact>
        {months.map((m) => <option key={m.month} value={m.month}>{m.label}</option>)}
      </MiniSelect>

      <button onClick={onRemove} className="transition-colors hover:scale-110 flex items-center justify-center" style={{ color: "var(--text-dim)" }} title="Remove">
        <X size={14} />
      </button>
    </div>
  );
}

// Shared column template for the bulk review table. Generous min widths keep
// every column readable; the table scrolls horizontally on narrow viewports.
const BULK_GRID = "minmax(220px, 2fr) minmax(150px, 1fr) minmax(150px, 1fr) 84px 120px 24px";

function SummaryChip({ label, value, positive }: { label: string; value: number; positive?: boolean }) {
  return (
    <div
      className="rounded-xl border px-3 py-2 text-center"
      style={{
        background: value > 0 && positive ? "rgba(61,184,134,0.10)" : "var(--panel-bg)",
        borderColor: "var(--border-subtle)",
      }}
    >
      <p className="text-lg font-bold tabular-nums" style={{ color: "var(--text-primary)" }}>{value}</p>
      <p className="text-[10px] font-medium leading-tight mt-0.5" style={{ color: "var(--text-muted)" }}>{label}</p>
    </div>
  );
}

export default function BulkUploadPanel({ onUploaded }: BulkUploadPanelProps) {
  const { addIngestionJob } = useAppStore();

  const [phase, setPhase] = useState<Phase>("pick");
  const [rows, setRows] = useState<BulkRow[]>([]);
  const [institutions, setInstitutions] = useState<InstitutionOption[]>([]);
  const [months, setMonths] = useState<MonthOption[]>([]);
  const [bulkInstitution, setBulkInstitution] = useState("");
  const [bulkAccount, setBulkAccount] = useState("");
  const [bulkYear, setBulkYear] = useState<number | "">("");
  const [rowStatuses, setRowStatuses] = useState<Map<string, UploadOutcome | "uploading" | "pending">>(new Map());
  const [summary, setSummary] = useState<BulkSummaryData | null>(null);

  useEffect(() => {
    catalogApi.institutions().then(setInstitutions).catch(() => {});
    catalogApi.months().then(setMonths).catch(() => {});
  }, []);

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

  const onDrop = useCallback((accepted: File[]) => { buildRows(accepted); }, [buildRows]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    multiple: true,
    disabled: phase !== "pick",
  });

  const folderInputRef = useRef<HTMLInputElement>(null);
  function handleFolderInput(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    buildRows(files);
    if (folderInputRef.current) folderInputRef.current.value = "";
  }

  function updateRow(id: string, patch: Partial<Omit<BulkRow, "id" | "file">>) {
    setRows((prev) => {
      const updated = prev.map((r) => r.id === id ? { ...r, ...patch, detection_confidence: "manual" as const } : r);
      return recomputeWarnings(updated, institutions);
    });
  }

  function removeRow(id: string) {
    setRows((prev) => prev.filter((r) => r.id !== id));
  }

  const bulkInstOption = institutions.find((i) => i.institution_slug === bulkInstitution);
  const bulkAcctOptions = bulkInstOption?.accounts ?? [];

  function applyBulkInstitution() {
    if (!bulkInstitution) return;
    setRows((prev) => {
      const updated = prev.map((r) => ({
        ...r, institution_slug: bulkInstitution,
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

  const validRows = rows.filter((r) => r.warnings.every((w) => w.type !== "not_pdf"));
  const readyCount = validRows.filter((r) => r.institution_slug && r.account_slug && r.year && r.month).length;
  const canIngest = readyCount > 0;

  async function handleIngestAll() {
    if (!canIngest) return;
    setPhase("uploading");

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
      const res = await fetch("/api/v1/documents/bulk-upload-local", { method: "POST", body: form });
      const data: BulkSummaryData = await res.json();

      if (!res.ok) {
        toast.error("Bulk upload failed: " + ((data as { detail?: string }).detail || "Unknown error"));
        setPhase("review");
        return;
      }

      const nameToId = new Map(toUpload.map((r) => [r.file.name, r.id]));
      const finalStatuses = new Map(initialStatuses);

      for (const result of data.results) {
        const rowId = nameToId.get(result.filename);
        if (rowId) finalStatuses.set(rowId, result.outcome as UploadOutcome);
        if (result.outcome === "saved" && result.document_id) {
          addIngestionJob({ document_id: result.document_id, filename: result.filename, status: "processing", started_at: Date.now() });
        }
      }
      setRowStatuses(finalStatuses);
      setSummary(data);
      setPhase("done");
      onUploaded?.();

      const ok = data.uploaded;
      const dupes = data.duplicates_skipped;
      const errs = data.failed;
      if (ok > 0) toast.success(`${ok} file${ok > 1 ? "s" : ""} saved — parsing in background`);
      if (dupes > 0) toast(`${dupes} already ingested — skipped`, { icon: "ℹ️" });
      if (errs > 0) toast.error(`${errs} file${errs > 1 ? "s" : ""} failed`);
    } catch (err: unknown) {
      toast.error(`Network error: ${err instanceof Error ? err.message : "Unknown"}`);
      setPhase("review");
    }
  }

  return (
    <div>
      {/* Phase: pick */}
      {phase === "pick" && (
        <div className="space-y-3">
          <div
            {...(getRootProps() as React.HTMLAttributes<HTMLDivElement>)}
            className="rounded-2xl border-2 border-dashed p-10 text-center cursor-pointer transition-all"
            style={{ borderColor: isDragActive ? "#FF7A5A" : "var(--border-accent)", background: isDragActive ? "rgba(255,122,90,0.05)" : "var(--upload-bg)" }}
          >
            <input {...getInputProps()} />
            <Layers size={28} className="mx-auto mb-3" style={{ color: "var(--text-muted)" }} />
            <p className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
              {isDragActive ? "Drop here" : "Drop PDFs or a folder, or click to browse"}
            </p>
            <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>Multiple files OK · up to 50 MB each</p>
          </div>
          <div className="flex items-center justify-center gap-2">
            <div className="h-px flex-1" style={{ background: "var(--border-subtle)" }} />
            <span className="text-xs px-2" style={{ color: "var(--text-dim)" }}>or</span>
            <div className="h-px flex-1" style={{ background: "var(--border-subtle)" }} />
          </div>
          <label className="flex items-center justify-center gap-2 w-full rounded-xl border py-2.5 text-sm font-medium transition-colors cursor-pointer"
            style={{ borderColor: "var(--border-subtle)", color: "var(--text-secondary)" }}>
            <FolderOpen size={14} />
            Browse folder
            <input
              ref={folderInputRef}
              type="file"
              className="hidden"
              accept=".pdf"
              multiple
              // @ts-expect-error webkitdirectory not in TS types
              webkitdirectory=""
              onChange={handleFolderInput}
            />
          </label>
        </div>
      )}

      {/* Phase: review */}
      {phase === "review" && (
        <div className="space-y-4">
          <div className="rounded-2xl px-4 py-3 flex flex-wrap gap-2 items-end" style={{ background: "var(--panel-bg)", border: "1px solid var(--border-subtle)" }}>
            <span className="text-[11px] font-semibold uppercase tracking-wide w-full mb-0.5" style={{ color: "var(--text-muted)" }}>
              Bulk apply to all rows
            </span>
            <div className="flex gap-2 flex-wrap flex-1">
              <MiniSelect value={bulkInstitution} onChange={(v) => { setBulkInstitution(v); setBulkAccount(""); }} placeholder="Institution">
                {institutions.map((i) => <option key={i.institution_slug} value={i.institution_slug}>{i.institution_label}</option>)}
              </MiniSelect>
              <MiniSelect value={bulkAccount} onChange={setBulkAccount} disabled={!bulkInstitution} placeholder="Account">
                {bulkAcctOptions.map((a) => <option key={a.account_slug} value={a.account_slug}>{a.account_label}</option>)}
              </MiniSelect>
              <button onClick={applyBulkInstitution} disabled={!bulkInstitution}
                className="px-3 py-1.5 rounded-lg text-xs font-medium text-white disabled:opacity-40 transition-colors"
                style={{ background: "var(--accent-coral-grad)" }}>
                Apply institution
              </button>
            </div>
            <div className="flex gap-2 items-center">
              <MiniSelect value={String(bulkYear)} onChange={(v) => setBulkYear(v ? Number(v) : "")} placeholder="Year">
                {YEAR_OPTIONS.map((y) => <option key={y} value={y}>{y}</option>)}
              </MiniSelect>
              <button onClick={applyBulkYear} disabled={!bulkYear}
                className="px-3 py-1.5 rounded-lg text-xs font-medium text-white disabled:opacity-40 transition-colors"
                style={{ background: "var(--accent-coral-grad)" }}>
                Apply year
              </button>
            </div>
          </div>

          <div className="flex gap-3 text-[13px] items-center" style={{ color: "var(--text-muted)" }}>
            <span>{rows.length} file{rows.length !== 1 ? "s" : ""}</span>
            <span>·</span>
            <span className="font-semibold" style={{ color: "var(--success-text)" }}>{readyCount} ready</span>
            {rows.length - readyCount > 0 && (
              <><span>·</span><span className="font-semibold" style={{ color: "var(--warn-text)" }}>{rows.length - readyCount} need attention</span></>
            )}
          </div>

          {/* Scrollable table — generous columns, horizontal scroll on small screens */}
          <div className="rounded-2xl border overflow-hidden" style={{ borderColor: "var(--border-subtle)" }}>
            <div className="overflow-x-auto">
              <div style={{ minWidth: 720 }}>
                <div
                  className="grid text-[10.5px] font-semibold uppercase tracking-wide px-4 py-2.5 border-b"
                  style={{ gridTemplateColumns: BULK_GRID, borderColor: "var(--border-subtle)", color: "var(--text-muted)", background: "var(--panel-bg)" }}
                >
                  <span>File</span><span>Institution</span><span>Account</span><span>Year</span><span>Month</span><span />
                </div>
                <div className="divide-y max-h-[42vh] overflow-y-auto" style={{ borderColor: "var(--border-subtle)" }}>
                  {rows.map((row) => (
                    <ReviewRow key={row.id} row={row} institutions={institutions} months={months}
                      onUpdate={(patch) => updateRow(row.id, patch)} onRemove={() => removeRow(row.id)} />
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Sticky action footer */}
          <div
            className="sticky bottom-0 -mx-6 sm:-mx-8 -mb-6 px-6 sm:px-8 pt-4 pb-6 flex flex-col gap-2"
            style={{ background: "linear-gradient(to top, var(--modal-bg) 70%, transparent)" }}
          >
            {readyCount === 0 && (
              <p className="text-[12px] text-center" style={{ color: "var(--warn-text)" }}>
                Set an institution, account, year and month for at least one row to enable ingest.
              </p>
            )}
            <div className="flex gap-3">
              <button onClick={() => { setRows([]); setPhase("pick"); }}
                className="flex-1 rounded-xl border py-3 text-sm font-medium transition-colors"
                style={{ borderColor: "var(--border-accent)", color: "var(--text-secondary)" }}>
                Back
              </button>
              <button onClick={handleIngestAll} disabled={!canIngest}
                className="flex-1 rounded-xl py-3 text-sm font-semibold text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                style={{ background: canIngest ? "var(--accent-coral-grad)" : "var(--btn-glass-bg)" }}>
                <Upload size={14} /> Ingest {readyCount} file{readyCount !== 1 ? "s" : ""}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Phase: uploading */}
      {phase === "uploading" && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm" style={{ color: "var(--text-secondary)" }}>
            <Loader2 size={15} className="animate-spin" />
            Uploading {rows.length} file{rows.length !== 1 ? "s" : ""}…
          </div>
          <div className="rounded-xl border divide-y max-h-[50vh] overflow-y-auto" style={{ borderColor: "var(--border-subtle)" }}>
            {rows.map((row) => {
              const status = rowStatuses.get(row.id) ?? "uploading";
              return (
                <div key={row.id} className="flex items-center gap-2 px-3 py-2.5">
                  <RowStatusIcon outcome={status} />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs truncate" style={{ color: "var(--text-secondary)" }}>{row.file.name}</p>
                    <p className="text-[10px]" style={{ color: "var(--text-dim)" }}>{row.institution_slug} / {row.account_slug}</p>
                  </div>
                  <span className="text-[10px] tabular-nums" style={{ color: "var(--text-dim)" }}>
                    {(row.file.size / 1024 / 1024).toFixed(1)} MB
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Phase: done */}
      {phase === "done" && summary && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <SummaryChip label="Saved" value={summary.uploaded} positive />
            <SummaryChip label="Duplicates skipped" value={summary.duplicates_skipped} />
            <SummaryChip label="Failed" value={summary.failed} />
            <SummaryChip label="Partial parses" value={summary.partial_parses} />
          </div>
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>
            Ingestion runs in background — ask a question anytime.
          </p>
          <div className="rounded-xl border divide-y max-h-[40vh] overflow-y-auto" style={{ borderColor: "var(--border-subtle)" }}>
            {summary.results.map((r, i) => (
              <div key={i} className="flex items-center gap-2 px-3 py-2">
                <RowStatusIcon outcome={r.outcome} />
                <div className="flex-1 min-w-0">
                  <p className="text-xs truncate" style={{ color: "var(--text-secondary)" }}>{r.filename}</p>
                  {r.outcome === "duplicate_skipped" && <p className="text-[10px] text-amber-400">Already ingested — skipped</p>}
                  {r.outcome === "failed" && r.error_message && <p className="text-[10px] truncate" style={{ color: "#FF7A5A" }}>{r.error_message}</p>}
                </div>
              </div>
            ))}
          </div>
          <button onClick={() => { setPhase("pick"); setRows([]); setSummary(null); }}
            className="w-full rounded-xl border py-2.5 text-sm font-medium transition-colors"
            style={{ borderColor: "var(--border-accent)", color: "var(--text-secondary)" }}>
            Upload more
          </button>
        </div>
      )}
    </div>
  );
}
