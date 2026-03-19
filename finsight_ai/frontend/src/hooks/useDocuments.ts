/**
 * Documents hook — manages document list, upload, deletion, and status polling.
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { documentsApi } from "../api/documents";
import type { StatementDocument, DocumentUploadResponse, DeletionSummary } from "../types";
import toast from "react-hot-toast";

export function useDocuments(onProcessed?: () => void) {
  const [documents, setDocuments] = useState<StatementDocument[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);

  // Track docs being polled for status
  const pollingRef = useRef<Record<string, ReturnType<typeof setInterval>>>({});
  // Store the callback ref so polling closure sees latest value
  const onProcessedRef = useRef(onProcessed);
  onProcessedRef.current = onProcessed;

  const fetchDocuments = useCallback(async () => {
    setIsLoading(true);
    try {
      const docs = await documentsApi.list();
      setDocuments(docs);
    } catch {
      // silently fail on background refresh
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDocuments();
    return () => {
      Object.values(pollingRef.current).forEach(clearInterval);
    };
  }, [fetchDocuments]);

  const pollDocumentStatus = useCallback(
    (documentId: string) => {
      const interval = setInterval(async () => {
        try {
          const status = await documentsApi.getStatus(documentId);
          setDocuments((prev) =>
            prev.map((doc) =>
              doc.id === documentId
                ? { ...doc, document_status: status.status as any, institution_type: (status as any).institution_type ?? doc.institution_type }
                : doc
            )
          );
          if (status.status === "processed" || status.status === "failed") {
            clearInterval(pollingRef.current[documentId]);
            delete pollingRef.current[documentId];
            if (status.status === "processed") {
              toast.success("Statement processed successfully!");
              // Trigger analytics refresh callback
              onProcessedRef.current?.();
            } else {
              toast.error(`Processing failed: ${status.error_message || "Unknown error"}`);
            }
          }
        } catch {
          clearInterval(pollingRef.current[documentId]);
          delete pollingRef.current[documentId];
        }
      }, 3000);
      pollingRef.current[documentId] = interval;
    },
    []
  );

  const uploadDocument = useCallback(
    async (file: File): Promise<DocumentUploadResponse | null> => {
      setIsUploading(true);
      try {
        const response = await documentsApi.upload(file);
        toast.success(`"${file.name}" uploaded. Processing in background...`);

        // Optimistically add to list
        setDocuments((prev) => [
          {
            id: response.document_id,
            original_filename: response.original_filename,
            institution_type: "unknown",
            document_status: "queued",
            page_count: null,
            upload_timestamp: new Date().toISOString(),
            processed_timestamp: null,
            error_message: null,
          },
          ...prev,
        ]);

        // Start polling for status
        pollDocumentStatus(response.document_id);
        return response;
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Upload failed";
        toast.error(msg);
        return null;
      } finally {
        setIsUploading(false);
      }
    },
    [pollDocumentStatus]
  );

  const deleteDocument = useCallback(
    async (documentId: string): Promise<DeletionSummary | null> => {
      try {
        const result = await documentsApi.delete(documentId);
        setDocuments((prev) => prev.filter((d) => d.id !== documentId));
        toast.success("Document deleted.");
        // Trigger analytics refresh
        onProcessedRef.current?.();
        return result;
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Delete failed";
        toast.error(msg);
        return null;
      }
    },
    []
  );

  return { documents, isLoading, isUploading, uploadDocument, deleteDocument, fetchDocuments };
}
