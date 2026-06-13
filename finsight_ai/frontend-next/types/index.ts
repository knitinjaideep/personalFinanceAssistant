// ── Core types ──────────────────────────────────────────────────────────────

export type DocumentStatus = "uploaded" | "processing" | "parsed" | "failed";

export interface DocumentSummary {
  id: string;
  filename: string;
  institution: string;
  status: DocumentStatus;
  page_count: number | null;
  statement_count: number;
  upload_time: string | null;
  processed_time?: string | null;
  error: string | null;

  // Enrichment for grouping (best-effort, may be null)
  account_product?: string | null;
  account_type?: string | null;
  period_start?: string | null;
  period_end?: string | null;
  statement_year?: number | null;
  statement_month?: number | null;
}

export interface DocumentStats {
  total: number;
  parsed: number;
  processing: number;
  uploaded: number;
  failed: number;
}

export interface IngestionHealthSummary {
  total_documents: number;
  complete_documents: number;
  missing_transactions: number;
  missing_chunks: number;
  missing_embeddings: number;
  missing_metadata: number;
  stuck_processing: number;
  failed: number;
  incomplete_documents: number;
}

export interface DocumentIssue {
  document_id: string;
  filename: string;
  status: string;
  issues: string[];
  recommended_action: string;
}

export interface IngestionHealth {
  summary: IngestionHealthSummary;
  documents: DocumentIssue[];
}

export interface ReprocessResult {
  document_id: string;
  filename: string;
  status_before: string;
  status_after: string;
  ok: boolean;
  transactions: number;
  fees: number;
  balances: number;
  holdings: number;
  chunks: number;
  embeddings: number;
  error: string | null;
}

export interface ReprocessJob {
  job_id: string;
  scope: string;
  total: number;
  completed: number;
  succeeded: number;
  failed: number;
  status: "running" | "done";
  results: ReprocessResult[];
  started_at: string;
  finished_at?: string;
}

export interface ReprocessBatchStart {
  job_id: string;
  scope: string;
  count: number;
  document_ids: string[];
}

export interface DocumentUploadResponse {
  document_id: string;
  filename: string;
  status: string;
}

// ── Chat types ──────────────────────────────────────────────────────────────

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  answer?: StructuredAnswer;
  timestamp?: string;
  error_request_id?: string;
  /** Set during SSE streaming — shows status text while LLM hasn't answered yet */
  streamStatus?: string;
}

export interface ChatRequest {
  question: string;
  history: Array<{ role: string; content: string }>;
}

export interface ChatResponse {
  answer: StructuredAnswer;
  raw_text: string;
  request_id?: string;
}

export interface ChartDataset {
  label: string;
  data: number[];
}

export interface ChartPayload {
  type: "bar" | "pie" | "line" | "horizontal_bar";
  title: string;
  labels: string[];
  datasets: ChartDataset[];
  currency: boolean;
}

export interface AnswerTimings {
  intent_ms: number | null;
  parse_ms: number | null;
  sql_ms: number | null;
  rag_ms: number | null;
  llm_ms: number | null;
  total_ms: number | null;
}

export interface StructuredAnswer {
  answer_type: "prose" | "numeric" | "table" | "comparison" | "no_data" | "partial_data";
  title: string;
  summary: string;
  primary_value: string | null;
  highlights: Array<{ label: string; value: string }>;
  sections: AnswerSection[];
  citations: Citation[];
  caveats: string[];
  suggested_followups: string[];
  query_path: string;
  intent: string;
  confidence: number;
  sql_used: string[];
  rows_used: number;
  chart_payload: ChartPayload | null;
  /** Short provenance string, e.g. "Chase Freedom, Mar 2026, 42 rows" */
  based_on?: string;
  // Observability
  request_id?: string;
  timings?: AnswerTimings;
  follow_up_suggestions?: string[];
}

export interface AnswerSection {
  type: string;
  columns?: string[];
  rows?: Record<string, unknown>[];
  [key: string]: unknown;
}

export interface Citation {
  source: string;
  text: string;
  document_id: string;
}

// ── Analytics types ─────────────────────────────────────────────────────────

export interface AnalyticsSummary {
  total_documents: number;
  total_statements: number;
  total_transactions: number;
  total_fees: number;
  total_holdings: number;
  institutions: string[];
  date_range: { start: string | null; end: string | null };
}

// ── Health ───────────────────────────────────────────────────────────────────

export interface HealthStatus {
  status: string;
  ollama: {
    status: string;
    models?: string[];
    chat_model_available?: boolean;
    embed_model_available?: boolean;
    error?: string;
  };
}

// ── Legacy / unused component stubs ─────────────────────────────────────────

export interface MonthlySummary {
  month: string;
  total_spend: number;
  income: number;
  [key: string]: unknown;
}

export interface NetWorthDataPoint {
  date: string;
  total: number;
  [key: string]: unknown;
}

export interface SpendingDataPoint {
  month: string;
  amount: number;
  [key: string]: unknown;
}

export interface Statement {
  id: string;
  institution: string;
  period_start: string;
  period_end: string;
  [key: string]: unknown;
}

export interface AnswerEvidence {
  chunks: EvidenceChunk[];
  [key: string]: unknown;
}

export interface EvidenceChunk {
  content: string;
  page_number?: number;
  document_id?: string;
  [key: string]: unknown;
}
