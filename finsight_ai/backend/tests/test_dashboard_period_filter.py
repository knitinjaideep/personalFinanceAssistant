"""
PR 05 — Global Period Filter: backend date-range querying for the dashboard
endpoints (`GET /api/v1/dashboard/banking`, `GET /api/v1/dashboard/investments`).

Exercises the unified `date_from`/`date_to` (service layer) /
`start_date`/`end_date` (API layer) contract against a real temp SQLite DB —
confirms transactions/snapshots/fees outside the requested range are
excluded, in-range rows are included, and the pre-PR-05 "no range given"
behavior (all-time or legacy rolling `months` window) is unchanged.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException

from app.api.dashboard import _validate_range, get_banking_dashboard, get_investments_dashboard
from app.db import repositories as repo
from app.db.engine import get_session
from app.services.dashboard.banking_queries import (
    banking_card_spend_summary,
    banking_cash_flow,
    banking_spend_by_category,
    banking_spend_by_month,
    banking_top_merchants,
)
from app.services.dashboard.investment_queries import (
    allocation_by_account,
    balance_history_by_account,
    investment_fees_summary,
    investment_portfolio_summary,
    top_holdings_by_value,
)


async def _make_account(session, *, institution_type, account_type, suffix):
    inst = await repo.get_or_create_institution(session, institution_type, institution_type.title())
    acct = await repo.get_or_create_account(
        session, institution_id=inst.id, institution_type=institution_type,
        account_number_masked=f"****{suffix}", account_type=account_type,
    )
    doc = await repo.create_document(
        session, original_filename="s.pdf", stored_filename="s.pdf",
        file_path="/tmp/s.pdf", file_size_bytes=1, mime_type="application/pdf",
        status="parsed", institution_type=institution_type,
    )
    stmt = await repo.create_statement(
        session, document_id=doc.id, institution_id=inst.id, institution_type=institution_type,
        account_id=acct.id, account_type=account_type, statement_type="bank",
        period_start=date(2026, 1, 1), period_end=date(2026, 12, 31),
        extraction_status="success", overall_confidence=0.9, warnings="[]",
    )
    return acct, stmt


async def _add_txn(session, account_id, statement_id, *, txn_date, description, amount, transaction_type="purchase"):
    await repo.bulk_create_transactions(session, [{
        "account_id": account_id, "statement_id": statement_id,
        "transaction_date": txn_date, "description": description,
        "amount": amount, "transaction_type": transaction_type,
    }])


# ── banking_spend_by_month ───────────────────────────────────────────────────

async def test_banking_spend_by_month_filters_to_range(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session, institution_type="chase", account_type="credit_card", suffix="1")
        await _add_txn(session, acct.id, stmt.id, txn_date=date(2026, 6, 10), description="IN RANGE", amount="-50.00")
        await _add_txn(session, acct.id, stmt.id, txn_date=date(2026, 5, 1), description="BEFORE RANGE", amount="-999.00")
        await _add_txn(session, acct.id, stmt.id, txn_date=date(2026, 7, 1), description="AFTER RANGE", amount="-999.00")

    async with get_session() as session:
        rows = await banking_spend_by_month(
            session, date_from=date(2026, 6, 1), date_to=date(2026, 6, 30),
        )
    assert len(rows) == 1
    assert rows[0]["month"] == "2026-06"
    assert rows[0]["total_spend"] == 50.0


async def test_banking_spend_by_month_no_range_uses_legacy_months_window(temp_db):
    """Backward compatibility: omitting date_from/date_to preserves the
    original rolling-`months`-window behavior (a transaction from today is
    always in range for the default months=12)."""
    async with get_session() as session:
        acct, stmt = await _make_account(session, institution_type="chase", account_type="credit_card", suffix="2")
        await _add_txn(session, acct.id, stmt.id, txn_date=date.today(), description="TODAY", amount="-10.00")

    async with get_session() as session:
        rows = await banking_spend_by_month(session, months=12)
    assert len(rows) == 1
    assert rows[0]["total_spend"] == 10.0


# ── banking_spend_by_category / top_merchants / card_spend_summary ─────────

async def test_banking_spend_by_category_filters_to_range(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session, institution_type="amex", account_type="credit_card", suffix="3")
        await _add_txn(session, acct.id, stmt.id, txn_date=date(2026, 6, 10), description="WHOLE FOODS", amount="-40.00")
        await repo.bulk_create_transactions(session, [{
            "account_id": acct.id, "statement_id": stmt.id, "transaction_date": date(2026, 6, 10),
            "description": "WHOLE FOODS", "amount": "-40.00", "transaction_type": "purchase",
            "category": "groceries",
        }])
        await repo.bulk_create_transactions(session, [{
            "account_id": acct.id, "statement_id": stmt.id, "transaction_date": date(2026, 1, 1),
            "description": "OLD SHOPPING", "amount": "-999.00", "transaction_type": "purchase",
            "category": "shopping",
        }])

    async with get_session() as session:
        rows = await banking_spend_by_category(session, date_from=date(2026, 6, 1), date_to=date(2026, 6, 30))
    categories = {r["category"] for r in rows}
    assert "groceries" in categories
    assert "shopping" not in categories

    async with get_session() as session:
        rows_unfiltered = await banking_spend_by_category(session)
    categories_unfiltered = {r["category"] for r in rows_unfiltered}
    assert "shopping" in categories_unfiltered


async def test_banking_top_merchants_filters_to_range(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session, institution_type="discover", account_type="credit_card", suffix="4")
        await _add_txn(session, acct.id, stmt.id, txn_date=date(2026, 6, 10), description="TARGET", amount="-30.00")
        await _add_txn(session, acct.id, stmt.id, txn_date=date(2026, 1, 1), description="OLD MERCHANT", amount="-500.00")

    async with get_session() as session:
        rows = await banking_top_merchants(session, date_from=date(2026, 6, 1), date_to=date(2026, 6, 30))
    merchants = {r["merchant"] for r in rows}
    assert "TARGET" in merchants
    assert "OLD MERCHANT" not in merchants


async def test_banking_card_spend_summary_filters_to_range(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session, institution_type="chase", account_type="credit_card", suffix="5")
        await _add_txn(session, acct.id, stmt.id, txn_date=date(2026, 6, 10), description="IN RANGE", amount="-30.00")
        await _add_txn(session, acct.id, stmt.id, txn_date=date(2026, 1, 1), description="OUT OF RANGE", amount="-500.00")

    async with get_session() as session:
        rows = await banking_card_spend_summary(session, date_from=date(2026, 6, 1), date_to=date(2026, 6, 30))
    assert len(rows) == 1
    assert rows[0]["total_spend"] == 30.0


# ── banking_cash_flow ────────────────────────────────────────────────────────

async def test_banking_cash_flow_filters_to_range(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session, institution_type="chase", account_type="checking", suffix="6")
        # Deposit (negative = inflow per this query's sign convention)
        await _add_txn(session, acct.id, stmt.id, txn_date=date(2026, 6, 5), description="PAYCHECK", amount="-2000.00", transaction_type="deposit")
        await _add_txn(session, acct.id, stmt.id, txn_date=date(2026, 1, 5), description="OLD PAYCHECK", amount="-2000.00", transaction_type="deposit")

    async with get_session() as session:
        rows = await banking_cash_flow(session, date_from=date(2026, 6, 1), date_to=date(2026, 6, 30))
    assert len(rows) == 1
    assert rows[0]["month"] == "2026-06"
    assert rows[0]["inflow"] == 2000.0


# ── balance_history_by_account (investments) ────────────────────────────────

async def test_balance_history_by_account_filters_to_range(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session, institution_type="etrade", account_type="individual_brokerage", suffix="7")
        await repo.bulk_create_balance_snapshots(session, [
            {"account_id": acct.id, "statement_id": stmt.id, "snapshot_date": date(2026, 6, 15), "total_value": "10000.00"},
            {"account_id": acct.id, "statement_id": stmt.id, "snapshot_date": date(2026, 1, 15), "total_value": "9000.00"},
        ])

    async with get_session() as session:
        rows = await balance_history_by_account(session, date_from=date(2026, 6, 1), date_to=date(2026, 6, 30))
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-06-15"

    async with get_session() as session:
        rows_unfiltered = await balance_history_by_account(session)
    assert len(rows_unfiltered) == 2


# ── investment_fees_summary ──────────────────────────────────────────────────

async def test_investment_fees_summary_filters_to_range(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session, institution_type="morgan_stanley", account_type="advisory", suffix="8")
        await repo.bulk_create_fees(session, [
            {"account_id": acct.id, "statement_id": stmt.id, "fee_date": date(2026, 6, 20), "description": "advisory fee", "amount": "25.00", "fee_category": "advisory"},
            {"account_id": acct.id, "statement_id": stmt.id, "fee_date": date(2026, 1, 20), "description": "old fee", "amount": "99.00", "fee_category": "advisory"},
        ])

    async with get_session() as session:
        summary = await investment_fees_summary(session, date_from=date(2026, 6, 1), date_to=date(2026, 6, 30))
    assert summary["total_fees"] == 25.0

    async with get_session() as session:
        summary_unfiltered = await investment_fees_summary(session)
    assert summary_unfiltered["total_fees"] == pytest.approx(124.0)


# ── _validate_range ──────────────────────────────────────────────────────────

def test_validate_range_allows_both_none():
    _validate_range(None, None)  # no raise


def test_validate_range_allows_both_given():
    _validate_range(date(2026, 6, 1), date(2026, 6, 30))  # no raise


def test_validate_range_rejects_partial():
    with pytest.raises(HTTPException) as exc:
        _validate_range(date(2026, 6, 1), None)
    assert exc.value.status_code == 422


def test_validate_range_rejects_inverted():
    with pytest.raises(HTTPException) as exc:
        _validate_range(date(2026, 6, 30), date(2026, 6, 1))
    assert exc.value.status_code == 422


# ── Full endpoint payloads ────────────────────────────────────────────────────

async def test_get_banking_dashboard_applies_range_and_reports_period(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session, institution_type="chase", account_type="credit_card", suffix="9")
        await _add_txn(session, acct.id, stmt.id, txn_date=date(2026, 6, 10), description="IN RANGE", amount="-15.00")
        await _add_txn(session, acct.id, stmt.id, txn_date=date(2026, 1, 1), description="OUT OF RANGE", amount="-500.00")

    payload = await get_banking_dashboard(start_date=date(2026, 6, 1), end_date=date(2026, 6, 30))
    assert payload["period"] == {"start_date": date(2026, 6, 1), "end_date": date(2026, 6, 30)}
    assert len(payload["spend_by_month"]) == 1
    assert payload["spend_by_month"][0]["total_spend"] == 15.0


async def test_get_banking_dashboard_no_range_reports_null_period(temp_db):
    payload = await get_banking_dashboard()
    assert payload["period"] is None


async def test_get_investments_dashboard_applies_range_and_reports_period(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(session, institution_type="etrade", account_type="individual_brokerage", suffix="10")
        await repo.bulk_create_balance_snapshots(session, [
            {"account_id": acct.id, "statement_id": stmt.id, "snapshot_date": date(2026, 6, 15), "total_value": "5000.00"},
            {"account_id": acct.id, "statement_id": stmt.id, "snapshot_date": date(2026, 1, 15), "total_value": "4000.00"},
        ])

    payload = await get_investments_dashboard(start_date=date(2026, 6, 1), end_date=date(2026, 6, 30))
    assert payload["period"] == {"start_date": date(2026, 6, 1), "end_date": date(2026, 6, 30)}
    assert len(payload["balance_history"]) == 1


async def test_get_dashboard_endpoints_reject_partial_range(temp_db):
    with pytest.raises(HTTPException):
        await get_banking_dashboard(start_date=date(2026, 6, 1), end_date=None)
    with pytest.raises(HTTPException):
        await get_investments_dashboard(start_date=date(2026, 6, 1), end_date=None)


# ── Point-in-time payloads resolve "as of" the end of the period ─────────────
#
# portfolio_summary / allocation / top_holdings are point-in-time figures, not
# period activity — but "point in time" must mean "as of the end of the
# selected period", not "as of today". Otherwise selecting a past period shows
# a period-filtered balance_history alongside an unfiltered, present-day
# headline portfolio value, which is a mixed-period (and therefore misleading)
# page.

async def test_portfolio_summary_resolves_as_of_end_date(temp_db):
    async with get_session() as session:
        acct, stmt = await _make_account(
            session, institution_type="etrade", account_type="individual_brokerage", suffix="20",
        )
        await repo.bulk_create_balance_snapshots(session, [
            {"account_id": acct.id, "statement_id": stmt.id,
             "snapshot_date": date(2026, 1, 15), "total_value": "4000.00"},
            {"account_id": acct.id, "statement_id": stmt.id,
             "snapshot_date": date(2026, 6, 15), "total_value": "5000.00"},
        ])

    async with get_session() as session:
        as_of_march = await investment_portfolio_summary(session, as_of=date(2026, 3, 31))
        as_of_july = await investment_portfolio_summary(session, as_of=date(2026, 7, 31))
        latest_ever = await investment_portfolio_summary(session)

    assert as_of_march["total_portfolio_value"] == 4000.0
    assert as_of_march["last_updated"] == "2026-01-15"
    assert as_of_july["total_portfolio_value"] == 5000.0
    # No `as_of` must behave exactly as it did before PR 05.
    assert latest_ever["total_portfolio_value"] == 5000.0


async def test_portfolio_summary_omits_accounts_with_no_data_as_of(temp_db):
    """Honest omission, never back-filling a later value into an earlier
    period (accounting-invariants: never fabricate a figure to fill a gap)."""
    async with get_session() as session:
        acct, stmt = await _make_account(
            session, institution_type="etrade", account_type="individual_brokerage", suffix="21",
        )
        await repo.bulk_create_balance_snapshots(session, [
            {"account_id": acct.id, "statement_id": stmt.id,
             "snapshot_date": date(2026, 6, 15), "total_value": "5000.00"},
        ])

    async with get_session() as session:
        summary = await investment_portfolio_summary(session, as_of=date(2026, 1, 31))
        allocation = await allocation_by_account(session, as_of=date(2026, 1, 31))

    assert summary["accounts"] == []
    assert summary["total_portfolio_value"] == 0.0
    assert allocation == []


async def test_allocation_uses_same_as_of_denominator_as_summary(temp_db):
    """Allocation % must never mix an as-of numerator with a latest-ever
    denominator — a classic percentage-denominator error."""
    async with get_session() as session:
        acct_a, stmt_a = await _make_account(
            session, institution_type="etrade", account_type="individual_brokerage", suffix="22",
        )
        acct_b, stmt_b = await _make_account(
            session, institution_type="morgan_stanley", account_type="advisory", suffix="23",
        )
        await repo.bulk_create_balance_snapshots(session, [
            {"account_id": acct_a.id, "statement_id": stmt_a.id,
             "snapshot_date": date(2026, 1, 15), "total_value": "3000.00"},
            {"account_id": acct_b.id, "statement_id": stmt_b.id,
             "snapshot_date": date(2026, 1, 15), "total_value": "1000.00"},
            # Later values that must NOT leak into an as-of-January reading.
            {"account_id": acct_a.id, "statement_id": stmt_a.id,
             "snapshot_date": date(2026, 6, 15), "total_value": "9000.00"},
        ])

    async with get_session() as session:
        allocation = await allocation_by_account(session, as_of=date(2026, 1, 31))

    by_pct = sorted(a["pct_of_portfolio"] for a in allocation)
    assert by_pct == [25.0, 75.0]
    assert sum(a["pct_of_portfolio"] for a in allocation) == pytest.approx(100.0)


async def test_top_holdings_resolve_as_of_end_date(temp_db):
    async with get_session() as session:
        acct, old_stmt = await _make_account(
            session, institution_type="etrade", account_type="individual_brokerage", suffix="24",
        )
        # `_make_account`'s statement covers all of 2026; add an earlier one
        # that closed in January so "as of Jan 31" has something to resolve to.
        early_stmt = await repo.create_statement(
            session, document_id=old_stmt.document_id, institution_id=old_stmt.institution_id,
            institution_type="etrade", account_id=acct.id,
            account_type="individual_brokerage", statement_type="brokerage",
            period_start=date(2026, 1, 1), period_end=date(2026, 1, 31),
            extraction_status="success", overall_confidence=0.9, warnings="[]",
        )
        await repo.bulk_create_holdings(session, [
            {"account_id": acct.id, "statement_id": early_stmt.id, "symbol": "OLDPOS",
             "description": "Old Position Fund", "market_value": "100.00",
             "unrealized_gain_loss": "5.00", "cost_basis": "95.00"},
            {"account_id": acct.id, "statement_id": old_stmt.id, "symbol": "NEWPOS",
             "description": "New Position Fund", "market_value": "200.00",
             "unrealized_gain_loss": "9.00", "cost_basis": "191.00"},
        ])

    async with get_session() as session:
        as_of_jan = await top_holdings_by_value(session, as_of=date(2026, 1, 31))
        latest_ever = await top_holdings_by_value(session)

    assert [h["symbol"] for h in as_of_jan] == ["OLDPOS"]
    assert [h["symbol"] for h in latest_ever] == ["NEWPOS"]


async def test_get_investments_dashboard_headline_matches_selected_period(temp_db):
    """End-to-end: the whole payload is anchored to one period — no mixing a
    period-filtered balance_history with an as-of-today headline value."""
    async with get_session() as session:
        acct, stmt = await _make_account(
            session, institution_type="etrade", account_type="individual_brokerage", suffix="25",
        )
        await repo.bulk_create_balance_snapshots(session, [
            {"account_id": acct.id, "statement_id": stmt.id,
             "snapshot_date": date(2026, 1, 15), "total_value": "4000.00"},
            {"account_id": acct.id, "statement_id": stmt.id,
             "snapshot_date": date(2026, 6, 15), "total_value": "5000.00"},
        ])

    payload = await get_investments_dashboard(
        start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
    )
    assert payload["portfolio_summary"]["total_portfolio_value"] == 4000.0
    assert [r["date"] for r in payload["balance_history"]] == ["2026-01-15"]

    unfiltered = await get_investments_dashboard()
    assert unfiltered["portfolio_summary"]["total_portfolio_value"] == 5000.0
