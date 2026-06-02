"""
Tests for the ingestion repair layer:

- documents stats counts + status normalization
- ingestion health detects parsed docs with zero transactions
- reprocess clears stale child rows for ONLY the target document
- reprocess updates status correctly
- processing count is 0 when no docs are actively processing
"""

from __future__ import annotations

from datetime import date

import pytest

from app.api.documents import document_stats, normalize_status
from app.db import repositories as repo
from app.db.engine import get_session
from app.services import reprocess_service as rs


# ── Status normalization ──────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("parsed", "parsed"), ("PARSED", "parsed"), ("completed", "parsed"),
        ("processed", "parsed"), ("success", "parsed"),
        ("processing", "processing"), ("PROCESSING", "processing"), ("in_progress", "processing"),
        ("uploaded", "uploaded"), ("pending", "uploaded"),
        ("failed", "failed"), ("error", "failed"),
        (None, "uploaded"), ("", "uploaded"), ("weird", "uploaded"),
    ],
)
def test_normalize_status(raw, expected):
    assert normalize_status(raw) == expected


# ── Seeding helpers ───────────────────────────────────────────────────────────

async def _make_document(doc_id: str, status: str = "parsed", institution: str = "amex") -> None:
    async with get_session() as session:
        await repo.create_document(
            session,
            id=doc_id,
            original_filename=f"{doc_id}.pdf",
            stored_filename=f"{doc_id}.pdf",
            file_path=f"/tmp/{doc_id}.pdf",
            file_size_bytes=1,
            mime_type="application/pdf",
            status=status,
            institution_type=institution,
        )


async def _attach_statement_with_txns(doc_id: str, n_txns: int, institution: str = "amex") -> str:
    """Create institution/account/statement and n transactions for a document."""
    async with get_session() as session:
        inst = await repo.get_or_create_institution(session, institution, institution.title())
        acct = await repo.get_or_create_account(
            session, institution_id=inst.id, institution_type=institution,
            account_number_masked="****0001", account_type="credit_card",
        )
        stmt = await repo.create_statement(
            session,
            document_id=doc_id, institution_id=inst.id, institution_type=institution,
            account_id=acct.id, account_type="credit_card", statement_type="credit_card",
            period_start=date(2025, 1, 1), period_end=date(2025, 1, 31),
            extraction_status="success", overall_confidence=0.9, warnings="[]",
        )
        if n_txns:
            await repo.bulk_create_transactions(session, [
                {
                    "account_id": acct.id, "statement_id": stmt.id,
                    "transaction_date": date(2025, 1, 5 + i),
                    "description": f"TXN {i}", "amount": "-10.00",
                    "transaction_type": "purchase", "category": "groceries",
                }
                for i in range(n_txns)
            ])
        return stmt.id


async def _attach_chunks(doc_id: str, n: int, institution: str = "amex") -> None:
    async with get_session() as session:
        await repo.bulk_create_text_chunks(session, [
            {
                "document_id": doc_id, "chunk_index": i, "content": f"chunk {i}",
                "page_number": 1, "institution_type": institution,
            }
            for i in range(n)
        ])


# ── Stats counts ──────────────────────────────────────────────────────────────

async def test_stats_counts_and_processing_zero(temp_db):
    await _make_document("d_parsed", status="parsed")
    await _make_document("d_parsed2", status="completed")  # normalizes to parsed
    await _make_document("d_uploaded", status="uploaded")
    await _make_document("d_failed", status="failed")

    stats = await document_stats()
    assert stats.total == 4
    assert stats.parsed == 2          # parsed + completed
    assert stats.uploaded == 1
    assert stats.failed == 1
    assert stats.processing == 0      # nothing is processing → 0, not stuck


async def test_stats_processing_counts_only_real_processing(temp_db):
    await _make_document("d1", status="parsed")
    await _make_document("d2", status="processing")
    await _make_document("d3", status="in_progress")  # normalizes to processing

    stats = await document_stats()
    assert stats.processing == 2
    assert stats.parsed == 1


# ── Ingestion health ──────────────────────────────────────────────────────────

async def test_health_detects_parsed_with_zero_transactions(temp_db):
    # Parsed doc with chunks but NO transactions → should be flagged incomplete.
    await _make_document("incomplete", status="parsed")
    await _attach_statement_with_txns("incomplete", n_txns=0)
    await _attach_chunks("incomplete", n=5)

    # Parsed doc that is complete (txns + chunks).
    await _make_document("complete", status="parsed")
    await _attach_statement_with_txns("complete", n_txns=3)
    await _attach_chunks("complete", n=5)

    health = await rs.ingestion_health()
    summary = health["summary"]
    assert summary["total_documents"] == 2
    assert summary["missing_transactions"] == 1
    assert summary["complete_documents"] == 1
    assert summary["incomplete_documents"] == 1

    flagged = {d["document_id"]: d for d in health["documents"]}
    assert "incomplete" in flagged
    assert rs.ISSUE_ZERO_TRANSACTIONS in flagged["incomplete"]["issues"]
    assert flagged["incomplete"]["recommended_action"] == "reprocess"
    assert "complete" not in flagged  # complete doc has no issues


async def test_find_documents_missing_data(temp_db):
    await _make_document("good", status="parsed")
    await _attach_statement_with_txns("good", n_txns=2)
    await _attach_chunks("good", n=3)

    await _make_document("bad", status="parsed")
    await _attach_statement_with_txns("bad", n_txns=0)
    await _attach_chunks("bad", n=3)

    missing = await rs.find_documents_missing_data()
    ids = {d.document_id for d in missing}
    assert "bad" in ids
    assert "good" not in ids


# ── Reprocess child-row cleanup isolation ─────────────────────────────────────

async def test_clear_children_only_targets_one_document(temp_db):
    # Two documents, each with a statement + transactions + chunks.
    await _make_document("doc_a", status="parsed")
    await _attach_statement_with_txns("doc_a", n_txns=3)
    await _attach_chunks("doc_a", n=4)

    await _make_document("doc_b", status="parsed")
    await _attach_statement_with_txns("doc_b", n_txns=5)
    await _attach_chunks("doc_b", n=6)

    # Clear ONLY doc_a's children.
    result = await rs.clear_document_child_records("doc_a")
    assert result["transactions_removed"] == 3

    async with get_session() as session:
        # doc_a fully cleared of children…
        assert await repo.count_transactions_for_document(session, "doc_a") == 0
        assert await repo.count_chunks_for_document(session, "doc_a") == 0
        assert await repo.get_statements_for_document(session, "doc_a") == []
        # …but doc_b is untouched.
        assert await repo.count_transactions_for_document(session, "doc_b") == 5
        assert await repo.count_chunks_for_document(session, "doc_b") == 6
        assert len(await repo.get_statements_for_document(session, "doc_b")) == 1

        # The document row itself must still exist.
        doc_a = await repo.get_document(session, "doc_a")
        assert doc_a is not None
        assert doc_a.original_filename == "doc_a.pdf"


async def test_reprocess_missing_file_sets_failed(temp_db):
    # Document points at a non-existent PDF → reprocess should mark it failed,
    # not raise, and must not delete the document row.
    await _make_document("ghost", status="parsed")
    await _attach_statement_with_txns("ghost", n_txns=0)

    result = await rs.reprocess_document("ghost")
    assert result.ok is False
    assert result.status_after == "failed"
    assert "not found" in (result.error or "").lower()

    async with get_session() as session:
        doc = await repo.get_document(session, "ghost")
        assert normalize_status(doc.status) == "failed"
        # stale child rows were cleared even though reprocess could not complete
        assert await repo.count_transactions_for_document(session, "ghost") == 0


# ── Reprocess updates status using a real PDF parse (stubbed parser) ──────────

async def test_reprocess_repopulates_and_marks_parsed(temp_db, tmp_path, monkeypatch):
    """End-to-end-ish: stub parse/classify/extract so reprocess persists fresh rows
    and flips status to parsed without needing a real PDF or Ollama."""
    from app.domain.entities import ExtractedTransaction, ParsedStatement
    from app.parsers.base import ParsedDocument, ParsedPage

    # Create a real (tiny) file so the path-exists check passes.
    pdf = tmp_path / "stub.pdf"
    pdf.write_bytes(b"%PDF-1.4 stub")

    await _make_document("repro", status="failed")
    # Point the doc's file_path at our stub file.
    async with get_session() as session:
        await repo.update_document(session, "repro", file_path=str(pdf))

    fake_doc = ParsedDocument(
        file_path=str(pdf), page_count=1,
        pages=[ParsedPage(page_number=1, raw_text="JACK'S SUPER FOODTOWN $10.00", tables=[])],
        metadata={},
    )

    async def fake_parse(_path):
        return fake_doc

    class FakeParser:
        institution_type = "amex"
        async def extract(self, _doc):
            return ParsedStatement(
                institution_type="amex", account_type="credit_card",
                statement_type="credit_card", account_number_masked="****0001",
                period_start=date(2025, 3, 1), period_end=date(2025, 3, 31),
                confidence=0.9,
                transactions=[ExtractedTransaction(
                    transaction_date=date(2025, 3, 5), description="JACK'S SUPER FOODTOWN",
                    amount="-10.00", transaction_type="purchase", category="groceries",
                )],
            )

    class FakeRegistry:
        def detect_institution(self, _text):
            return FakeParser(), 0.99

    monkeypatch.setattr(rs, "parse_pdf", fake_parse)
    monkeypatch.setattr(rs, "get_parser_registry", lambda: FakeRegistry())

    result = await rs.reprocess_document("repro")
    assert result.ok is True
    assert result.status_before == "failed"
    assert result.status_after == "parsed"
    assert result.transactions == 1

    async with get_session() as session:
        doc = await repo.get_document(session, "repro")
        assert normalize_status(doc.status) == "parsed"
        assert await repo.count_transactions_for_document(session, "repro") == 1


# ── Account disambiguation (Prime vs Freedom vs Sapphire) ─────────────────────

async def test_unknown_masked_accounts_split_by_name(temp_db):
    """Chase cards with no parsed masked number must not collapse into one account."""
    async with get_session() as session:
        inst = await repo.get_or_create_institution(session, "chase", "Chase")

        prime = await repo.get_or_create_account(
            session, institution_id=inst.id, institution_type="chase",
            account_number_masked="unknown", account_type="credit_card",
            account_name="Prime Visa",
        )
        freedom = await repo.get_or_create_account(
            session, institution_id=inst.id, institution_type="chase",
            account_number_masked="unknown", account_type="credit_card",
            account_name="Freedom Unlimited",
        )
        # Same name again → must reuse, not create a second row.
        prime2 = await repo.get_or_create_account(
            session, institution_id=inst.id, institution_type="chase",
            account_number_masked="unknown", account_type="credit_card",
            account_name="Prime Visa",
        )

    assert prime.id != freedom.id        # distinct cards → distinct accounts
    assert prime.id == prime2.id          # same card → same account
    assert prime.account_name == "Prime Visa"


async def test_real_masked_number_still_matches_regardless_of_name(temp_db):
    """When a real masked number exists, it remains the identity key."""
    async with get_session() as session:
        inst = await repo.get_or_create_institution(session, "chase", "Chase")
        a1 = await repo.get_or_create_account(
            session, institution_id=inst.id, institution_type="chase",
            account_number_masked="****1234", account_type="checking",
            account_name="Checking",
        )
        a2 = await repo.get_or_create_account(
            session, institution_id=inst.id, institution_type="chase",
            account_number_masked="****1234", account_type="checking",
            account_name="Checking",
        )
    assert a1.id == a2.id


async def _attach_holdings_statement(doc_id: str, institution: str = "morgan_stanley",
                                     *, with_balance: bool = True) -> str:
    """Holdings/advisory statement: no transactions, but a balance snapshot."""
    async with get_session() as session:
        inst = await repo.get_or_create_institution(session, institution, institution.title())
        acct = await repo.get_or_create_account(
            session, institution_id=inst.id, institution_type=institution,
            account_number_masked="****9999", account_type="advisory",
            account_name="Advisory",
        )
        stmt = await repo.create_statement(
            session,
            document_id=doc_id, institution_id=inst.id, institution_type=institution,
            account_id=acct.id, account_type="advisory", statement_type="advisory",
            period_start=date(2025, 5, 1), period_end=date(2025, 5, 31),
            extraction_status="success", overall_confidence=0.9, warnings="[]",
        )
        if with_balance:
            await repo.bulk_create_balance_snapshots(session, [{
                "account_id": acct.id, "statement_id": stmt.id,
                "snapshot_date": date(2025, 5, 31), "total_value": "123456.00",
            }])
        return stmt.id


async def test_holdings_statement_with_balance_is_complete(temp_db):
    """A Morgan Stanley advisory statement with balances but zero transactions
    must NOT be flagged incomplete (zero transactions is expected there)."""
    await _make_document("ms_ok", status="parsed", institution="morgan_stanley")
    await _attach_holdings_statement("ms_ok", with_balance=True)
    await _attach_chunks("ms_ok", n=5, institution="morgan_stanley")

    health = await rs.ingestion_health()
    flagged = {d["document_id"] for d in health["documents"]}
    assert "ms_ok" not in flagged
    assert health["summary"]["missing_transactions"] == 0
    assert health["summary"]["incomplete_documents"] == 0

    missing = await rs.find_documents_missing_data()
    assert "ms_ok" not in {d.document_id for d in missing}


async def test_holdings_statement_with_no_data_is_incomplete(temp_db):
    """But a holdings-style statement with NO transactions, balances, holdings, or
    fees genuinely extracted nothing → still flagged."""
    await _make_document("ms_empty", status="parsed", institution="morgan_stanley")
    await _attach_holdings_statement("ms_empty", with_balance=False)
    await _attach_chunks("ms_empty", n=5, institution="morgan_stanley")

    missing = await rs.find_documents_missing_data()
    assert "ms_empty" in {d.document_id for d in missing}


async def test_credit_card_zero_transactions_still_flagged(temp_db):
    """Regression guard: a credit-card statement with zero transactions is still
    a defect (transaction-style institution)."""
    await _make_document("amex_empty", status="parsed", institution="amex")
    await _attach_statement_with_txns("amex_empty", n_txns=0, institution="amex")
    await _attach_chunks("amex_empty", n=5, institution="amex")

    missing = await rs.find_documents_missing_data()
    assert "amex_empty" in {d.document_id for d in missing}
