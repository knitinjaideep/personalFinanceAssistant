import { api } from "./client";
import type { DeletionSummary, DocumentUploadResponse, StatementDocument } from "../types";

export const documentsApi = {
  upload: (file: File): Promise<DocumentUploadResponse> =>
    api.upload<DocumentUploadResponse>("/documents/upload", file),

  list: (limit = 50): Promise<StatementDocument[]> =>
    api.get<StatementDocument[]>("/documents/", { limit }),

  getStatus: (documentId: string) =>
    api.get<{
      document_id: string;
      status: string;
      institution_type: string;
      page_count: number | null;
      error_message: string | null;
    }>(`/documents/${documentId}/status`),

  delete: (documentId: string): Promise<DeletionSummary> =>
    api.delete<DeletionSummary>(`/documents/${documentId}`),
};
