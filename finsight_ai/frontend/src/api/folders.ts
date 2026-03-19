import { api } from "./client";

export interface FolderSummary {
  folder_key: string;
  label: string;
  bucket: "investments" | "banking";
  institution_type: string;
  file_count: number;
  latest_file_date: string | null;
  latest_filename: string | null;
}

export interface RecentFile {
  filename: string;
  folder_label: string;
  institution_type: string;
  bucket: "investments" | "banking";
  modified_date: string;
  size_bytes: number;
}

export interface FolderScanResult {
  folders: FolderSummary[];
  total_files: number;
  investments_total: number;
  banking_total: number;
  recent_files: RecentFile[];
}

export const foldersApi = {
  scan: (recentLimit = 10): Promise<FolderScanResult> =>
    api.get<FolderScanResult>("/analytics/folders", { recent_limit: recentLimit }),
};
