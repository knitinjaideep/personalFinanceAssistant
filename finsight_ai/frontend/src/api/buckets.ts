/**
 * Buckets API client.
 */

import { api } from "./client";
import type {
  Bucket,
  BucketCreateRequest,
  BucketWithDocuments,
  DeletionSummary,
  StatementDocument,
} from "../types";

export const bucketsApi = {
  list: (): Promise<Bucket[]> => api.get<Bucket[]>("/buckets/"),

  grouped: (): Promise<BucketWithDocuments[]> =>
    api.get<BucketWithDocuments[]>("/buckets/grouped"),

  get: (bucketId: string): Promise<Bucket> =>
    api.get<Bucket>(`/buckets/${bucketId}`),

  create: (request: BucketCreateRequest): Promise<Bucket> =>
    api.post<Bucket>("/buckets/", request),

  delete: (bucketId: string): Promise<{ deleted: boolean; bucket_id: string }> =>
    api.delete<{ deleted: boolean; bucket_id: string }>(`/buckets/${bucketId}`),

  assignDocument: (bucketId: string, documentId: string): Promise<Bucket> =>
    api.post<Bucket>(`/buckets/${bucketId}/documents/${documentId}`, {}),

  unassignDocument: (
    bucketId: string,
    documentId: string
  ): Promise<{ removed: boolean }> =>
    api.delete<{ removed: boolean }>(
      `/buckets/${bucketId}/documents/${documentId}`
    ),

  listDocuments: (bucketId: string): Promise<StatementDocument[]> =>
    api.get<StatementDocument[]>(`/buckets/${bucketId}/documents`),
};
