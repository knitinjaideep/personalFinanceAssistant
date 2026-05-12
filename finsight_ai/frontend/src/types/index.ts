// ── Core types ──────────────────────────────────────────────────────────────

export interface DocumentSummary {
  id: string;
  filename: string;
  institution: string;
  status: "uploaded" | "processing" | "parsed" | "failed";
  page_count: number | null;
  statement_count: number;
  upload_time: string | null;
  error: string | null;
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
}

export interface ChatRequest {
  question: string;
  history: Array<{ role: string; content: string }>;
}

export interface ChatResponse {
  answer: StructuredAnswer;
  raw_text: string;
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
