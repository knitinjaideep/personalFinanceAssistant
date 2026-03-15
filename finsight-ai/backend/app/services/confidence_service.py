"""
ConfidenceService — document and field-level confidence aggregation.

Converts raw 0.0–1.0 per-field confidence scores from ExtractionResult into:
  - A single overall_confidence float for the document
  - A ConfidenceTier (HIGH / MEDIUM / LOW / NEEDS_REVIEW) for UI display
  - A DocumentConfidenceSummary with display label, color, and warnings

Design decisions:
- Missing optional fields degrade confidence gently (weighted penalty).
- Missing required fields degrade confidence severely.
- ExtractionStatus.PARTIAL always produces at most MEDIUM tier.
- ExtractionStatus.FAILED always produces NEEDS_REVIEW regardless of scores.
- Deterministic extraction (regex/table) with was_found=True contributes
  full confidence; LLM extraction with was_found=True contributes its score.
- This service is stateless and synchronous — it operates on in-memory
  ExtractionResult objects only.
"""

from __future__ import annotations

import uuid

from app.domain.entities import DocumentConfidenceSummary, ExtractionResult, FieldConfidence
from app.domain.enums import ConfidenceTier, ExtractionStatus


# Fields considered required for a meaningful statement extraction.
# Missing any of these triggers a severe penalty.
_REQUIRED_FIELDS: frozenset[str] = frozenset(
    {
        "period_start",
        "period_end",
        "institution_type",
        "account_type",
    }
)

# Confidence thresholds for tier assignment.
_THRESHOLD_HIGH: float = 0.80
_THRESHOLD_MEDIUM: float = 0.50
_THRESHOLD_LOW: float = 0.25

# How much to penalize each missing required vs optional field.
_REQUIRED_MISSING_PENALTY: float = 0.15
_OPTIONAL_MISSING_PENALTY: float = 0.03


class ConfidenceService:
    """
    Computes document-level confidence summaries from extraction results.

    Usage:
        svc = ConfidenceService()
        summary = svc.compute(extraction_result)
    """

    def compute(self, result: ExtractionResult) -> DocumentConfidenceSummary:
        """
        Compute a DocumentConfidenceSummary from an ExtractionResult.

        Args:
            result: The output of an institution agent's extraction run.

        Returns:
            DocumentConfidenceSummary with tier, display label, and warnings.
        """
        # Short-circuit on hard failure — nothing to aggregate.
        if result.status == ExtractionStatus.FAILED:
            return DocumentConfidenceSummary(
                document_id=result.document_id,
                overall_confidence=0.0,
                tier=ConfidenceTier.NEEDS_REVIEW,
                extraction_status=result.status,
                display_label="Extraction Failed",
                display_color="red",
                warnings=list(result.errors) + list(result.warnings),
            )

        field_confidences = result.field_confidences
        warnings: list[str] = list(result.warnings)

        # ── Aggregate field scores ─────────────────────────────────────────────
        fields_found = sum(1 for f in field_confidences if f.was_found)
        fields_missing = sum(1 for f in field_confidences if not f.was_found)
        fields_low_confidence = sum(
            1 for f in field_confidences if f.was_found and f.confidence < 0.50
        )

        # Start from the agent's self-reported overall confidence if available.
        # Fall back to computing from field scores.
        if result.overall_confidence > 0.0:
            base_score = result.overall_confidence
        elif field_confidences:
            found_scores = [f.confidence for f in field_confidences if f.was_found]
            base_score = sum(found_scores) / len(found_scores) if found_scores else 0.0
        else:
            # No fields reported — treat as low but not zero (document was parsed)
            base_score = 0.30

        # ── Apply penalties for missing fields ─────────────────────────────────
        penalty = 0.0
        for field_name in result.missing_fields:
            if field_name in _REQUIRED_FIELDS:
                penalty += _REQUIRED_MISSING_PENALTY
                warnings.append(f"Required field missing: {field_name}")
            else:
                penalty += _OPTIONAL_MISSING_PENALTY

        overall = max(0.0, min(1.0, base_score - penalty))

        # ── Cap score for PARTIAL status ───────────────────────────────────────
        if result.status == ExtractionStatus.PARTIAL:
            # Partial extraction cannot be HIGH confidence regardless of scores
            overall = min(overall, _THRESHOLD_MEDIUM - 0.01)
            warnings.append(
                "Document was partially extracted — some fields may be missing."
            )

        # ── Assign tier ────────────────────────────────────────────────────────
        tier = _score_to_tier(overall)

        # ── Build display label and color ──────────────────────────────────────
        label, color = _tier_to_display(tier, result.status)

        return DocumentConfidenceSummary(
            document_id=result.document_id,
            overall_confidence=round(overall, 4),
            tier=tier,
            extraction_status=result.status,
            fields_found=fields_found,
            fields_missing=fields_missing,
            fields_low_confidence=fields_low_confidence,
            display_label=label,
            display_color=color,
            warnings=warnings,
        )

    def compute_from_fields(
        self,
        document_id: uuid.UUID,
        field_confidences: list[FieldConfidence],
        extraction_status: ExtractionStatus = ExtractionStatus.SUCCESS,
        missing_fields: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> DocumentConfidenceSummary:
        """
        Convenience method to compute a summary directly from field lists
        without constructing a full ExtractionResult.
        """
        result = ExtractionResult(
            document_id=document_id,
            institution_type="unknown",  # type: ignore[arg-type]
            status=extraction_status,
            field_confidences=field_confidences,
            missing_fields=missing_fields or [],
            warnings=warnings or [],
        )
        return self.compute(result)


# ── Private helpers ────────────────────────────────────────────────────────────

def _score_to_tier(score: float) -> ConfidenceTier:
    if score >= _THRESHOLD_HIGH:
        return ConfidenceTier.HIGH
    if score >= _THRESHOLD_MEDIUM:
        return ConfidenceTier.MEDIUM
    if score >= _THRESHOLD_LOW:
        return ConfidenceTier.LOW
    return ConfidenceTier.NEEDS_REVIEW


def _tier_to_display(
    tier: ConfidenceTier, status: ExtractionStatus
) -> tuple[str, str]:
    """Return (display_label, display_color) for a tier + status combination."""
    if status == ExtractionStatus.FAILED:
        return "Extraction Failed", "red"
    if status == ExtractionStatus.PARTIAL or tier == ConfidenceTier.NEEDS_REVIEW:
        return "Needs Review", "red"
    if tier == ConfidenceTier.HIGH:
        return "High Confidence", "green"
    if tier == ConfidenceTier.MEDIUM:
        return "Medium Confidence", "yellow"
    return "Low Confidence", "red"
