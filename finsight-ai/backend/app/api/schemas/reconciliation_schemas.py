"""Pydantic schemas for the reconciliation API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class CheckResultResponse(BaseModel):
    check_id: str
    name: str
    status: str          # CheckStatus value
    severity: str        # CheckSeverity value
    message: str
    expected: Optional[str]
    actual: Optional[str]
    delta: Optional[str]
    tolerance: Optional[str]


class ReconciliationResultResponse(BaseModel):
    id: str
    ingestion_job_id: str
    staged_statement_id: str
    status: str                  # ReconciliationStatus value
    integrity_score: float
    run_number: int
    checks: List[CheckResultResponse]
    checks_total: int
    checks_passed: int
    checks_failed: int
    checks_skipped: int
    checks_critical: int
    checks_warning: int
    review_items_created: int
    ran_at: datetime
    duration_ms: Optional[int]


class RunReconciliationRequest(BaseModel):
    """Trigger reconciliation for a specific staged statement."""
    staged_statement_id: str
    job_id: str


class JobReconciliationSummary(BaseModel):
    """Aggregated reconciliation status across all statements in a job."""
    job_id: str
    results: List[ReconciliationResultResponse]
    overall_integrity_score: float    # Average across all statements
    any_critical_failures: bool
    any_warnings: bool
    total_review_items_created: int
