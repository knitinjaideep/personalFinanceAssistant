"""
Correction Store endpoints — Phase 2.5.

Routes:
  GET  /api/v1/corrections                           List all corrections (paginated)
  GET  /api/v1/corrections/hints                     Get extraction hints for a field
  GET  /api/v1/corrections/calibration               Get confidence calibration for a field set
  GET  /api/v1/corrections/record/{staged_record_id} Correction history for a staged record
  GET  /api/v1/corrections/job/{job_id}              All corrections for an ingestion job

All endpoints are read-only.  Corrections are written exclusively through
the review queue (``POST /api/v1/review/items/{id}/correct``).

Design:
- The ``hints`` endpoint is the primary integration point for future extraction
  improvements.  The institution agent calls it before running extraction on
  a new document to prime its prompt with prior user corrections.
- The ``calibration`` endpoint is used by the confidence scoring layer to
  apply field-level penalty multipliers to raw extraction confidence scores.
- The record and job history endpoints power the review drawer and job audit trail.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.schemas.correction_schemas import (
    CalibrationResponse,
    CorrectionListResponse,
    CorrectionResponse,
    FieldCalibrationResponse,
    HintsResponse,
    CorrectionHintResponse,
    JobCorrectionsResponse,
    RecordCorrectionHistoryResponse,
)
from app.services.correction_service import CorrectionRecord, CorrectionService

logger = structlog.get_logger(__name__)
router = APIRouter()


def _get_correction_service(
    session: AsyncSession = Depends(get_session),
) -> CorrectionService:
    return CorrectionService(session)


def _to_response(rec: CorrectionRecord) -> CorrectionResponse:
    return CorrectionResponse(
        id=rec.id,
        institution_type=rec.institution_type,
        record_type=rec.record_type,
        field_name=rec.field_name,
        staged_record_id=rec.staged_record_id,
        ingestion_job_id=rec.ingestion_job_id,
        original_value=rec.original_value,
        corrected_value=rec.corrected_value,
        correction_reason=rec.correction_reason,
        original_confidence=rec.original_confidence,
        reviewed_by=rec.reviewed_by,
        corrected_at=rec.corrected_at,
    )


@router.get(
    "",
    response_model=CorrectionListResponse,
    summary="List all corrections, optionally filtered by institution",
)
async def list_corrections(
    institution_type: str | None = Query(
        default=None,
        description="Filter by institution (e.g. 'morgan_stanley')",
    ),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    svc: CorrectionService = Depends(_get_correction_service),
) -> CorrectionListResponse:
    """
    Return a paginated list of field corrections from the journal.

    Use this to:
    - Audit what the user has corrected across all documents.
    - Drive the Correction Explorer page.
    - Identify systematically wrong extraction fields per institution.
    """
    try:
        records = await svc.list_for_institution(
            institution_type=institution_type or "",
            limit=limit,
            offset=offset,
        ) if institution_type else []

        total = await svc.total_count(institution_type=institution_type)

        # If no institution filter, fall back to empty (full scan not yet
        # implemented — requires a CorrectionRepository.list_all() method).
        return CorrectionListResponse(
            corrections=[_to_response(r) for r in records],
            total=total,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        logger.exception("corrections.list_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to list corrections: {exc}")


@router.get(
    "/hints",
    response_model=HintsResponse,
    summary="Get extraction hints for a specific institution + record type + field",
)
async def get_hints(
    institution_type: str = Query(..., description="e.g. 'morgan_stanley'"),
    record_type: str = Query(..., description="e.g. 'staged_transaction'"),
    field_name: str = Query(..., description="e.g. 'amount'"),
    limit: int = Query(default=5, ge=1, le=20),
    svc: CorrectionService = Depends(_get_correction_service),
) -> HintsResponse:
    """
    Return recent correction examples for a (institution, record_type, field_name) key.

    These hints are injected into the extraction prompt so the institution
    agent can learn from past corrections without model fine-tuning.

    The extraction agent should present these as few-shot examples in its prompt:
    ```
    In past extractions for Morgan Stanley transactions, the 'amount' field
    was corrected as follows:
      - Extracted: "-500.00" → Corrected: "500.00" (reason: amount should be positive)
      - Extracted: "1250"    → Corrected: "1250.00" (reason: missing decimal)
    ```
    """
    try:
        hints = await svc.get_hints(
            institution_type=institution_type,
            record_type=record_type,
            field_name=field_name,
            limit=limit,
        )
        return HintsResponse(
            institution_type=institution_type,
            record_type=record_type,
            field_name=field_name,
            hints=[
                CorrectionHintResponse(
                    field_name=h.field_name,
                    original_value=h.original_value,
                    corrected_value=h.corrected_value,
                    correction_reason=h.correction_reason,
                    institution_type=h.institution_type,
                    record_type=h.record_type,
                    corrected_at=h.corrected_at,
                )
                for h in hints
            ],
            hint_count=len(hints),
        )
    except Exception as exc:
        logger.exception("corrections.hints_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to fetch hints: {exc}")


@router.get(
    "/calibration",
    response_model=CalibrationResponse,
    summary="Get confidence calibration penalties for an institution + record type",
)
async def get_calibration(
    institution_type: str = Query(..., description="e.g. 'morgan_stanley'"),
    record_type: str = Query(..., description="e.g. 'staged_transaction'"),
    svc: CorrectionService = Depends(_get_correction_service),
) -> CalibrationResponse:
    """
    Return confidence calibration data for every corrected field of an
    institution + record type combination.

    The caller should multiply each field's raw extraction confidence by
    ``(1.0 + penalty)`` to get a calibrated score.

    Example:
    - Field ``amount`` has been corrected 4 times → penalty = −0.20
    - Raw extraction confidence = 0.90 → calibrated = 0.90 × 0.80 = 0.72

    Fields not present in the response have no recorded corrections and
    should retain their original extraction confidence.
    """
    try:
        calibrations = await svc.get_calibration(
            institution_type=institution_type,
            record_type=record_type,
        )
        items: list[FieldCalibrationResponse] = []
        for field_name, cal in calibrations.items():
            example_raw = 0.90
            calibrated = round(example_raw * (1.0 + cal.penalty), 2)
            items.append(
                FieldCalibrationResponse(
                    field_name=field_name,
                    correction_count=cal.correction_count,
                    penalty=cal.penalty,
                    calibrated_example=f"{example_raw:.2f} → {calibrated:.2f}",
                )
            )
        # Sort by most corrections first
        items.sort(key=lambda x: x.correction_count, reverse=True)
        return CalibrationResponse(
            institution_type=institution_type,
            record_type=record_type,
            calibrations=items,
        )
    except Exception as exc:
        logger.exception("corrections.calibration_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to fetch calibration: {exc}")


@router.get(
    "/record/{staged_record_id}",
    response_model=RecordCorrectionHistoryResponse,
    summary="Get correction history for a specific staged record",
)
async def get_record_correction_history(
    staged_record_id: str,
    svc: CorrectionService = Depends(_get_correction_service),
) -> RecordCorrectionHistoryResponse:
    """
    Return all corrections ever made to a specific staged record.

    Used in the review drawer to show the user a full before/after
    history of every field edit, in chronological order.
    """
    try:
        records = await svc.list_for_record(staged_record_id)
        return RecordCorrectionHistoryResponse(
            staged_record_id=staged_record_id,
            corrections=[_to_response(r) for r in records],
            correction_count=len(records),
        )
    except Exception as exc:
        logger.exception(
            "corrections.record_history_error",
            staged_record_id=staged_record_id,
            error=str(exc),
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch correction history: {exc}"
        )


@router.get(
    "/job/{job_id}",
    response_model=JobCorrectionsResponse,
    summary="Get all corrections made during an ingestion job",
)
async def get_job_corrections(
    job_id: str,
    svc: CorrectionService = Depends(_get_correction_service),
) -> JobCorrectionsResponse:
    """
    Return all corrections made during a specific ingestion job.

    Used in the job audit trail to give an overview of how much the
    user had to correct after extraction, and which fields were most
    frequently corrected.

    The ``corrected_fields`` list is deduplicated and sorted — useful for
    the UI to highlight which fields had problems in this document.
    """
    try:
        records = await svc.list_for_job(job_id)
        corrected_fields = sorted({r.field_name for r in records})
        return JobCorrectionsResponse(
            ingestion_job_id=job_id,
            corrections=[_to_response(r) for r in records],
            correction_count=len(records),
            corrected_fields=corrected_fields,
        )
    except Exception as exc:
        logger.exception(
            "corrections.job_error",
            job_id=job_id,
            error=str(exc),
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch job corrections: {exc}"
        )
