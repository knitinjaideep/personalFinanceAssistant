/**
 * DocumentUpload — extended upload screen with bucket assignment,
 * grouped document list, delete support, and live processing event panel.
 */

import React, { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import {
  UploadCloud,
  File,
  CheckCircle,
  XCircle,
  Loader2,
  Trash2,
  AlertTriangle,
  FolderOpen,
} from "lucide-react";
import { clsx } from "clsx";
import toast from "react-hot-toast";

import { useDocuments } from "../../hooks/useDocuments";
import { useBuckets } from "../../hooks/useBuckets";
import { useEventStream } from "../../hooks/useEventStream";
import { bucketsApi } from "../../api/buckets";
import { documentsApi } from "../../api/documents";
import { BucketSelector } from "./BucketSelector";
import { EventStreamPanel } from "./EventStreamPanel";
import type { BucketWithDocuments, StatementDocument } from "../../types";

// ── Status config ─────────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<
  string,
  { label: string; color: string; icon: React.ReactNode }
> = {
  uploaded:        { label: "Uploaded",         color: "text-gray-500",   icon: <Loader2 size={13} className="animate-spin" /> },
  queued:          { label: "Queued",            color: "text-yellow-600", icon: <Loader2 size={13} className="animate-spin" /> },
  processing:      { label: "Processing…",       color: "text-blue-600",   icon: <Loader2 size={13} className="animate-spin" /> },
  parsed:          { label: "Parsed",            color: "text-indigo-600", icon: <Loader2 size={13} className="animate-spin" /> },
  partially_parsed:{ label: "Partial",           color: "text-orange-500", icon: <AlertTriangle size={13} /> },
  embedded:        { label: "Embedded",          color: "text-teal-600",   icon: <Loader2 size={13} className="animate-spin" /> },
  processed:       { label: "Processed",         color: "text-green-600",  icon: <CheckCircle size={13} /> },
  failed:          { label: "Failed",            color: "text-red-600",    icon: <XCircle size={13} /> },
  deleted:         { label: "Deleted",           color: "text-gray-400",   icon: <XCircle size={13} /> },
};

// ── Document row ──────────────────────────────────────────────────────────────

interface DocumentRowProps {
  doc: StatementDocument;
  onDelete: (doc: StatementDocument) => void;
  isDeleting: boolean;
}

function DocumentRow({ doc, onDelete, isDeleting }: DocumentRowProps) {
  const cfg = STATUS_CONFIG[doc.document_status] ?? STATUS_CONFIG.uploaded;
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <div className="flex items-center justify-between py-2 px-3 rounded-lg bg-white border border-gray-100 group">
      <div className="flex items-center gap-2 min-w-0">
        <File size={13} className="text-gray-400 shrink-0" />
        <span className="text-sm text-gray-700 truncate">{doc.original_filename}</span>
        {doc.institution_type !== "unknown" && (
          <span className="text-xs px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 shrink-0">
            {doc.institution_type.replace("_", " ")}
          </span>
        )}
      </div>

      <div className="flex items-center gap-2 shrink-0 ml-2">
        <div className={clsx("flex items-center gap-1 text-xs", cfg.color)}>
          {cfg.icon}
          <span>{cfg.label}</span>
        </div>

        {/* Delete button */}
        {doc.document_status !== "deleted" && (
          confirmDelete ? (
            <div className="flex items-center gap-1">
              <button
                onClick={() => onDelete(doc)}
                disabled={isDeleting}
                className="text-xs text-red-600 hover:text-red-800 font-medium disabled:opacity-50"
              >
                {isDeleting ? <Loader2 size={11} className="animate-spin" /> : "Delete"}
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                className="text-xs text-gray-400 hover:text-gray-600"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => setConfirmDelete(true)}
              className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500 transition-all"
              title="Delete document"
            >
              <Trash2 size={13} />
            </button>
          )
        )}
      </div>
    </div>
  );
}

// ── Bucket group ──────────────────────────────────────────────────────────────

interface BucketGroupProps {
  group: BucketWithDocuments;
  onDelete: (doc: StatementDocument) => void;
  deletingId: string | null;
}

function BucketGroup({ group, onDelete, deletingId }: BucketGroupProps) {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2 mb-1">
        <span
          className="w-2.5 h-2.5 rounded-full"
          style={{ backgroundColor: group.color }}
        />
        <span className="text-sm font-medium text-gray-700">{group.name}</span>
        <span className="text-xs text-gray-400">{group.documents.length} doc{group.documents.length !== 1 ? "s" : ""}</span>
      </div>
      {group.documents.length === 0 ? (
        <p className="text-xs text-gray-400 pl-4 py-1">No documents yet.</p>
      ) : (
        <div className="space-y-1 pl-4">
          {group.documents.map((doc) => (
            <DocumentRow
              key={doc.id}
              doc={doc}
              onDelete={onDelete}
              isDeleting={deletingId === doc.id}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function DocumentUpload() {
  const { documents, isUploading, uploadDocument, fetchDocuments } = useDocuments();
  const { buckets, isCreating, createBucket, assignDocument } = useBuckets();
  const { events, isStreaming } = useEventStream();

  const [selectedBucketId, setSelectedBucketId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [groupedBuckets, setGroupedBuckets] = useState<BucketWithDocuments[]>([]);
  const [groupedLoading, setGroupedLoading] = useState(false);

  // Load grouped view
  const loadGrouped = useCallback(async () => {
    setGroupedLoading(true);
    try {
      const data = await bucketsApi.grouped();
      setGroupedBuckets(data);
    } catch {
      // fail silently
    } finally {
      setGroupedLoading(false);
    }
  }, []);

  // Load grouped data when buckets list is ready
  React.useEffect(() => {
    if (buckets.length > 0) loadGrouped();
  }, [buckets.length, loadGrouped]);

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      for (const file of acceptedFiles) {
        const response = await uploadDocument(file);
        if (response && selectedBucketId) {
          await assignDocument(selectedBucketId, response.document_id);
          await loadGrouped();
        }
      }
    },
    [uploadDocument, selectedBucketId, assignDocument, loadGrouped]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    multiple: true,
    disabled: isUploading,
  });

  const handleDelete = useCallback(
    async (doc: StatementDocument) => {
      setDeletingId(doc.id);
      try {
        await documentsApi.delete(doc.id);
        toast.success(`"${doc.original_filename}" deleted.`);
        await fetchDocuments();
        await loadGrouped();
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Delete failed";
        toast.error(msg);
      } finally {
        setDeletingId(null);
      }
    },
    [fetchDocuments, loadGrouped]
  );

  // Ungrouped docs — documents not in any visible bucket group
  const groupedDocIds = new Set(
    groupedBuckets.flatMap((g) => g.documents.map((d) => d.id))
  );
  const ungroupedDocs = documents.filter(
    (d) => !groupedDocIds.has(d.id) && d.document_status !== "deleted"
  );

  return (
    <div className="p-6 max-w-2xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-gray-900">Upload Statements</h1>
        <p className="text-sm text-gray-500 mt-1">
          Upload PDF financial statements from Morgan Stanley, Chase, or E*TRADE.
          Processing happens locally — your data never leaves this machine.
        </p>
      </div>

      {/* Bucket selector */}
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1.5">
          Assign to bucket (optional)
        </label>
        <BucketSelector
          buckets={buckets}
          selectedBucketId={selectedBucketId}
          onSelect={setSelectedBucketId}
          onCreateBucket={createBucket}
          isCreating={isCreating}
        />
      </div>

      {/* Drop zone */}
      <div
        {...getRootProps()}
        className={clsx(
          "border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors",
          isDragActive
            ? "border-blue-400 bg-blue-50"
            : "border-gray-300 hover:border-blue-300 hover:bg-gray-50",
          isUploading && "opacity-60 cursor-not-allowed"
        )}
      >
        <input {...getInputProps()} />
        <UploadCloud
          size={36}
          className={clsx("mx-auto mb-3", isDragActive ? "text-blue-500" : "text-gray-400")}
        />
        {isUploading ? (
          <p className="text-sm text-blue-600 font-medium">Uploading…</p>
        ) : isDragActive ? (
          <p className="text-sm text-blue-600 font-medium">Drop to upload</p>
        ) : (
          <>
            <p className="text-sm font-medium text-gray-700">
              Drag & drop PDFs here, or click to select
            </p>
            <p className="text-xs text-gray-400 mt-1">PDF only · Max 50 MB</p>
            {selectedBucketId && (
              <p className="text-xs text-blue-600 mt-2">
                Will be added to:{" "}
                <strong>
                  {buckets.find((b) => b.id === selectedBucketId)?.name}
                </strong>
              </p>
            )}
          </>
        )}
      </div>

      {/* Live processing events */}
      <EventStreamPanel events={events} isStreaming={isStreaming} />

      {/* Bucket-grouped documents */}
      {(groupedBuckets.length > 0 || ungroupedDocs.length > 0) && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <FolderOpen size={15} className="text-gray-400" />
            <h2 className="text-sm font-medium text-gray-700">Documents by Bucket</h2>
            {groupedLoading && <Loader2 size={13} className="text-gray-400 animate-spin" />}
          </div>

          {groupedBuckets.map((group) => (
            <BucketGroup
              key={group.id}
              group={group}
              onDelete={handleDelete}
              deletingId={deletingId}
            />
          ))}

          {/* Ungrouped documents */}
          {ungroupedDocs.length > 0 && (
            <div className="space-y-1">
              <div className="flex items-center gap-2 mb-1">
                <span className="w-2.5 h-2.5 rounded-full bg-gray-300" />
                <span className="text-sm font-medium text-gray-500">Unassigned</span>
                <span className="text-xs text-gray-400">{ungroupedDocs.length}</span>
              </div>
              <div className="space-y-1 pl-4">
                {ungroupedDocs.map((doc) => (
                  <DocumentRow
                    key={doc.id}
                    doc={doc}
                    onDelete={handleDelete}
                    isDeleting={deletingId === doc.id}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
