# Coral — Database Reference

The database is a local SQLite file at `backend/data/db/finsight.db`.

Connect with:
```bash
sqlite3 backend/data/db/finsight.db
```

Or use TablePlus, DB Browser for SQLite, or DBeaver for a GUI.

---

## Schema overview

### Canonical tables (primary query surface)

| Table | Purpose |
|-------|---------|
| `institutions` | One row per institution (chase, morgan_stanley, etc.) |
| `accounts` | One row per financial account per institution |
| `documents` | One row per ingested PDF file |
| `statements` | One row per parsed statement period |
| `transactions` | Individual transactions (banking + investment trades) |
| `fees` | Fee records (advisory, management, late fee, etc.) |
| `holdings` | Investment holdings per statement |
| `balance_snapshots` | Point-in-time account balances |
| `text_chunks` | Document text chunks for FTS5 search |
| `derived_metrics` | Pre-aggregated monthly metrics per account |

### Institution-specific detail tables

| Table | Institution |
|-------|-------------|
| `morgan_stanley_details` | Advisor info, performance, asset allocation JSON |
| `chase_details` | Rewards points, APR, credit limit |
| `etrade_details` | Buying power, realized gain/loss YTD |
| `amex_details` | Membership rewards, credit limit |
| `discover_details` | Cashback earned/redeemed, APR |

Bank of America (`institution_type = 'bofa'`) has a full parser but **no**
detail table — it only ever populates the canonical tables above. Marcus and
529 are catalog-only stubs with no parser registered at all (see
`backend/app/config/statement_catalog.py`), so they won't appear in any table
until a parser is written for them.

### Scanner tracking fields (on `documents` table)

| Column | Purpose |
|--------|---------|
| `file_hash` | SHA-256 of the PDF — used for deduplication |
| `source_file_path` | Absolute path as discovered by scanner |
| `account_product` | Human label, e.g. "Chase Freedom Unlimited" |
| `source_id` | Source key from statement_sources.py |

---

## Key design decisions

- **Monetary values stored as TEXT (Decimal strings)** to avoid SQLite float precision loss
  - Query them with `CAST(amount AS REAL)` for arithmetic
- **Dates stored as SQLite `DATE`** (`YYYY-MM-DD`)
- **UUIDs stored as TEXT**
- **FTS5 virtual table** `text_chunks_fts` mirrors `text_chunks` for full-text search

---

## Example SQL queries

The full, actively-maintained query reference lives in
[`queries.sql`](queries.sql) at the repo root — schema exploration, balances,
holdings, spending, fees, institution-detail tables, derived metrics, FTS5
search, and data-quality checks, all copy-paste ready. A couple of the most
common ones:

### Total portfolio value (latest balance per account)
```sql
SELECT
    a.account_name,
    a.institution_type,
    bs.total_value,
    bs.snapshot_date
FROM balance_snapshots bs
JOIN accounts a ON a.id = bs.account_id
WHERE bs.snapshot_date = (
    SELECT MAX(snapshot_date) FROM balance_snapshots
    WHERE account_id = bs.account_id
)
ORDER BY CAST(bs.total_value AS REAL) DESC;
```

### Monthly spend (last 12 months)
```sql
SELECT
    strftime('%Y-%m', transaction_date) AS month,
    SUM(CAST(amount AS REAL))           AS total_spend,
    COUNT(*)                            AS txn_count
FROM transactions t
JOIN accounts a ON a.id = t.account_id
WHERE a.institution_type IN ('chase','amex','discover','bofa')
  AND t.transaction_type IN ('purchase','withdrawal','other')
  AND CAST(t.amount AS REAL) > 0
  AND t.transaction_date >= date('now', '-12 months')
GROUP BY month
ORDER BY month;
```

See [`queries.sql`](queries.sql) for the rest (fees by category, top holdings,
document/statement coverage, FTS5 search, institution-detail tables, data
quality checks, and more).

---

## Where dashboard queries live

All dashboard SQL is centralized in:

```
backend/app/services/dashboard/
  investment_queries.py   — portfolio, holdings, fees, balance history
  banking_queries.py      — spend, categories, merchants, cash flow, subscriptions
  summary_queries.py      — top-level KPI counts, per-institution coverage
```

The API layer in `backend/app/api/dashboard.py` calls these functions and assembles JSON responses. No business logic lives in the API layer.

---

## FTS5 full-text search

The `text_chunks_fts` virtual table enables full-text search across all document text.

```sql
-- Search for mentions of "advisory fee"
SELECT
    chunk_id, document_id, institution_type,
    snippet(text_chunks_fts, 2, '<b>', '</b>', '...', 32) AS excerpt
FROM text_chunks_fts
WHERE text_chunks_fts MATCH 'advisory fee'
ORDER BY rank
LIMIT 10;
```

Used by the chat system when `QueryPath.FTS` or `QueryPath.HYBRID` is selected.
