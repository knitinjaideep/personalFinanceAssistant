import { useState } from "react";
import {
  FileText,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  RefreshCw,
  Trash2,
} from "lucide-react";
import toast from "react-hot-toast";
import type { DocumentStatus, DocumentSummary } from "../../types";
import { documentsApi } from "../../api/documents";
import {
  STATUS_LABELS,
  normalizeStatus,
  inferInstitution,
  institutionLabel,
  inferAccount,
  periodLabel,
} from "../../utils/documentUtils";

const STATUS_CONFIG: Record<DocumentStatus, { icon: React.ReactNode; color: string }> = {
  parsed: { icon: <CheckCircle2 size={12} />, color: "#4CAF93" },
  processing: { icon: <Loader2 size={12} className="animate-spin" />, color: "#1F6F8B" },
  uploaded: { icon: <Clock size={12} />, color: "#c89a00" },
  failed: { icon: <XCircle size={12} />, color: "#E45757" },
};

interface Props {
  doc: DocumentSummary;
  /** Called after a successful delete or reingest so the parent can refetch. */
  onChanged: () => void;
}

export function DocumentRow({ doc, onChanged }: Props) {
  const status = normalizeStatus(doc.status);
  const cfg = STATUS_CONFIG[status];
  const [deleting, setDeleting] = useState(false);
  const [reingesting, setReingesting] = useState(false);

  const instLabel = institutionLabel(inferInstitution(doc));
  const account = inferAccount(doc);
  const period = periodLabel(doc);

  const handleDelete = async () => {
    if (!confirm(`Delete "${doc.filename}"? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      await documentsApi.delete(doc.id);
      toast.success("Document deleted");
      onChanged();
    } catch {
      toast.error("Failed to delete");
      setDeleting(false);
    }
  };

  const handleReingest = async () => {
    setReingesting(true);
    try {
      await documentsApi.reingest(doc.id);
      toast.success("Re-ingestion started");
      onChanged();
    } catch {
      toast.error("Re-ingest failed");
    } finally {
      setReingesting(false);
    }
  };

  return (
    <div className="flex items-center justify-between pl-12 pr-4 py-2.5 border-t border-ocean-50/40 hover:bg-ocean-50/25 transition-colors group">
      <div className="flex items-center gap-3 min-w-0">
        <div
          className="p-1.5 rounded-lg shrink-0"
          style={{ background: "rgba(31,111,139,0.08)", color: "#1F6F8B" }}
        >
          <FileText size={13} />
        </div>
        <div className="min-w-0">
          <p className="text-[12.5px] font-medium text-ocean-deep truncate">{doc.filename}</p>
          <p className="text-[10px] text-ocean/45 mt-0.5 flex items-center gap-1.5 flex-wrap">
            <span>{instLabel}</span>
            <span className="text-ocean/20">·</span>
            <span>{account}</span>
            {period !== "—" && (
              <>
                <span className="text-ocean/20">·</span>
                <span>{period}</span>
              </>
            )}
            {doc.page_count != null && (
              <>
                <span className="text-ocean/20">·</span>
                <span>{doc.page_count}p</span>
              </>
            )}
            {doc.statement_count > 0 && (
              <>
                <span className="text-ocean/20">·</span>
                <span>{doc.statement_count} stmt</span>
              </>
            )}
            {doc.upload_time && (
              <>
                <span className="text-ocean/20">·</span>
                <span>{new Date(doc.upload_time).toLocaleDateString()}</span>
              </>
            )}
          </p>
          {status === "failed" && doc.error && (
            <p className="text-[10px] text-negative/70 mt-0.5 truncate" title={doc.error}>
              {doc.error}
            </p>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0 ml-4">
        <span
          className="flex items-center gap-1 text-[10px] font-semibold px-2 py-1 rounded-full"
          style={{ background: `${cfg.color}14`, color: cfg.color }}
        >
          {cfg.icon}
          {STATUS_LABELS[status]}
        </span>

        {status === "failed" && (
          <button
            onClick={handleReingest}
            disabled={reingesting}
            className="p-1.5 rounded-lg text-ocean/35 hover:text-ocean transition-colors disabled:opacity-40"
            title="Re-ingest"
          >
            {reingesting ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
          </button>
        )}
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="p-1.5 rounded-lg text-ocean/25 hover:text-negative/70 transition-colors disabled:opacity-40 opacity-0 group-hover:opacity-100"
          title="Delete"
        >
          {deleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
        </button>
      </div>
    </div>
  );
}
