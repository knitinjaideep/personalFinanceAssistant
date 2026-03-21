import { api } from "./client";

export interface SourceSummary {
  source_id: string;
  institution_type: string;
  account_product: string;
  bucket: "investments" | "banking";
  root_path: string;
  total_files: number;
  ingested: number;
  pending: number;
  failed: number;
  no_parser: number;
  latest_file_date: string | null;
}

export interface ScanStatusResponse {
  sources: SourceSummary[];
  total_discovered: number;
  total_ingested: number;
  total_pending: number;
  total_failed: number;
  total_no_parser: number;
  scanned_at: string;
}

export interface IngestResultResponse {
  ingested: number;
  skipped: number;
  failed: number;
  no_parser: number;
  errors: string[];
  scan: ScanStatusResponse;
}

export const scanApi = {
  status: (): Promise<ScanStatusResponse> =>
    api.get<ScanStatusResponse>("/scan/status"),

  ingest: (): Promise<IngestResultResponse> =>
    api.post<IngestResultResponse>("/scan/ingest", {}),
};
