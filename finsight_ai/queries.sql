-- ============================================================================
-- Coral — SQL Query Reference
-- ============================================================================
-- Ad-hoc queries against the local Coral SQLite database. This file is a
-- reference to copy/paste from, not a script meant to be run top to bottom.
--
-- Connect:
--   sqlite3 backend/data/db/finsight.db
--   (or point a GUI client — TablePlus / DB Browser for SQLite / DBeaver — here)
--
-- Run a single query from this file with sqlite3's dot-command:
--   sqlite3 backend/data/db/finsight.db < queries.sql   -- runs everything (noisy)
--   sqlite3 -header -column backend/data/db/finsight.db "$(sed -n '40,55p' queries.sql)"
--
-- Schema reference: README_DATABASE.md
-- Full schema notes:
--   - Monetary columns (amount, market_value, total_value, ...) are stored as
--     TEXT (Decimal strings) to avoid float precision loss. Wrap them in
--     CAST(col AS REAL) for arithmetic/sorting.
--   - Dates are SQLite DATE ('YYYY-MM-DD'); datetimes are ISO 8601 TEXT.
--   - All primary/foreign keys are TEXT (UUIDs).
--   - institution_type is free text, not an enforced FK. Current parseable
--     values: 'morgan_stanley', 'chase', 'etrade', 'amex', 'discover', 'bofa'.
--     Catalog-only (no parser yet): 'marcus', '529'.
-- ============================================================================


-- ============================================================================
-- 0. SCHEMA EXPLORATION
-- ============================================================================

-- List every table (equivalent to sqlite3's `.tables`)
SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name;

-- Show the CREATE TABLE statement for a given table (equivalent to `.schema <table>`)
SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'transactions';

-- Row counts across every canonical table, useful as a quick sanity check
SELECT 'institutions' AS table_name, COUNT(*) AS rows FROM institutions
UNION ALL SELECT 'accounts', COUNT(*) FROM accounts
UNION ALL SELECT 'documents', COUNT(*) FROM documents
UNION ALL SELECT 'statements', COUNT(*) FROM statements
UNION ALL SELECT 'transactions', COUNT(*) FROM transactions
UNION ALL SELECT 'fees', COUNT(*) FROM fees
UNION ALL SELECT 'holdings', COUNT(*) FROM holdings
UNION ALL SELECT 'balance_snapshots', COUNT(*) FROM balance_snapshots
UNION ALL SELECT 'text_chunks', COUNT(*) FROM text_chunks
UNION ALL SELECT 'derived_metrics', COUNT(*) FROM derived_metrics;


-- ============================================================================
-- 1. INSTITUTIONS & ACCOUNTS
-- ============================================================================

-- All institutions on file
SELECT id, name, institution_type, website, created_at
FROM institutions
ORDER BY name;

-- All accounts with their parent institution
SELECT
    a.id,
    a.account_name,
    a.account_number_masked,
    a.account_type,
    a.institution_type,
    i.name AS institution_name,
    a.currency,
    a.created_at
FROM accounts a
JOIN institutions i ON i.id = a.institution_id
ORDER BY a.institution_type, a.account_name;

-- Account count per institution
SELECT institution_type, COUNT(*) AS account_count
FROM accounts
GROUP BY institution_type
ORDER BY account_count DESC;


-- ============================================================================
-- 2. DOCUMENTS & INGESTION STATUS
-- ============================================================================

-- Ingestion status per institution (parsed / failed / pending / total)
SELECT
    institution_type,
    COUNT(*)                                             AS total,
    SUM(CASE WHEN status = 'parsed'     THEN 1 ELSE 0 END) AS parsed,
    SUM(CASE WHEN status = 'failed'     THEN 1 ELSE 0 END) AS failed,
    SUM(CASE WHEN status = 'processing' THEN 1 ELSE 0 END) AS processing,
    SUM(CASE WHEN status = 'uploaded'   THEN 1 ELSE 0 END) AS uploaded,
    MAX(upload_time)                                       AS last_ingested
FROM documents
GROUP BY institution_type
ORDER BY total DESC;

-- Documents that failed to parse, with the error message
SELECT original_filename, institution_type, error_message, upload_time
FROM documents
WHERE status = 'failed'
ORDER BY upload_time DESC;

-- Documents discovered by the local scanner but not yet ingested
SELECT original_filename, institution_type, account_product, source_id, source_file_path, status
FROM documents
WHERE status != 'parsed'
ORDER BY upload_time DESC;

-- Duplicate-hash check (should return 0 rows — file_hash is the dedup key)
SELECT file_hash, COUNT(*) AS copies
FROM documents
WHERE file_hash IS NOT NULL
GROUP BY file_hash
HAVING COUNT(*) > 1;

-- Statement date coverage per institution (earliest → latest parsed statement)
SELECT
    d.institution_type,
    MIN(s.period_start)  AS earliest,
    MAX(s.period_end)    AS latest,
    COUNT(DISTINCT d.id) AS doc_count
FROM statements s
JOIN documents d ON d.id = s.document_id
GROUP BY d.institution_type
ORDER BY doc_count DESC;

-- Statements with low extraction confidence — worth a manual review
SELECT
    s.id,
    d.original_filename,
    d.institution_type,
    s.period_start,
    s.period_end,
    s.overall_confidence,
    s.warnings
FROM statements s
JOIN documents d ON d.id = s.document_id
WHERE s.overall_confidence < 0.7
ORDER BY s.overall_confidence ASC;


-- ============================================================================
-- 3. BALANCES / NET WORTH
-- ============================================================================

-- Latest balance snapshot per account (current net worth by account)
SELECT
    a.account_name,
    a.institution_type,
    a.account_type,
    bs.total_value,
    bs.cash_value,
    bs.invested_value,
    bs.snapshot_date
FROM balance_snapshots bs
JOIN accounts a ON a.id = bs.account_id
WHERE bs.snapshot_date = (
    SELECT MAX(snapshot_date) FROM balance_snapshots WHERE account_id = bs.account_id
)
ORDER BY CAST(bs.total_value AS REAL) DESC;

-- Total net worth right now (sum of latest snapshot per account)
SELECT SUM(CAST(bs.total_value AS REAL)) AS net_worth
FROM balance_snapshots bs
WHERE bs.snapshot_date = (
    SELECT MAX(snapshot_date) FROM balance_snapshots WHERE account_id = bs.account_id
);

-- Balance history for one account (swap the account_id) — for trend charts
SELECT snapshot_date, total_value, cash_value, invested_value
FROM balance_snapshots
WHERE account_id = 'REPLACE_WITH_ACCOUNT_ID'
ORDER BY snapshot_date;

-- Month-over-month change in total balance, per account
WITH ranked AS (
    SELECT
        account_id,
        snapshot_date,
        CAST(total_value AS REAL) AS total_value,
        LAG(CAST(total_value AS REAL)) OVER (
            PARTITION BY account_id ORDER BY snapshot_date
        ) AS prev_value
    FROM balance_snapshots
)
SELECT
    a.account_name,
    r.snapshot_date,
    r.total_value,
    r.prev_value,
    ROUND(r.total_value - r.prev_value, 2) AS change
FROM ranked r
JOIN accounts a ON a.id = r.account_id
WHERE r.prev_value IS NOT NULL
ORDER BY a.account_name, r.snapshot_date;


-- ============================================================================
-- 4. INVESTMENTS / HOLDINGS
-- ============================================================================

-- Current holdings (as of each account's most recent statement), largest first
SELECT
    a.account_name,
    a.institution_type,
    h.symbol,
    h.description,
    h.quantity,
    h.market_value,
    h.unrealized_gain_loss,
    h.asset_class
FROM holdings h
JOIN accounts a ON a.id = h.account_id
JOIN statements s ON s.id = h.statement_id
WHERE s.period_end = (
    SELECT MAX(period_end) FROM statements WHERE account_id = h.account_id
)
ORDER BY CAST(h.market_value AS REAL) DESC;

-- Top 10 holdings across all accounts, by market value
SELECT
    h.symbol, h.description, h.market_value, h.unrealized_gain_loss,
    a.account_name, a.institution_type
FROM holdings h
JOIN accounts a ON a.id = h.account_id
JOIN statements s ON s.id = h.statement_id
WHERE s.period_end = (
    SELECT MAX(period_end) FROM statements WHERE account_id = h.account_id
)
ORDER BY CAST(h.market_value AS REAL) DESC
LIMIT 10;

-- Portfolio allocation by asset class
SELECT
    COALESCE(h.asset_class, 'unclassified') AS asset_class,
    SUM(CAST(h.market_value AS REAL))       AS total_value,
    COUNT(*)                                AS holding_count
FROM holdings h
JOIN statements s ON s.id = h.statement_id
WHERE s.period_end = (
    SELECT MAX(period_end) FROM statements WHERE account_id = h.account_id
)
GROUP BY asset_class
ORDER BY total_value DESC;

-- Investment trades (buys/sells) in transactions, most recent first
SELECT
    t.transaction_date, t.description, t.symbol, t.quantity, t.price_per_unit,
    t.amount, t.transaction_type, a.account_name
FROM transactions t
JOIN accounts a ON a.id = t.account_id
WHERE t.transaction_type IN ('trade_buy', 'trade_sell')
ORDER BY t.transaction_date DESC;


-- ============================================================================
-- 5. BANKING / SPENDING
-- ============================================================================

-- Monthly spend, last 12 months (banking institutions only)
SELECT
    strftime('%Y-%m', t.transaction_date) AS month,
    SUM(CAST(t.amount AS REAL))           AS total_spend,
    COUNT(*)                              AS txn_count
FROM transactions t
JOIN accounts a ON a.id = t.account_id
WHERE a.institution_type IN ('chase', 'amex', 'discover', 'bofa')
  AND t.transaction_type IN ('purchase', 'withdrawal', 'other')
  AND CAST(t.amount AS REAL) > 0
  AND t.transaction_date >= date('now', '-12 months')
GROUP BY month
ORDER BY month;

-- Spending by category (all time)
SELECT
    COALESCE(t.category, 'uncategorized') AS category,
    SUM(CAST(t.amount AS REAL))           AS total,
    COUNT(*)                              AS txn_count
FROM transactions t
JOIN accounts a ON a.id = t.account_id
WHERE a.institution_type IN ('chase', 'amex', 'discover', 'bofa')
  AND CAST(t.amount AS REAL) > 0
GROUP BY category
ORDER BY total DESC;

-- Spending by category, single month (swap the month)
SELECT
    COALESCE(t.category, 'uncategorized') AS category,
    SUM(CAST(t.amount AS REAL))           AS total,
    COUNT(*)                              AS txn_count
FROM transactions t
JOIN accounts a ON a.id = t.account_id
WHERE a.institution_type IN ('chase', 'amex', 'discover', 'bofa')
  AND CAST(t.amount AS REAL) > 0
  AND strftime('%Y-%m', t.transaction_date) = '2026-07'
GROUP BY category
ORDER BY total DESC;

-- Top merchants by total spend
SELECT
    COALESCE(t.merchant_name, t.description) AS merchant,
    SUM(CAST(t.amount AS REAL))              AS total_spend,
    COUNT(*)                                 AS txn_count
FROM transactions t
JOIN accounts a ON a.id = t.account_id
WHERE a.institution_type IN ('chase', 'amex', 'discover', 'bofa')
  AND CAST(t.amount AS REAL) > 0
GROUP BY merchant
ORDER BY total_spend DESC
LIMIT 25;

-- Recurring / subscription-like transactions (flagged during ingestion)
SELECT
    COALESCE(t.merchant_name, t.description) AS merchant,
    a.account_name,
    t.category,
    t.amount,
    t.transaction_date
FROM transactions t
JOIN accounts a ON a.id = t.account_id
WHERE t.is_recurring = 1
ORDER BY merchant, t.transaction_date;

-- Transactions over a given amount, any account (swap the threshold)
SELECT
    t.transaction_date, t.description, t.merchant_name, t.amount, t.category,
    a.account_name, a.institution_type
FROM transactions t
JOIN accounts a ON a.id = t.account_id
WHERE CAST(t.amount AS REAL) > 500
ORDER BY t.transaction_date DESC;

-- Cash flow summary: inflow vs outflow per account, per month
SELECT
    a.account_name,
    strftime('%Y-%m', t.transaction_date) AS month,
    SUM(CASE WHEN CAST(t.amount AS REAL) < 0 THEN -CAST(t.amount AS REAL) ELSE 0 END) AS inflow,
    SUM(CASE WHEN CAST(t.amount AS REAL) > 0 THEN  CAST(t.amount AS REAL) ELSE 0 END) AS outflow
FROM transactions t
JOIN accounts a ON a.id = t.account_id
GROUP BY a.account_name, month
ORDER BY a.account_name, month;


-- ============================================================================
-- 6. FEES
-- ============================================================================

-- Total fees by category, all time
SELECT
    COALESCE(fee_category, 'uncategorized') AS fee_category,
    COUNT(*)                                AS count,
    SUM(CAST(amount AS REAL))               AS total
FROM fees
GROUP BY fee_category
ORDER BY total DESC;

-- Fees by institution, last 12 months
SELECT
    a.institution_type,
    SUM(CAST(f.amount AS REAL)) AS total_fees,
    COUNT(*)                    AS fee_count
FROM fees f
JOIN accounts a ON a.id = f.account_id
WHERE f.fee_date >= date('now', '-12 months')
GROUP BY a.institution_type
ORDER BY total_fees DESC;

-- Advisory fees over time (Morgan Stanley) with annualized rate
SELECT fee_date, description, amount, annualized_rate
FROM fees
WHERE fee_category = 'advisory'
ORDER BY fee_date DESC;


-- ============================================================================
-- 7. INSTITUTION-SPECIFIC DETAIL TABLES
-- ============================================================================

-- Morgan Stanley: advisor info + performance, most recent statement per account
SELECT
    a.account_name, s.period_end,
    md.financial_advisor, md.advisor_phone,
    md.management_fee_rate, md.performance_ytd, md.performance_1yr, md.margin_balance
FROM morgan_stanley_details md
JOIN statements s ON s.id = md.statement_id
JOIN accounts a ON a.id = s.account_id
ORDER BY s.period_end DESC;

-- Chase: rewards balance + APR + credit utilization, most recent statement per account
SELECT
    a.account_name, s.period_end,
    cd.rewards_balance, cd.apr_purchase, cd.credit_limit, cd.available_credit,
    ROUND(1 - (CAST(cd.available_credit AS REAL) / NULLIF(CAST(cd.credit_limit AS REAL), 0)), 3) AS utilization
FROM chase_details cd
JOIN statements s ON s.id = cd.statement_id
JOIN accounts a ON a.id = s.account_id
ORDER BY s.period_end DESC;

-- E*TRADE: buying power + realized gain/loss YTD
SELECT
    a.account_name, s.period_end,
    ed.margin_buying_power, ed.option_buying_power, ed.realized_gain_loss_ytd
FROM etrade_details ed
JOIN statements s ON s.id = ed.statement_id
JOIN accounts a ON a.id = s.account_id
ORDER BY s.period_end DESC;

-- Amex: membership rewards + spend YTD
SELECT
    a.account_name, s.period_end,
    ad.membership_rewards_balance, ad.year_to_date_spend, ad.payment_due_date, ad.minimum_payment
FROM amex_details ad
JOIN statements s ON s.id = ad.statement_id
JOIN accounts a ON a.id = s.account_id
ORDER BY s.period_end DESC;

-- Discover: cashback balance + credit limit
SELECT
    a.account_name, s.period_end,
    dd.cashback_balance, dd.apr_purchase, dd.credit_limit, dd.promotional_balance
FROM discover_details dd
JOIN statements s ON s.id = dd.statement_id
JOIN accounts a ON a.id = s.account_id
ORDER BY s.period_end DESC;


-- ============================================================================
-- 8. DERIVED METRICS (pre-aggregated monthly rollups)
-- ============================================================================

-- Monthly rollup per account, most recent 12 months
SELECT
    a.account_name, dm.year, dm.month,
    dm.total_value, dm.total_deposits, dm.total_withdrawals, dm.total_fees,
    dm.net_cash_flow, dm.total_spend, dm.transaction_count
FROM derived_metrics dm
JOIN accounts a ON a.id = dm.account_id
WHERE dm.month_start >= date('now', '-12 months')
ORDER BY a.account_name, dm.month_start;


-- ============================================================================
-- 9. FULL-TEXT SEARCH (FTS5 — text_chunks_fts)
-- ============================================================================
-- Used by the chat pipeline for RouteType.DOCUMENT_SEARCH / HYBRID answers.
-- See backend/app/db/fts.py for index_chunk() / search_fts().

-- Search document text for a phrase (MATCH supports FTS5 query syntax:
-- AND/OR/NOT, "phrase queries", prefix* etc.)
SELECT
    chunk_id, document_id, institution_type, page_number,
    snippet(text_chunks_fts, 0, '[', ']', '...', 32) AS excerpt
FROM text_chunks_fts
WHERE text_chunks_fts MATCH 'advisory fee'
ORDER BY rank
LIMIT 10;

-- Full-text search scoped to one institution
SELECT
    chunk_id, page_number,
    snippet(text_chunks_fts, 0, '[', ']', '...', 32) AS excerpt
FROM text_chunks_fts
WHERE text_chunks_fts MATCH 'margin call'
  AND institution_type = 'morgan_stanley'
ORDER BY rank
LIMIT 10;

-- Join FTS hits back to the parent document for filenames/dates
SELECT
    d.original_filename, d.institution_type, tc.page_number,
    snippet(text_chunks_fts, 0, '[', ']', '...', 32) AS excerpt
FROM text_chunks_fts
JOIN text_chunks tc ON tc.id = text_chunks_fts.chunk_id
JOIN documents d ON d.id = tc.document_id
WHERE text_chunks_fts MATCH 'expense ratio'
ORDER BY rank
LIMIT 10;


-- ============================================================================
-- 10. DATA QUALITY / DEBUGGING
-- ============================================================================

-- Transactions with low extraction confidence
SELECT t.id, a.account_name, t.transaction_date, t.description, t.amount, t.confidence
FROM transactions t
JOIN accounts a ON a.id = t.account_id
WHERE t.confidence < 0.8
ORDER BY t.confidence ASC;

-- Accounts with no balance snapshot at all (likely an incomplete ingest)
SELECT a.id, a.account_name, a.institution_type
FROM accounts a
LEFT JOIN balance_snapshots bs ON bs.account_id = a.id
WHERE bs.id IS NULL;

-- Statements that never got a corresponding text_chunks row (FTS gap)
SELECT s.id, d.original_filename, s.period_end
FROM statements s
JOIN documents d ON d.id = s.document_id
LEFT JOIN text_chunks tc ON tc.statement_id = s.id
WHERE tc.id IS NULL;

-- Text chunks missing an embedding (vector search will skip these)
SELECT COUNT(*) AS chunks_without_embedding
FROM text_chunks
WHERE embedding IS NULL;
