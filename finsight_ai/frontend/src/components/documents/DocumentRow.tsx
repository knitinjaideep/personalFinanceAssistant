import {
  FileText,
  CheckCircle,
  AlertCircle,
  Clock,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { clsx } from "clsx";
import type { DocumentSummary } from "../../types";
import { INSTITUTION_LABELS, INSTITUTION_COLORS } from "../../design/tokens";

const STATUS_CONFIG: Record<
  string,
  { icon: React.ReactNode; color: string; bg: string; label: string }
> = {
  uploaded: {
    icon: <Clock size={12} />,
    color: "text-ocean-DEFAULT/60",
    bg: "bg-ocean-50",
    label: "Uploaded",
  },
  processing: {
    icon: <RefreshCw size={12} className="animate-spin" />,
    color: "text-ocean",
    bg: "bg-ocean-50",
    label: "Processing",
  },
  parsed: {
    icon: <CheckCircle size={12} />,
    color: "text-positive",
    bg: "bg-positive/10",
    label: "Parsed",
  },
  failed: {
    icon: <AlertCircle size={12} />,
    color: "text-negative",
    bg: "bg-negative/10",
    label: "Failed",
  },
};

interface DocumentRowProps {
  doc: DocumentSummary;
  onDelete: (id: string, filename: string) => void;
}

export function DocumentRow({ doc, onDelete }: DocumentRowProps) {
  const cfg = STATUS_CONFIG[doc.status] || STATUS_CONFIG.uploaded;
  const instColor =
    INSTITUTION_COLORS[doc.institution] ||
    "bg-gray-50 text-gray-500 border-gray-200";

  return (
    <div className="flex items-center gap-4 px-5 py-3.5 hover:bg-ocean-50/40 transition-colors group">
      {/* File icon */}
      <div className="shrink-0 w-8 h-8 rounded-xl bg-ocean-50 flex items-center justify-center text-ocean">
        <FileText size={16} />
      </div>

      {/* Name + meta */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-slate truncate">{doc.filename}</p>
        <div className="flex items-center gap-2 mt-0.5 flex-wrap">
          <span
            className={clsx(
              "px-2 py-0.5 rounded-full text-xs font-medium border",
              instColor
            )}
          >
            {INSTITUTION_LABELS[doc.institution] || doc.institution}
          </span>
          {doc.page_count != null && (
            <span className="text-xs text-ocean-DEFAULT/40">
              {doc.page_count} pg
            </span>
          )}
          {doc.statement_count > 0 && (
            <span className="text-xs text-ocean-DEFAULT/40">
              {doc.statement_count} stmt
            </span>
          )}
        </div>
      </div>

      {/* Status */}
      <div
        className={clsx(
          "flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium shrink-0",
          cfg.bg,
          cfg.color
        )}
      >
        {cfg.icon}
        {cfg.label}
      </div>

      {/* Error */}
      {doc.error && (
        <span
          className="text-xs text-negative max-w-32 truncate"
          title={doc.error}
        >
          {doc.error}
        </span>
      )}

      {/* Delete */}
      <button
        onClick={() => onDelete(doc.id, doc.filename)}
        className="text-ocean-DEFAULT/20 hover:text-negative transition-colors opacity-0 group-hover:opacity-100"
        title="Delete document"
      >
        <Trash2 size={15} />
      </button>
    </div>
  );
}
