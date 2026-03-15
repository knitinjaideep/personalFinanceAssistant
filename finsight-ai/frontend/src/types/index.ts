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

// ── Phase 2.7: Structured answer types ───────────────────────────────────────

export interface AnswerHighlight {
  /** Human-readable label for the stat chip, e.g. "Total Fees". */
  label: string;
  /** Formatted value string, e.g. "$1,234.56". */
  value: string;
  unit: string | null;
  /** Direction indicator — used to colour-code the trend annotation. */
  trend: "up" | "down" | "neutral" | null;
  /** Human-readable trend annotation, e.g. "+12% vs last month". */
  trend_label: string | null;
}

export interface AnswerSection {
  /** Section heading shown in the accordion trigger. */
  heading: string;
  /** Section body text rendered as prose. */
  content: string;
  /** Whether the accordion should be open on first render. */
  expanded_by_default: boolean;
}

export interface EvidenceChunk {
  id: string;
  document_id: string;
  chunk_text: string;
  page_number: number | null;
  section: string | null;
  institution_type: string | null;
  statement_period: string | null;
  relevance_score: number | null;
}

export interface AnswerEvidence {
  chunks: EvidenceChunk[];
  sql_query: string | null;
  sql_row_count: number | null;
  data_source: "sql" | "vector" | "hybrid" | "none";
}

export interface ProseAnswer {
  answer_type: "prose";
  text: string;
  title?: string | null;
  highlights?: AnswerHighlight[];
  sections?: AnswerSection[];
  suggested_followups?: string[];
  confidence: number | null;
  caveats: string[];
  evidence: AnswerEvidence;
}

export interface NumericAnswerPayload {
  answer_type: "numeric";
  title?: string | null;
  label: string;
  value: string;
  raw_value: number | null;
  unit: string | null;
  period: string | null;
  institution: string | null;
  account: string | null;
  summary_text: string | null;
  highlights?: AnswerHighlight[];
  sections?: AnswerSection[];
  suggested_followups?: string[];
  confidence: number | null;
  caveats: string[];
  evidence: AnswerEvidence;
}

export interface TableRow {
  cells: Record<string, unknown>;
}

export interface TableAnswerPayload {
  answer_type: "table";
  title: string;
  columns: string[];
  rows: TableRow[];
  row_count: number;
  truncated: boolean;
  summary_text: string | null;
  highlights?: AnswerHighlight[];
  sections?: AnswerSection[];
  suggested_followups?: string[];
  confidence: number | null;
  caveats: string[];
  evidence: AnswerEvidence;
}

export interface ComparisonItem {
  label: string;
  value: string;
  raw_value: number | null;
  delta_pct: number | null;
  is_baseline: boolean;
}

export interface ComparisonAnswerPayload {
  answer_type: "comparison";
  title: string;
  dimension: string;
  metric: string;
  unit: string | null;
  items: ComparisonItem[];
  summary_text: string | null;
  highlights?: AnswerHighlight[];
  sections?: AnswerSection[];
  suggested_followups?: string[];
  confidence: number | null;
  caveats: string[];
  evidence: AnswerEvidence;
}

/** Deterministic no-data answer — built without the LLM. */
export interface NoDataAnswer {
  answer_type: "no_data";
  title: string;
  summary: string;
  what_was_checked: string[];
  possible_reasons: string[];
  suggested_followups: string[];
  confidence: number;
  caveats: string[];
  evidence: AnswerEvidence;
  bucket_label: string | null;
  institution_labels: string[];
}

/** Deterministic partial-data answer — some context found, LLM skipped. */
export interface PartialDataAnswer {
  answer_type: "partial_data";
  title: string;
  summary: string;
  what_was_found: string[];
  what_is_missing: string[];
  suggested_followups: string[];
  confidence: number | null;
  caveats: string[];
  evidence: AnswerEvidence;
  bucket_label: string | null;
  institution_labels: string[];
}

export type StructuredAnswer =
  | ProseAnswer
  | NumericAnswerPayload
  | TableAnswerPayload
  | ComparisonAnswerPayload
  | NoDataAnswer
  | PartialDataAnswer;

/** Mirrors backend PipelineMeta schema. Carried in every response_complete payload. */
export interface PipelineMeta {
  pipeline_stage: "llm" | "no_data" | "partial_data" | "retrieval_only" | "safe_error";
  fallback_triggered: boolean;
  fallback_reason: string | null;
  warnings: string[];
}

export interface StructuredChatResponse {
  session_id: string;
  answer: string;
  answer_type: string;
  structured_answer: StructuredAnswer | null;
  sources: EmbeddingSource[];
  sql_query_used: string | null;
  confidence: number | null;
  caveats: string[];
  processing_time_seconds: number | null;
  /** Pipeline execution metadata — always present in Phase 2.7+ responses. */
  pipeline_meta: PipelineMeta;
}

// ── Phase 2.8: Derived metrics types ─────────────────────────────────────────

export interface AccountNetWorthPoint {
  account_id: string;
  account_label: string;
  institution_type: string;
  total_value: string;
}

export interface NetWorthDataPoint {
  month_start: string;
  year: number;
  month: number;
  total_value: string;
  accounts: AccountNetWorthPoint[];
}

export interface SpendingDataPoint {
  month_start: string;
  year: number;
  month: number;
  total_fees: string;
  total_withdrawals: string;
  total_deposits: string;
  net_cash_flow: string;
  total_dividends: string;
}

export interface MonthlyAccountSummary {
  account_id: string;
  account_label: string;
  institution_type: string;
  institution_name: string;
  total_value: string | null;
  total_fees: string | null;
  total_deposits: string | null;
  total_withdrawals: string | null;
  net_cash_flow: string | null;
  transaction_count: number;
  holding_count: number;
}

export interface MonthlySummary {
  year: number;
  month: number;
  account_count: number;
  total_value: string;
  total_fees: string;
  accounts: MonthlyAccountSummary[];
}

export interface AvailableMonth {
  year: number;
  month: number;
  month_start: string;
}

// ── Phase 3: Bucket-aware analytics types ────────────────────────────────────

export type BucketKind = "investments" | "banking";

/** Standard envelope returned by all /analytics/* Phase 3 endpoints. */
export interface AnalyticsEnvelope<T> {
  data: T;
  warnings: string[];
  partial: boolean;
}

// Investments
export interface AccountSummary {
  account_id: string;
  account_name: string;
  account_type: string;
  institution: string;
  current_value: string;
  as_of_date: string | null;
  portfolio_pct: string;
}

export interface HoldingRow {
  symbol: string | null;
  description: string;
  quantity: string | null;
  price: string | null;
  market_value: string;
  cost_basis: string | null;
  unrealized_gain_loss: string | null;
  unrealized_pct: string | null;
  asset_class: string | null;
  account_id: string;
  account_name: string;
  institution: string;
}

export interface InvMonthlyFee {
  year: number;
  month: number;
  total_fees: string;
  fee_count: number;
  by_category: Record<string, string>;
}

export interface InvBalancePoint {
  snapshot_date: string;
  total_value: string;
  account_id: string;
  account_name: string;
  institution: string;
}

export interface PeriodChange {
  account_id: string;
  account_name: string;
  institution: string;
  previous_value: string | null;
  current_value: string;
  change_amount: string | null;
  change_pct: string | null;
  period_start: string | null;
  period_end: string | null;
}

export interface InvestmentsOverview {
  total_portfolio_value: string;
  accounts: AccountSummary[];
  holdings_breakdown: HoldingRow[];
  fee_trend: InvMonthlyFee[];
  balance_trend: InvBalancePoint[];
  period_changes: PeriodChange[];
}

// Banking
export interface MerchantSpend {
  merchant_name: string;
  total_amount: string;
  transaction_count: number;
  category: string | null;
}

export interface Subscription {
  merchant_name: string;
  typical_amount: string;
  frequency_days: number;
  last_charged: string;
  category: string | null;
  transaction_ids: string[];
}

export interface CardBalance {
  account_id: string;
  account_name: string;
  institution: string;
  current_balance: string;
  as_of_date: string | null;
}

export interface CheckingInOut {
  total_inflows: string;
  total_outflows: string;
  net: string;
}

export interface TransactionSummary {
  id: string;
  account_id: string;
  transaction_date: string;
  description: string;
  merchant_name: string;
  amount: string;
  spend_amount: string | null;
  type: string | null;
  category: string | null;
}

export interface BankingOverview {
  total_spend_this_month: string;
  spend_by_category: Record<string, string>;
  spend_by_merchant: MerchantSpend[];
  subscriptions: Subscription[];
  credit_card_balances: CardBalance[];
  checking_summary: CheckingInOut;
  top_transactions: TransactionSummary[];
  unusual_transactions: TransactionSummary[];
}

// ── Phase 4: chat pipeline types ─────────────────────────────────────────────

export type PipelineStageValue = "llm" | "retrieval_only" | "safe_error";

/**
 * @deprecated Use PipelineMeta (from StructuredChatResponse) instead.
 * Kept for backward compatibility with older response_complete payloads.
 */
export interface ChatPipelinePayload {
  fallback_triggered: boolean;
  pipeline_stage: PipelineStageValue;
  warnings: string[];
  partial: boolean;
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
