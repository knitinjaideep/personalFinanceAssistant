/**
 * Shared TypeScript types mirroring backend Pydantic schemas.
 */

export type DocumentStatus =
  | "uploaded"
  | "queued"
  | "processing"
  | "parsed"
  | "partially_parsed"
  | "embedded"
  | "processed"
  | "failed"
  | "deleted";

export type ExtractionStatus =
  | "pending"
  | "processing"
  | "success"
  | "partial"
  | "failed";

export type InstitutionType =
  | "morgan_stanley"
  | "chase"
  | "etrade"
  | "unknown";

export interface StatementDocument {
  id: string;
  original_filename: string;
  institution_type: InstitutionType;
  document_status: DocumentStatus;
  page_count: number | null;
  upload_timestamp: string;
  processed_timestamp: string | null;
  error_message: string | null;
}

export interface DocumentUploadResponse {
  document_id: string;
  original_filename: string;
  file_size_bytes: number;
  status: DocumentStatus;
  message: string;
}

export interface Statement {
  id: string;
  institution_id: string;
  account_id: string;
  statement_type: string;
  period_start: string;
  period_end: string;
  extraction_status: ExtractionStatus;
  overall_confidence: number;
  created_at: string;
}

export interface Fee {
  id: string;
  fee_date: string;
  description: string;
  amount: string;
  fee_category: string | null;
  confidence: number;
}

export interface Holding {
  id: string;
  symbol: string | null;
  description: string;
  quantity: string | null;
  price: string | null;
  market_value: string;
  asset_class: string | null;
  confidence: number;
}

export interface BalancePoint {
  account_id: string;
  account: string;
  institution: string;
  date: string;
  total_value: string;
}

export interface FeeSummary {
  institution: string;
  account: string;
  total_fees: string;
  fee_count: number;
  categories: Record<string, string>;
}

export interface FeeAnalyticsResponse {
  period: { start: string; end: string };
  institution_filter: string | null;
  total_fees: string;
  summaries: FeeSummary[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
}

export interface ChatRequest {
  question: string;
  conversation_history: ChatMessage[];
}

export interface EmbeddingSource {
  id: string;
  document_id: string;
  chunk_index: number;
  chunk_text: string;
  page_number: number | null;
  section: string | null;
  institution_type: InstitutionType | null;
  statement_period: string | null;
}

export interface ChatResponse {
  answer: string;
  sources: EmbeddingSource[];
  sql_query_used: string | null;
  processing_time_seconds: number | null;
}

export interface MissingStatement {
  institution: string;
  account: string;
  year: number;
  missing_months: number[];
  missing_month_names: string[];
}

// ── Bucket types ──────────────────────────────────────────────────────────────

export type BucketStatus = "active" | "archived" | "deleted";

export interface Bucket {
  id: string;
  name: string;
  description: string | null;
  institution_type: InstitutionType | null;
  status: BucketStatus;
  color: string;
  icon: string | null;
  document_count: number;
  created_at: string;
  updated_at: string;
}

export interface BucketWithDocuments extends Bucket {
  documents: StatementDocument[];
}

export interface BucketCreateRequest {
  name: string;
  description?: string;
  institution_type?: InstitutionType;
  color?: string;
  icon?: string;
}

// ── Processing event types ────────────────────────────────────────────────────

export type ProcessingEventStatus =
  | "started"
  | "in_progress"
  | "complete"
  | "failed"
  | "warning";

export interface ProcessingEvent {
  session_id: string;
  event_type: string;
  status: ProcessingEventStatus;
  agent_name: string;
  step_name: string;
  message: string;
  bucket_id?: string;
  bucket_name?: string;
  document_id?: string;
  document_name?: string;
  progress?: number;
  metadata?: Record<string, unknown>;
  timestamp: string;
}

// ── Bucket-scoped chat ────────────────────────────────────────────────────────

export interface BucketScopedChatRequest {
  question: string;
  conversation_history: ChatMessage[];
  bucket_ids?: string[];
  session_id?: string;
}

// ── Document deletion ─────────────────────────────────────────────────────────

export interface DeletionSummary {
  document_id: string;
  original_filename: string;
  bucket_links_removed: number;
  bucket_ids_affected: string[];
  sql_rows_removed: Record<string, number>;
  embeddings_removed: number;
  status: "deleted";
}
