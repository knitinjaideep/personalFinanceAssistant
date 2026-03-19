"""
CorrectionService — Phase 2.5 correction store.

Responsibilities
================

1. **record()** — Journal every field-level edit a user makes during review.
   Called by ``ReviewService.correct()`` after the field is applied to the
   staged record.  One correction row is written per edited field.

2. **get_hints()** — Return prior corrections for a given
   (institution, record_type, field_name) as a list of
   ``CorrectionHint`` objects.  These are injected into the extraction
   prompt so the institution agent can learn from past mistakes without
   full model fine-tuning.

3. **get_calibration()** — Return a confidence penalty map for each field
   of a given (institution, record_type).  Fields with high correction
   rates receive a negative delta (−0.05 per correction, capped at −0.5)
   that the extraction confidence is multiplied against.

4. **list_for_record()** — Return the full correction history for a single
   staged record (used in the review drawer).

5. **list_for_job()** — Return all corrections made during an ingestion job
   (used in the job audit trail).

6. **list_for_institution()** — Paginated list of all corrections for an
   institution (used in the correction explorer page).

Design decisions
----------------
- Corrections are append-only.  Rows are never updated after creation.
- Monetary values enter as strings (Decimal-safe) and are stored as JSON.
- Any JSON-serialisable value is accepted for ``original_value`` /
  ``corrected_value`` — the caller passes Python objects; this service
  encodes them.
- Calibration uses a simple linear penalty; confidence calibration hooks
  for more sophisticated Bayesian updates are left for future work.
- The service is stateless; it takes a session at construction time.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.correction_repository import CorrectionRepository
from app.database.staged_models import FieldCorrectionModel

logger = structlog.get_logger(__name__)

# Confidence penalty per correction occurrence (linear penalty)
_PENALTY_PER_CORRECTION: float = 0.05
# Maximum cumulative penalty — confidence never drops below 0.5 × baseline
_MAX_PENALTY: float = 0.5


def _encode(value: Any) -> str:
    """JSON-encode a value for storage in the corrections journal."""
    try:
        return json.dumps(value, default=str)
    except Exception:
        return json.dumps(str(value))


@dataclass
class CorrectionHint:
    """
    A single prior correction example for a field.

    Returned by ``get_hints()`` to be injected into extraction prompts.
    The extraction agent should show these examples to the LLM to bias
    future outputs toward user-approved values.
    """

    field_name: str
    original_value: Any
    corrected_value: Any
    correction_reason: str | None
    institution_type: str
    record_type: str
    corrected_at: str
    """ISO-8601 string — for display only."""


@dataclass
class FieldCalibration:
    """
    Confidence calibration data for a single field.

    ``penalty`` is a negative float in [−_MAX_PENALTY, 0].
    The caller should multiply the raw extraction confidence by
    ``(1.0 + penalty)`` to get a calibrated confidence.
    """

    field_name: str
    correction_count: int
    penalty: float
    """Negative float: correction_count × −_PENALTY_PER_CORRECTION, capped at −_MAX_PENALTY."""


@dataclass
class CorrectionRecord:
    """Lightweight domain representation of a ``FieldCorrectionModel`` row."""

    id: str
    institution_type: str
    record_type: str
    field_name: str
    staged_record_id: str
    ingestion_job_id: str
    original_value: Any
    corrected_value: Any
    correction_reason: str | None
    original_confidence: float
    reviewed_by: str
    corrected_at: str


class CorrectionService:
    """
    Orchestrates the correction journal: write, read, and calibration.

    Injected with a DB session at construction time.  Stateless beyond
    the session — safe to construct per-request.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = CorrectionRepository(session)

    # ── Write ──────────────────────────────────────────────────────────────────

    async def record(
        self,
        *,
        institution_type: str,
        record_type: str,
        field_name: str,
        staged_record_id: str,
        ingestion_job_id: str,
        original_value: Any,
        corrected_value: Any,
        original_confidence: float = 1.0,
        correction_reason: str | None = None,
        reviewed_by: str = "user",
    ) -> CorrectionRecord:
        """
        Journal a single field correction.

        Args:
            institution_type: e.g. 'morgan_stanley'
            record_type: e.g. 'staged_transaction' (ReviewItemType value)
            field_name: e.g. 'amount'
            staged_record_id: PK of the staged row that was corrected
            ingestion_job_id: FK to ingestion_jobs.id
            original_value: Value before correction (any JSON-serialisable type)
            corrected_value: Value after correction
            original_confidence: Extraction confidence score at correction time
            correction_reason: Optional free-text from the reviewer
            reviewed_by: Identifier for the reviewer (default: 'user')

        Returns:
            ``CorrectionRecord`` domain object representing the new row.
        """
        model = FieldCorrectionModel(
            institution_type=institution_type,
            record_type=record_type,
            field_name=field_name,
            staged_record_id=staged_record_id,
            ingestion_job_id=ingestion_job_id,
            original_value=_encode(original_value),
            corrected_value=_encode(corrected_value),
            correction_reason=correction_reason,
            original_confidence=original_confidence,
            reviewed_by=reviewed_by,
        )
        saved = await self._repo.create(model)

        logger.info(
            "correction.recorded",
            id=saved.id,
            institution=institution_type,
            record_type=record_type,
            field_name=field_name,
            staged_record_id=staged_record_id,
        )

        return self._to_record(saved)

    async def record_bulk(
        self,
        *,
        institution_type: str,
        record_type: str,
        staged_record_id: str,
        ingestion_job_id: str,
        field_updates: dict[str, Any],
        original_values: dict[str, Any],
        original_confidence: float = 1.0,
        correction_reason: str | None = None,
        reviewed_by: str = "user",
    ) -> list[CorrectionRecord]:
        """
        Journal multiple field corrections from a single ``CorrectRequest``.

        One row is created per key in ``field_updates``.  If the original
        value for a field is not in ``original_values``, it is stored as null.

        Args:
            field_updates: ``{field_name: new_value}`` dict from the API request.
            original_values: ``{field_name: old_value}`` dict from the staged record.
        """
        models: list[FieldCorrectionModel] = []
        for field_name, new_val in field_updates.items():
            orig_val = original_values.get(field_name)
            models.append(
                FieldCorrectionModel(
                    institution_type=institution_type,
                    record_type=record_type,
                    field_name=field_name,
                    staged_record_id=staged_record_id,
                    ingestion_job_id=ingestion_job_id,
                    original_value=_encode(orig_val),
                    corrected_value=_encode(new_val),
                    correction_reason=correction_reason,
                    original_confidence=original_confidence,
                    reviewed_by=reviewed_by,
                )
            )

        if not models:
            return []

        saved = await self._repo.bulk_create(models)
        logger.info(
            "correction.bulk_recorded",
            institution=institution_type,
            record_type=record_type,
            staged_record_id=staged_record_id,
            field_count=len(saved),
        )
        return [self._to_record(m) for m in saved]

    # ── Read — hints ───────────────────────────────────────────────────────────

    async def get_hints(
        self,
        institution_type: str,
        record_type: str,
        field_name: str,
        limit: int = 5,
    ) -> list[CorrectionHint]:
        """
        Return recent correction examples for a (institution, record_type, field_name).

        These are injected into the extraction prompt as few-shot corrections
        so the extractor can learn from past mistakes without model training.

        Args:
            institution_type: e.g. 'morgan_stanley'
            record_type: e.g. 'staged_transaction'
            field_name: e.g. 'amount'
            limit: Max examples to return (default 5 — keep prompts manageable).

        Returns:
            List of ``CorrectionHint`` ordered by most recent first.
        """
        rows = await self._repo.list_hints(
            institution_type=institution_type,
            record_type=record_type,
            field_name=field_name,
            limit=limit,
        )
        return [self._to_hint(r) for r in rows]

    async def get_all_hints_for_institution(
        self,
        institution_type: str,
        record_type: str,
        limit_per_field: int = 3,
    ) -> dict[str, list[CorrectionHint]]:
        """
        Return hints for every corrected field for an institution + record type.

        Returns a dict of ``{field_name: [CorrectionHint, ...]}``.
        Used to build the full correction context block for an extraction prompt.
        """
        # Fetch recent corrections for the institution/record_type
        rows = await self._repo.list_for_institution(
            institution_type=institution_type,
            limit=200,
        )
        # Filter to the requested record type and group by field_name
        grouped: dict[str, list[CorrectionHint]] = {}
        for row in rows:
            if row.record_type != record_type:
                continue
            fn = row.field_name
            if fn not in grouped:
                grouped[fn] = []
            if len(grouped[fn]) < limit_per_field:
                grouped[fn].append(self._to_hint(row))
        return grouped

    # ── Read — calibration ─────────────────────────────────────────────────────

    async def get_calibration(
        self,
        institution_type: str,
        record_type: str,
    ) -> dict[str, FieldCalibration]:
        """
        Return confidence calibration data for every field of an institution + record type.

        The caller multiplies each field's raw extraction confidence by
        ``(1.0 + calibration[field_name].penalty)`` to get a calibrated value.

        Fields that have never been corrected are not included in the result;
        callers should treat missing keys as a penalty of 0.0.

        Returns:
            Dict of ``{field_name: FieldCalibration}``.
        """
        counts = await self._repo.count_by_field(
            institution_type=institution_type,
            record_type=record_type,
        )
        calibrations: dict[str, FieldCalibration] = {}
        for field_name, count in counts.items():
            raw_penalty = count * -_PENALTY_PER_CORRECTION
            capped_penalty = max(raw_penalty, -_MAX_PENALTY)
            calibrations[field_name] = FieldCalibration(
                field_name=field_name,
                correction_count=count,
                penalty=capped_penalty,
            )
        return calibrations

    # ── Read — history ─────────────────────────────────────────────────────────

    async def list_for_record(
        self, staged_record_id: str
    ) -> list[CorrectionRecord]:
        """Return all corrections for a specific staged record."""
        rows = await self._repo.list_for_record(staged_record_id)
        return [self._to_record(r) for r in rows]

    async def list_for_job(
        self, ingestion_job_id: str
    ) -> list[CorrectionRecord]:
        """Return all corrections made during an ingestion job."""
        rows = await self._repo.list_for_job(ingestion_job_id)
        return [self._to_record(r) for r in rows]

    async def list_for_institution(
        self,
        institution_type: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CorrectionRecord]:
        """Return paginated corrections for an institution."""
        rows = await self._repo.list_for_institution(
            institution_type=institution_type,
            limit=limit,
            offset=offset,
        )
        return [self._to_record(r) for r in rows]

    async def total_count(self, institution_type: str | None = None) -> int:
        """Total number of corrections, optionally filtered by institution."""
        return await self._repo.total_count(institution_type=institution_type)

    # ── Mapping helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _to_record(model: FieldCorrectionModel) -> CorrectionRecord:
        """Map a DB model to the domain record type."""
        try:
            orig = json.loads(model.original_value)
        except Exception:
            orig = model.original_value
        try:
            corrected = json.loads(model.corrected_value)
        except Exception:
            corrected = model.corrected_value

        return CorrectionRecord(
            id=model.id,
            institution_type=model.institution_type,
            record_type=model.record_type,
            field_name=model.field_name,
            staged_record_id=model.staged_record_id,
            ingestion_job_id=model.ingestion_job_id,
            original_value=orig,
            corrected_value=corrected,
            correction_reason=model.correction_reason,
            original_confidence=model.original_confidence,
            reviewed_by=model.reviewed_by,
            corrected_at=model.corrected_at.isoformat(),
        )

    @staticmethod
    def _to_hint(model: FieldCorrectionModel) -> CorrectionHint:
        """Map a DB model to the hint type used in extraction prompts."""
        try:
            orig = json.loads(model.original_value)
        except Exception:
            orig = model.original_value
        try:
            corrected = json.loads(model.corrected_value)
        except Exception:
            corrected = model.corrected_value

        return CorrectionHint(
            field_name=model.field_name,
            original_value=orig,
            corrected_value=corrected,
            correction_reason=model.correction_reason,
            institution_type=model.institution_type,
            record_type=model.record_type,
            corrected_at=model.corrected_at.isoformat(),
        )
