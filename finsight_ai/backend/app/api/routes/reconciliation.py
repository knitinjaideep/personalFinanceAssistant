"""
Reconciliation API routes — Phase 2.3.
Mounted under /api/v1/reconciliation.

GET  /jobs/{job_id}                       — all results for a job
GET  /statements/{staged_statement_id}    — latest result for one statement
POST /run                                 — trigger reconciliation on demand
POST /jobs/{job_id}/run-all              — run for every staged statement in a job
"""

from __future__ import annotations

import json
from typing import List

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.reconciliation_schemas import (
    CheckResultResponse,
    JobReconciliationSummary,
    ReconciliationResultResponse,
    RunReconciliationRequest,
)
from app.database.engine import get_db_session
from app.database.staged_models import ReconciliationResultModel
from app.domain.errors import EntityNotFoundError
from app.services.reconciliation_service import ReconciliationService

logger = structlog.get_logger(__name__)
router = APIRouter()


def get_reconciliation_service(
    session: AsyncSession = Depends(get_db_session),
) -> ReconciliationService:
    return ReconciliationService(session)


def _to_response(r: ReconciliationResultModel) -> ReconciliationResultResponse:
    checks_raw = json.loads(r.checks_json or "[]")
    checks = [
        CheckResultResponse(
            check_id=c["check_id"],
            name=c["name"],
            status=c["status"],
            severity=c["severity"],
            message=c["message"],
            expected=c.get("expected"),
            actual=c.get("actual"),
            delta=c.get("delta"),
            tolerance=c.get("tolerance"),
        )
        for c in checks_raw
    ]
    return ReconciliationResultResponse(
        id=r.id,
        ingestion_job_id=r.ingestion_job_id,
        staged_statement_id=r.staged_statement_id,
        status=r.status,
        integrity_score=r.integrity_score,
        run_number=r.run_number,
        checks=checks,
        checks_total=r.checks_total,
        checks_passed=r.checks_passed,
        checks_failed=r.checks_failed,
        checks_skipped=r.checks_skipped,
        checks_critical=r.checks_critical,
        checks_warning=r.checks_warning,
        review_items_created=r.review_items_created,
        ran_at=r.ran_at,
        duration_ms=r.duration_ms,
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobReconciliationSummary,
    summary="Reconciliation summary for an ingestion job",
)
async def get_job_reconciliation(
    job_id: str,
    service: ReconciliationService = Depends(get_reconciliation_service),
) -> JobReconciliationSummary:
    results = await service.get_results_for_job(job_id)
    responses = [_to_response(r) for r in results]

    overall_score = (
        sum(r.integrity_score for r in responses) / len(responses)
        if responses else 0.0
    )
    return JobReconciliationSummary(
        job_id=job_id,
        results=responses,
        overall_integrity_score=round(overall_score, 4),
        any_critical_failures=any(r.checks_critical > 0 for r in responses),
        any_warnings=any(r.checks_warning > 0 for r in responses),
        total_review_items_created=sum(r.review_items_created for r in responses),
    )


@router.get(
    "/statements/{staged_statement_id}",
    response_model=ReconciliationResultResponse,
    summary="Latest reconciliation result for a staged statement",
)
async def get_statement_reconciliation(
    staged_statement_id: str,
    service: ReconciliationService = Depends(get_reconciliation_service),
) -> ReconciliationResultResponse:
    result = await service.get_result(staged_statement_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No reconciliation result found for statement {staged_statement_id}",
        )
    return _to_response(result)


@router.post(
    "/run",
    response_model=ReconciliationResultResponse,
    summary="Run reconciliation for a single staged statement",
)
async def run_reconciliation(
    body: RunReconciliationRequest,
    service: ReconciliationService = Depends(get_reconciliation_service),
) -> ReconciliationResultResponse:
    try:
        result = await service.run_for_staged_statement(
            staged_statement_id=body.staged_statement_id,
            job_id=body.job_id,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error("reconciliation.run_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Reconciliation failed: {exc}")
    return _to_response(result)


@router.post(
    "/jobs/{job_id}/run-all",
    response_model=JobReconciliationSummary,
    summary="Run reconciliation for all staged statements in a job",
)
async def run_all_for_job(
    job_id: str,
    service: ReconciliationService = Depends(get_reconciliation_service),
) -> JobReconciliationSummary:
    try:
        results = await service.run_for_job(job_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error("reconciliation.run_all_failed", job_id=job_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Reconciliation failed: {exc}")

    responses = [_to_response(r) for r in results]
    overall_score = (
        sum(r.integrity_score for r in responses) / len(responses)
        if responses else 0.0
    )
    return JobReconciliationSummary(
        job_id=job_id,
        results=responses,
        overall_integrity_score=round(overall_score, 4),
        any_critical_failures=any(r.checks_critical > 0 for r in responses),
        any_warnings=any(r.checks_warning > 0 for r in responses),
        total_review_items_created=sum(r.review_items_created for r in responses),
    )
