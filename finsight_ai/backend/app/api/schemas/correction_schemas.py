"""
Pydantic schemas for the Correction Store API — Phase 2.5.

These schemas define the request and response contracts for:
  GET  /api/v1/corrections                  List corrections (filterable)
  GET  /api/v1/corrections/hints            Hints for an extraction field
  GET  /api/v1/corrections/calibration      Confidence penalties for a field set
  GET  /api/v1/corrections/record/{id}      Correction history for a staged record
  GET  /api/v1/corrections/job/{job_id}     All corrections for an ingestion job
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ── Response models ────────────────────────────────────────────────────────────

class CorrectionResponse(BaseModel):
    """
    Serialized view of a single ``FieldCorrectionModel`` row.

    Returned in list endpoints and the record history drawer.
    """

    id: str
    institution_type: str
    record_type: str
    field_name: str
    staged_record_id: str
    ingestion_job_id: str
    original_value: Any
    corrected_value: Any
    correction_reason: str | None = None
    original_confidence: float
    reviewed_by: str
    corrected_at: str
    """ISO-8601 timestamp."""


class CorrectionListResponse(BaseModel):
    """Paginated list of corrections."""

    corrections: list[CorrectionResponse]
    total: int
    limit: int
    offset: int


class CorrectionHintResponse(BaseModel):
    """
    A single extraction hint derived from a prior correction.

    Returned by ``GET /corrections/hints`` and consumed by the extraction
    agent to bias its outputs for the same field on a new document.
    """

    field_name: str
    original_value: Any
    """What the extractor originally produced."""

    corrected_value: Any
    """What the user corrected it to — the preferred value."""

    correction_reason: str | None = None
    institution_type: str
    record_type: str
    corrected_at: str
    """ISO-8601 timestamp — most recent first."""


class HintsResponse(BaseModel):
    """Response envelope for the hints endpoint."""

    institution_type: str
    record_type: str
    field_name: str
    hints: list[CorrectionHintResponse]
    hint_count: int


class FieldCalibrationResponse(BaseModel):
    """Confidence calibration data for a single field."""

    field_name: str
    correction_count: int
    penalty: float
    """Negative float: applies as confidence × (1.0 + penalty)."""

    calibrated_example: str
    """Human-readable example: '0.90 → 0.85' for a 5% penalty."""


class CalibrationResponse(BaseModel):
    """Response envelope for the calibration endpoint."""

    institution_type: str
    record_type: str
    calibrations: list[FieldCalibrationResponse]
    uncorrected_fields_note: str = (
        "Fields absent from this list have no recorded corrections "
        "and retain their original extraction confidence."
    )


class RecordCorrectionHistoryResponse(BaseModel):
    """Full correction history for a single staged record."""

    staged_record_id: str
    corrections: list[CorrectionResponse]
    correction_count: int


class JobCorrectionsResponse(BaseModel):
    """All corrections made during a single ingestion job."""

    ingestion_job_id: str
    corrections: list[CorrectionResponse]
    correction_count: int
    corrected_fields: list[str]
    """Deduplicated list of field names that were corrected in this job."""
