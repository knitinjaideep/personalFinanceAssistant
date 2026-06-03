import { useState } from "react";
import {
  FileText,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  RefreshCw,
  Trash2,
  AlertTriangle,
} from "lucide-react";
import toast from "react-hot-toast";
import type { DocumentIssue, DocumentStatus, DocumentSummary } from "../../types";
import { documentsApi } from "../../api/documents";
import {
  STATUS_LABELS,
  normalizeStatus,
  inferInstitution,
  institutionLabel,
  inferAccount,
  periodLabel,
  issueLabel,
} from "../../utils/documentUtils";

const STATUS_CONFIG: Record<DocumentStatus, { icon: React.ReactNode; color: string }> = {
  parsed:     { icon: <CheckCircle2 size={12} />, color: "#4CAF93" },
  processing: { icon: <Loader2 size={12} className="animate-spin" />, color: "#22d3ee" },
  uploaded:   { icon: <Clock size={12} />, color: "#c89a00" },
  failed:     { icon: <XCircle size={12} />, color: "#E45757" },
};

interface Props {
  doc: DocumentSummary;
  onChanged: () => void;
  issue?: DocumentIssue;
}

export function DocumentRow({ doc, onChanged, issue }: Props) {
  const status = normalizeStatus(doc.status);
  const cfg = STATUS_CONFIG[status];
  const [deleting, setDeleting] = useState(false);
  const [reprocessing, setReprocessing] = useState(false);
  const [showIssues, setShowIssues] = useState(false);

  const instLabel = institutionLabel(inferInstitution(doc));
  const account = inferAccount(doc);
  const period = periodLabel(doc);

  const incomplete = status === "parsed" && !!issue && issue.issues.length > 0;

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

  const handleReprocess = async () => {
    setReprocessing(true);
    try {
      const res = await documentsApi.reprocess(doc.id);
      if (res.ok) {
        toast.success(`Reprocessed: ${res.transactions} txns, ${res.chunks} chunks`);
      } else {
        toast.error(res.error || "Reprocess failed");
      }
      onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Reprocess failed");
    } finally {
      setReprocessing(false);
    }
  };

  return (
    <div
      className="flex items-center justify-between pl-12 pr-4 py-2.5 transition-colors group"
      style={{ borderTop: "1px solid rgba(34,211,238,0.07)" }}
      onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(34,211,238,0.04)")}
      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
    >
      <div className="flex items-center gap-3 min-w-0">
        <div
          className="p-1.5 rounded-lg shrink-0"
          style={{ background: "rgba(34,211,238,0.10)", color: "rgba(34,211,238,0.70)" }}
        >
          <FileText size={13} />
        </div>
        <div className="min-w-0">
          <p className="text-[12.5px] font-medium text-white truncate">{doc.filename}</p>
          <p className="text-[10px] mt-0.5 flex items-center gap-1.5 flex-wrap" style={{ color: "rgba(255,255,255,0.38)" }}>
            <span>{instLabel}</span>
            <span style={{ color: "rgba(255,255,255,0.18)" }}>·</span>
            <span>{account}</span>
            {period !== "—" && (
              <>
                <span style={{ color: "rgba(255,255,255,0.18)" }}>·</span>
                <span>{period}</span>
              </>
            )}
            {doc.page_count != null && (
              <>
                <span style={{ color: "rgba(255,255,255,0.18)" }}>·</span>
                <span>{doc.page_count}p</span>
              </>
            )}
            {doc.statement_count > 0 && (
              <>
                <span style={{ color: "rgba(255,255,255,0.18)" }}>·</span>
                <span>{doc.statement_count} stmt</span>
              </>
            )}
            {doc.upload_time && (
              <>
                <span style={{ color: "rgba(255,255,255,0.18)" }}>·</span>
                <span>{new Date(doc.upload_time).toLocaleDateString()}</span>
              </>
            )}
          </p>
          {status === "failed" && doc.error && (
            <p className="text-[10px] mt-0.5 truncate" style={{ color: "rgba(228,87,87,0.75)" }} title={doc.error}>
              {doc.error}
            </p>
          )}
          {incomplete && showIssues && (
            <div className="flex flex-wrap gap-1 mt-1">
              {issue!.issues.map((iss) => (
                <span
                  key={iss}
                  className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                  style={{ background: "rgba(228,87,87,0.12)", color: "#E45757" }}
                >
                  {issueLabel(iss)}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0 ml-4">
        {incomplete && (
          <button
            onClick={() => setShowIssues((v) => !v)}
            className="flex items-center gap-1 text-[10px] font-semibold px-2 py-1 rounded-full"
            style={{ background: "rgba(255,209,102,0.14)", color: "#c89a00" }}
            title="Parsed but incomplete — click for details"
          >
            <AlertTriangle size={11} />
            Incomplete
          </button>
        )}

        <span
          className="flex items-center gap-1 text-[10px] font-semibold px-2 py-1 rounded-full"
          style={{ background: `${cfg.color}1a`, color: cfg.color }}
        >
          {cfg.icon}
          {STATUS_LABELS[status]}
        </span>

        {(status === "failed" || incomplete) && (
          <button
            onClick={handleReprocess}
            disabled={reprocessing}
            className="p-1.5 rounded-lg transition-colors disabled:opacity-40"
            style={{ color: "rgba(34,211,238,0.45)" }}
            onMouseEnter={(e) => (e.currentTarget.style.color = "rgba(34,211,238,0.85)")}
            onMouseLeave={(e) => (e.currentTarget.style.color = "rgba(34,211,238,0.45)")}
            title="Reprocess this document"
          >
            {reprocessing ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
          </button>
        )}
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="p-1.5 rounded-lg transition-colors disabled:opacity-40 opacity-0 group-hover:opacity-100"
          style={{ color: "rgba(255,255,255,0.28)" }}
          onMouseEnter={(e) => (e.currentTarget.style.color = "rgba(228,87,87,0.80)")}
          onMouseLeave={(e) => (e.currentTarget.style.color = "rgba(255,255,255,0.28)")}
          title="Delete"
        >
          {deleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
        </button>
      </div>
    </div>
  );
}
