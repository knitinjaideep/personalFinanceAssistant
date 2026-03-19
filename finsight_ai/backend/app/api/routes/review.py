"""
Review queue API routes — Phase 2.2.

All routes are under /api/v1/review (mounted in main.py).

Endpoints:
  GET  /queue                         — paginated pending items (global or job-scoped)
  GET  /jobs/{job_id}                 — job review summary
  GET  /records/{record_type}/{id}    — full staged record detail
  POST /approve                       — approve one item
  POST /correct                       — correct one item
  POST /reject                        — reject one item
  POST /skip                          — defer one item
  POST /bulk-approve                  — approve all pending for a job
  POST /jobs/{job_id}/promote         — promote approved records to canonical tables
"""

from __future__ import annotations

import json
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.review_schemas import (
    ApproveRequest,
    BulkApproveRequest,
    CorrectRequest,
    JobReviewSummary,
    PromotionResult,
    RejectRequest,
    ReviewItemResponse,
    ReviewQueueResponse,
    SkipRequest,
    StagedBalanceSnapshotDetail,
    StagedFeeDetail,
    StagedHoldingDetail,
    StagedStatementDetail,
    StagedTransactionDetail,
)
from app.database.engine import get_db_session
from app.database.staged_models import ReviewItemModel
from app.domain.enums import ReviewItemType
from app.domain.errors import EntityNotFoundError
from app.services.review_service import ReviewService

logger = structlog.get_logger(__name__)
router = APIRouter()


# ── Dependencies ───────────────────────────────────────────────────────────────

def get_review_service(
    session: AsyncSession = Depends(get_db_session),
) -> ReviewService:
    return ReviewService(session)


# ── Serialisation helpers ──────────────────────────────────────────────────────

def _item_to_response(item: ReviewItemModel) -> ReviewItemResponse:
    return ReviewItemResponse(
        id=item.id,
        ingestion_job_id=item.ingestion_job_id,
        record_type=item.record_type,
        record_id=item.record_id,
        status=item.status,
        reason=item.reason,
        priority=item.priority,
        confidence=item.confidence,
        resolved_at=item.resolved_at,
        resolution_action=item.resolution_action,
        resolution_notes=item.resolution_notes,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


# ── Queue ──────────────────────────────────────────────────────────────────────

@router.get("/queue", response_model=ReviewQueueResponse, summary="Get pending review queue")
async def get_review_queue(
    job_id: Optional[str] = Query(default=None, description="Scope to a single ingestion job"),
    record_type: Optional[str] = Query(default=None, description="Filter by record type"),
    limit: int = Query(default=100, ge=1, le=500),
    service: ReviewService = Depends(get_review_service),
) -> ReviewQueueResponse:
    """
    Return pending review items ordered by priority then confidence.

    Optionally scoped to a single job or record type.
    """
    rt: Optional[ReviewItemType] = None
    if record_type:
        try:
            rt = ReviewItemType(record_type)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid record_type '{record_type}'. "
                       f"Valid values: {[e.value for e in ReviewItemType]}",
            )

    items, total = await service.fetch_queue(job_id=job_id, record_type=rt, limit=limit)
    return ReviewQueueResponse(
        items=[_item_to_response(i) for i in items],
        total_pending=total,
        job_id=job_id,
    )


# ── Job summary ────────────────────────────────────────────────────────────────

@router.get(
    "/jobs/{job_id}",
    response_model=JobReviewSummary,
    summary="Review summary for an ingestion job",
)
async def get_job_review_summary(
    job_id: str,
    service: ReviewService = Depends(get_review_service),
) -> JobReviewSummary:
    try:
        job = await service.get_job_summary(job_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    counts = await service.count_staged_records(job_id)
    _, pending_count = await service.fetch_queue(job_id=job_id, limit=1)

    return JobReviewSummary(
        job_id=job.id,
        document_id=job.document_id,
        job_status=job.status,
        current_stage=job.current_stage,
        pending_review_count=pending_count,
        total_review_count=sum(counts.values()),
        staged_statements=counts["staged_statements"],
        staged_transactions=counts["staged_transactions"],
        staged_fees=counts["staged_fees"],
        staged_holdings=counts["staged_holdings"],
        staged_balance_snapshots=counts["staged_balance_snapshots"],
        warnings=json.loads(job.warnings_json or "[]"),
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


# ── Staged record detail ───────────────────────────────────────────────────────

@router.get(
    "/records/staged_statement/{record_id}",
    response_model=StagedStatementDetail,
    summary="Get staged statement detail",
)
async def get_staged_statement(
    record_id: str,
    service: ReviewService = Depends(get_review_service),
) -> StagedStatementDetail:
    try:
        r = await service.get_staged_statement(record_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return StagedStatementDetail(
        id=r.id,
        ingestion_job_id=r.ingestion_job_id,
        document_id=r.document_id,
        institution_type=r.institution_type,
        account_number_masked=r.account_number_masked,
        account_name=r.account_name,
        account_type=r.account_type,
        statement_type=r.statement_type,
        period_start=r.period_start,
        period_end=r.period_end,
        currency=r.currency,
        status=r.status,
        overall_confidence=r.overall_confidence,
        field_flags=json.loads(r.field_flags_json or "{}"),
        reviewer_notes=r.reviewer_notes,
        reviewed_at=r.reviewed_at,
        extraction_notes=json.loads(r.extraction_notes_json or "[]"),
        source_pages=json.loads(r.source_pages_json or "[]"),
        canonical_statement_id=r.canonical_statement_id,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


@router.get(
    "/records/staged_transaction/{record_id}",
    response_model=StagedTransactionDetail,
    summary="Get staged transaction detail",
)
async def get_staged_transaction(
    record_id: str,
    service: ReviewService = Depends(get_review_service),
) -> StagedTransactionDetail:
    try:
        r = await service.get_staged_transaction(record_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return StagedTransactionDetail(
        id=r.id,
        ingestion_job_id=r.ingestion_job_id,
        staged_statement_id=r.staged_statement_id,
        transaction_date=r.transaction_date,
        settlement_date=r.settlement_date,
        description=r.description,
        transaction_type=r.transaction_type,
        amount=r.amount,
        currency=r.currency,
        quantity=r.quantity,
        price_per_unit=r.price_per_unit,
        symbol=r.symbol,
        status=r.status,
        confidence=r.confidence,
        field_flags=json.loads(r.field_flags_json or "{}"),
        reviewer_notes=r.reviewer_notes,
        reviewed_at=r.reviewed_at,
        source_page=r.source_page,
        source_section=r.source_section,
        canonical_transaction_id=r.canonical_transaction_id,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


@router.get(
    "/records/staged_fee/{record_id}",
    response_model=StagedFeeDetail,
    summary="Get staged fee detail",
)
async def get_staged_fee(
    record_id: str,
    service: ReviewService = Depends(get_review_service),
) -> StagedFeeDetail:
    try:
        r = await service.get_staged_fee(record_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return StagedFeeDetail(
        id=r.id,
        ingestion_job_id=r.ingestion_job_id,
        staged_statement_id=r.staged_statement_id,
        fee_date=r.fee_date,
        description=r.description,
        amount=r.amount,
        fee_category=r.fee_category,
        annualized_rate=r.annualized_rate,
        currency=r.currency,
        status=r.status,
        confidence=r.confidence,
        field_flags=json.loads(r.field_flags_json or "{}"),
        reviewer_notes=r.reviewer_notes,
        reviewed_at=r.reviewed_at,
        source_page=r.source_page,
        source_section=r.source_section,
        canonical_fee_id=r.canonical_fee_id,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


@router.get(
    "/records/staged_holding/{record_id}",
    response_model=StagedHoldingDetail,
    summary="Get staged holding detail",
)
async def get_staged_holding(
    record_id: str,
    service: ReviewService = Depends(get_review_service),
) -> StagedHoldingDetail:
    try:
        r = await service.get_staged_holding(record_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return StagedHoldingDetail(
        id=r.id,
        ingestion_job_id=r.ingestion_job_id,
        staged_statement_id=r.staged_statement_id,
        symbol=r.symbol,
        description=r.description,
        quantity=r.quantity,
        price=r.price,
        market_value=r.market_value,
        cost_basis=r.cost_basis,
        unrealized_gain_loss=r.unrealized_gain_loss,
        percent_of_portfolio=r.percent_of_portfolio,
        asset_class=r.asset_class,
        currency=r.currency,
        status=r.status,
        confidence=r.confidence,
        field_flags=json.loads(r.field_flags_json or "{}"),
        reviewer_notes=r.reviewer_notes,
        reviewed_at=r.reviewed_at,
        source_page=r.source_page,
        source_section=r.source_section,
        canonical_holding_id=r.canonical_holding_id,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


@router.get(
    "/records/staged_balance_snapshot/{record_id}",
    response_model=StagedBalanceSnapshotDetail,
    summary="Get staged balance snapshot detail",
)
async def get_staged_balance_snapshot(
    record_id: str,
    service: ReviewService = Depends(get_review_service),
) -> StagedBalanceSnapshotDetail:
    try:
        r = await service.get_staged_balance_snapshot(record_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return StagedBalanceSnapshotDetail(
        id=r.id,
        ingestion_job_id=r.ingestion_job_id,
        staged_statement_id=r.staged_statement_id,
        snapshot_date=r.snapshot_date,
        total_value=r.total_value,
        cash_value=r.cash_value,
        invested_value=r.invested_value,
        unrealized_gain_loss=r.unrealized_gain_loss,
        currency=r.currency,
        status=r.status,
        confidence=r.confidence,
        field_flags=json.loads(r.field_flags_json or "{}"),
        reviewer_notes=r.reviewer_notes,
        reviewed_at=r.reviewed_at,
        source_page=r.source_page,
        source_section=r.source_section,
        canonical_balance_snapshot_id=r.canonical_balance_snapshot_id,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


# ── Actions ────────────────────────────────────────────────────────────────────

@router.post(
    "/approve",
    response_model=ReviewItemResponse,
    summary="Approve a staged record",
)
async def approve_item(
    body: ApproveRequest,
    service: ReviewService = Depends(get_review_service),
) -> ReviewItemResponse:
    try:
        item = await service.approve(body.review_item_id, notes=body.notes)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _item_to_response(item)


@router.post(
    "/correct",
    response_model=ReviewItemResponse,
    summary="Correct fields on a staged record",
)
async def correct_item(
    body: CorrectRequest,
    service: ReviewService = Depends(get_review_service),
) -> ReviewItemResponse:
    try:
        item = await service.correct(
            body.review_item_id,
            field_updates=body.field_updates,
            notes=body.notes,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _item_to_response(item)


@router.post(
    "/reject",
    response_model=ReviewItemResponse,
    summary="Reject a staged record",
)
async def reject_item(
    body: RejectRequest,
    service: ReviewService = Depends(get_review_service),
) -> ReviewItemResponse:
    try:
        item = await service.reject(body.review_item_id, notes=body.notes)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _item_to_response(item)


@router.post(
    "/skip",
    response_model=ReviewItemResponse,
    summary="Skip (defer) a review item",
)
async def skip_item(
    body: SkipRequest,
    service: ReviewService = Depends(get_review_service),
) -> ReviewItemResponse:
    try:
        item = await service.skip(body.review_item_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _item_to_response(item)


@router.post(
    "/bulk-approve",
    summary="Approve all pending items for a job",
)
async def bulk_approve(
    body: BulkApproveRequest,
    service: ReviewService = Depends(get_review_service),
) -> dict:
    try:
        count = await service.bulk_approve(body.job_id, notes=body.notes)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"approved_count": count, "job_id": body.job_id}


# ── Promotion ──────────────────────────────────────────────────────────────────

@router.post(
    "/jobs/{job_id}/promote",
    response_model=PromotionResult,
    summary="Promote approved staged records to canonical tables",
)
async def promote_job(
    job_id: str,
    service: ReviewService = Depends(get_review_service),
) -> PromotionResult:
    """
    Promote all APPROVED / CORRECTED staged records for this job to the
    canonical Statement, Transaction, Fee, Holding, and BalanceSnapshot tables.

    Returns 409 if any review items are still PENDING.
    """
    try:
        result = await service.promote_job(job_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        # Pending items remain
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        logger.error("promotion.unexpected_error", job_id=job_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Promotion failed: {exc}")

    return PromotionResult(**result)
