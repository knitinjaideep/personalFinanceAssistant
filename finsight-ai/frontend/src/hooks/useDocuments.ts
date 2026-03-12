/**
 * Documents hook — manages document list and upload with status polling.
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { documentsApi } from "../api/documents";
import type { StatementDocument, DocumentUploadResponse } from "../types";
import toast from "react-hot-toast";

export function useDocuments() {
  const [documents, setDocuments] = useState<StatementDocument[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);

  // Track docs being polled for status
  const pollingRef = useRef<Record<string, ReturnType<typeof setInterval>>>({});

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
      // Cleanup all polling intervals on unmount
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
                ? { ...doc, document_status: status.status as any }
                : doc
            )
          );
          if (status.status === "processed" || status.status === "failed") {
            clearInterval(pollingRef.current[documentId]);
            delete pollingRef.current[documentId];
            if (status.status === "processed") {
              toast.success("Statement processed successfully!");
            } else {
              toast.error(`Processing failed: ${status.error_message || "Unknown error"}`);
            }
          }
        } catch {
          clearInterval(pollingRef.current[documentId]);
          delete pollingRef.current[documentId];
        }
      }, 3000); // poll every 3 seconds
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

  return { documents, isLoading, isUploading, uploadDocument, fetchDocuments };
}
