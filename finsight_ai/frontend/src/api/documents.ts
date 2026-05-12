import { api } from "./client";
import type { DocumentSummary, DocumentUploadResponse } from "../types";

export const documentsApi = {
  upload: (file: File, sourceId?: string, year?: number): Promise<DocumentUploadResponse> => {
    const formData = new FormData();
    formData.append("file", file);
    if (sourceId) formData.append("source_id", sourceId);
    if (year) formData.append("year", String(year));
    return api.uploadForm<DocumentUploadResponse>("/documents/upload", formData);
  },

  list: (limit = 50): Promise<DocumentSummary[]> =>
    api.get<DocumentSummary[]>("/documents/", { limit }),

  get: (documentId: string): Promise<DocumentSummary> =>
    api.get<DocumentSummary>(`/documents/${documentId}`),

  delete: (documentId: string): Promise<{ status: string; document_id: string }> =>
    api.delete<{ status: string; document_id: string }>(`/documents/${documentId}`),

  reingest: (documentId: string): Promise<{ status: string; document_id: string }> =>
    api.post<{ status: string; document_id: string }>(`/documents/${documentId}/reingest`, {}),

  listSources: () =>
    api.get<Array<{
      source_id: string;
      account_product: string;
      bucket: string;
      institution_type: string;
      root_path: string;
    }>>("/documents/sources/list"),
};
