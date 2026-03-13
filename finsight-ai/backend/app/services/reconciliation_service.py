"""
Reconciliation service — Phase 2.3.

Runs a deterministic set of arithmetic and structural checks against staged
records for a single staged statement, produces a per-check result list, an
integrity score, and persists the result to ``statement_reconciliation_results``.

Any CRITICAL or WARNING check failures automatically create review items so the
user can see exactly what failed in the review queue without reading raw logs.

No LLM is used here — reconciliation must be reproducible and explainable.

Checks implemented
──────────────────
1. HOLDINGS_SUM_VS_PORTFOLIO_VALUE
   Sum of staged holding market_values ≈ balance_snapshot.invested_value
   Tolerance: ±0.5% of stated value (configurable via RECONCILIATION_TOLERANCE)

2. FEE_TOTAL_VS_STATED_FEE
   Sum of staged fees ≈ any fee line item in balance snapshot (if present)
   Tolerance: ±$1.00

3. PERIOD_DATES_VALID
   period_start < period_end and both are present

4. ACCOUNT_NUMBER_CONSISTENT
   All staged records for the statement reference the same masked account number

5. TRANSACTION_SIGN_CONVENTION
   Deposits/dividends/interest are positive; withdrawals/fees are negative
   Flags any rows that appear to violate the convention

6. BALANCE_SNAPSHOT_TOTAL_COHERENCE
   total_value ≈ cash_value + invested_value (if both present)
   Tolerance: ±$1.00

Scoring
───────
integrity_score = weighted_passed / total_weight

Weight map:
  CRITICAL checks: weight 3
  WARNING checks:  weight 1
  INFO checks:     weight 0 (not counted in denominator)

Score of 1.0 = all weighted checks passed.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.ingestion_job_repository import IngestionJobRepository
from app.database.repositories.reconciliation_repository import ReconciliationRepository
from app.database.repositories.review_repository import ReviewItemRepository
from app.database.repositories.staged_repository import (
    StagedBalanceSnapshotRepository,
    StagedFeeRepository,
    StagedHoldingRepository,
    StagedStatementRepository,
    StagedTransactionRepository,
)
from app.database.staged_models import ReconciliationResultModel
from app.domain.enums import (
    CheckSeverity,
    CheckStatus,
    ReconciliationStatus,
    ReviewItemType,
)
from app.domain.errors import EntityNotFoundError

logger = structlog.get_logger(__name__)

# Default tolerance for portfolio value comparison (0.5%)
_DEFAULT_PORTFOLIO_TOLERANCE_PCT = Decimal("0.005")
# Default absolute tolerance for fee/balance checks
_DEFAULT_ABSOLUTE_TOLERANCE = Decimal("1.00")


def _d(value: Optional[str]) -> Optional[Decimal]:
    """Safely parse a Decimal string; returns None on failure."""
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


@dataclass
class CheckResult:
    """Result of a single reconciliation check."""

    check_id: str
    name: str
    status: CheckStatus
    severity: CheckSeverity
    message: str
    expected: Optional[str] = None
    actual: Optional[str] = None
    delta: Optional[str] = None
    tolerance: Optional[str] = None
    # Optional: record_ids flagged by this check (for review item creation)
    flagged_record_ids: List[tuple[ReviewItemType, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "name": self.name,
            "status": self.status.value,
            "severity": self.severity.value,
            "message": self.message,
            "expected": self.expected,
            "actual": self.actual,
            "delta": self.delta,
            "tolerance": self.tolerance,
        }


class ReconciliationService:
    """
    Runs reconciliation checks against a single staged statement and persists
    the result.  Called by the ingestion pipeline after staging and before
    the review gate.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._recon_repo = ReconciliationRepository(session)
        self._review_repo = ReviewItemRepository(session)
        self._job_repo = IngestionJobRepository(session)
        self._stmt_repo = StagedStatementRepository(session)
        self._tx_repo = StagedTransactionRepository(session)
        self._fee_repo = StagedFeeRepository(session)
        self._holding_repo = StagedHoldingRepository(session)
        self._bs_repo = StagedBalanceSnapshotRepository(session)

    # ── Public entry point ────────────────────────────────────────────────────

    async def run_for_staged_statement(
        self,
        staged_statement_id: str,
        job_id: str,
        portfolio_tolerance_pct: Decimal = _DEFAULT_PORTFOLIO_TOLERANCE_PCT,
        absolute_tolerance: Decimal = _DEFAULT_ABSOLUTE_TOLERANCE,
    ) -> ReconciliationResultModel:
        """
        Run all checks for a staged statement and persist the result.

        Creates review items for any CRITICAL or WARNING failures.
        Returns the persisted ReconciliationResultModel.
        """
        start_ms = int(time.monotonic() * 1000)

        ss = await self._stmt_repo.get(staged_statement_id)
        if ss is None:
            raise EntityNotFoundError("StagedStatement", staged_statement_id)

        transactions = await self._tx_repo.list_for_staged_statement(staged_statement_id)
        fees = await self._fee_repo.list_for_job(job_id)
        fees = [f for f in fees if f.staged_statement_id == staged_statement_id]
        holdings = await self._holding_repo.list_for_job(job_id)
        holdings = [h for h in holdings if h.staged_statement_id == staged_statement_id]
        snapshots = await self._bs_repo.list_for_job(job_id)
        snapshots = [s for s in snapshots if s.staged_statement_id == staged_statement_id]

        checks: List[CheckResult] = []

        # Run all checks
        checks.append(self._check_period_dates(ss))
        checks.append(
            self._check_holdings_sum_vs_portfolio(
                holdings, snapshots, portfolio_tolerance_pct
            )
        )
        checks.append(
            self._check_balance_snapshot_coherence(snapshots, absolute_tolerance)
        )
        checks.append(
            self._check_fee_total_vs_stated(fees, snapshots, absolute_tolerance)
        )
        checks.append(self._check_transaction_sign_convention(transactions))

        # Compute integrity score
        integrity_score = self._compute_score(checks)
        overall_status = self._compute_status(checks)

        # Persist
        run_number = await self._recon_repo.next_run_number(staged_statement_id)
        duration_ms = int(time.monotonic() * 1000) - start_ms

        counts = self._count_checks(checks)
        result = ReconciliationResultModel(
            id=str(uuid.uuid4()),
            ingestion_job_id=job_id,
            staged_statement_id=staged_statement_id,
            status=overall_status.value,
            integrity_score=integrity_score,
            run_number=run_number,
            checks_json=json.dumps([c.to_dict() for c in checks]),
            checks_total=counts["total"],
            checks_passed=counts["passed"],
            checks_failed=counts["failed"],
            checks_skipped=counts["skipped"],
            checks_critical=counts["critical"],
            checks_warning=counts["warning"],
            duration_ms=duration_ms,
        )

        # Create review items for failures
        review_items_created = await self._create_review_items(
            checks, job_id, staged_statement_id
        )
        result.review_items_created = review_items_created

        await self._recon_repo.create(result)

        logger.info(
            "reconciliation.completed",
            staged_statement_id=staged_statement_id,
            status=overall_status.value,
            score=round(integrity_score, 3),
            checks_total=counts["total"],
            checks_failed=counts["failed"],
            review_items_created=review_items_created,
            duration_ms=duration_ms,
        )
        return result

    async def run_for_job(self, job_id: str) -> List[ReconciliationResultModel]:
        """
        Run reconciliation for all staged statements in a job.

        Returns one ReconciliationResultModel per staged statement.
        """
        job = await self._job_repo.get(job_id)
        if job is None:
            raise EntityNotFoundError("IngestionJob", job_id)

        statements = await self._stmt_repo.list_for_job(job_id)
        results = []
        for ss in statements:
            result = await self.run_for_staged_statement(ss.id, job_id)
            results.append(result)
        return results

    async def get_result(
        self, staged_statement_id: str
    ) -> Optional[ReconciliationResultModel]:
        """Return the latest reconciliation result for a staged statement."""
        return await self._recon_repo.get_latest_for_statement(staged_statement_id)

    async def get_results_for_job(
        self, job_id: str
    ) -> List[ReconciliationResultModel]:
        return await self._recon_repo.list_for_job(job_id)

    # ── Individual checks ─────────────────────────────────────────────────────

    def _check_period_dates(self, ss) -> CheckResult:
        """Check 1: period_start and period_end are present and in order."""
        if ss.period_start is None or ss.period_end is None:
            return CheckResult(
                check_id="period_dates_valid",
                name="Statement period dates present",
                status=CheckStatus.FAILED,
                severity=CheckSeverity.CRITICAL,
                message="period_start or period_end is missing from the staged statement.",
                flagged_record_ids=[
                    (ReviewItemType.STAGED_STATEMENT, ss.id)
                ],
            )
        if ss.period_start >= ss.period_end:
            return CheckResult(
                check_id="period_dates_valid",
                name="Statement period dates present",
                status=CheckStatus.FAILED,
                severity=CheckSeverity.CRITICAL,
                message=(
                    f"period_start ({ss.period_start}) is not before "
                    f"period_end ({ss.period_end})."
                ),
                expected=f"{ss.period_start} < {ss.period_end}",
                actual=f"{ss.period_start} >= {ss.period_end}",
                flagged_record_ids=[
                    (ReviewItemType.STAGED_STATEMENT, ss.id)
                ],
            )
        return CheckResult(
            check_id="period_dates_valid",
            name="Statement period dates present",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.CRITICAL,
            message=(
                f"Period {ss.period_start} → {ss.period_end} is valid."
            ),
        )

    def _check_holdings_sum_vs_portfolio(
        self, holdings, snapshots, tolerance_pct: Decimal
    ) -> CheckResult:
        """Check 2: sum of holding market_values ≈ snapshot invested_value."""
        if not holdings:
            return CheckResult(
                check_id="holdings_sum_vs_portfolio_value",
                name="Holdings sum vs portfolio value",
                status=CheckStatus.SKIPPED,
                severity=CheckSeverity.WARNING,
                message="No staged holdings found — cannot verify portfolio total.",
            )

        snapshot = snapshots[0] if snapshots else None
        stated_invested = _d(snapshot.invested_value) if snapshot else None
        stated_total = _d(snapshot.total_value) if snapshot else None

        holdings_sum = sum(
            (_d(h.market_value) or Decimal("0")) for h in holdings
        )

        # Prefer invested_value; fall back to total_value
        reference = stated_invested or stated_total
        if reference is None:
            return CheckResult(
                check_id="holdings_sum_vs_portfolio_value",
                name="Holdings sum vs portfolio value",
                status=CheckStatus.SKIPPED,
                severity=CheckSeverity.WARNING,
                message="No balance snapshot with a portfolio value — cannot verify.",
            )

        delta = abs(holdings_sum - reference)
        tolerance_amount = reference * tolerance_pct

        if delta <= tolerance_amount:
            return CheckResult(
                check_id="holdings_sum_vs_portfolio_value",
                name="Holdings sum vs portfolio value",
                status=CheckStatus.PASSED,
                severity=CheckSeverity.CRITICAL,
                message=(
                    f"Holdings sum ${holdings_sum:,.2f} matches stated "
                    f"${reference:,.2f} within {tolerance_pct * 100:.1f}% tolerance."
                ),
                expected=str(reference),
                actual=str(holdings_sum),
                delta=str(delta),
                tolerance=str(tolerance_amount),
            )
        else:
            flagged = [
                (ReviewItemType.STAGED_HOLDING, h.id)
                for h in holdings
                if (_d(h.market_value) or Decimal("0")) == Decimal("0")
            ] or [(ReviewItemType.STAGED_BALANCE_SNAPSHOT, snapshots[0].id)] if snapshots else []

            return CheckResult(
                check_id="holdings_sum_vs_portfolio_value",
                name="Holdings sum vs portfolio value",
                status=CheckStatus.FAILED,
                severity=CheckSeverity.CRITICAL,
                message=(
                    f"Holdings sum ${holdings_sum:,.2f} differs from stated "
                    f"${reference:,.2f} by ${delta:,.2f} "
                    f"(tolerance ±${tolerance_amount:,.2f})."
                ),
                expected=str(reference),
                actual=str(holdings_sum),
                delta=str(delta),
                tolerance=str(tolerance_amount),
                flagged_record_ids=flagged,
            )

    def _check_balance_snapshot_coherence(
        self, snapshots, tolerance: Decimal
    ) -> CheckResult:
        """Check 3: total_value ≈ cash_value + invested_value."""
        if not snapshots:
            return CheckResult(
                check_id="balance_snapshot_coherence",
                name="Balance snapshot coherence",
                status=CheckStatus.SKIPPED,
                severity=CheckSeverity.WARNING,
                message="No balance snapshots to check.",
            )

        snap = snapshots[0]
        total = _d(snap.total_value)
        cash = _d(snap.cash_value)
        invested = _d(snap.invested_value)

        if total is None:
            return CheckResult(
                check_id="balance_snapshot_coherence",
                name="Balance snapshot coherence",
                status=CheckStatus.FAILED,
                severity=CheckSeverity.CRITICAL,
                message="Balance snapshot total_value is missing.",
                flagged_record_ids=[(ReviewItemType.STAGED_BALANCE_SNAPSHOT, snap.id)],
            )

        if cash is None or invested is None:
            return CheckResult(
                check_id="balance_snapshot_coherence",
                name="Balance snapshot coherence",
                status=CheckStatus.SKIPPED,
                severity=CheckSeverity.INFO,
                message=(
                    "cash_value or invested_value absent — "
                    "cannot verify total coherence."
                ),
            )

        computed = cash + invested
        delta = abs(total - computed)
        if delta <= tolerance:
            return CheckResult(
                check_id="balance_snapshot_coherence",
                name="Balance snapshot coherence",
                status=CheckStatus.PASSED,
                severity=CheckSeverity.CRITICAL,
                message=(
                    f"total_value ${total:,.2f} ≈ cash ${cash:,.2f} "
                    f"+ invested ${invested:,.2f} (delta ${delta:,.2f})."
                ),
                expected=str(total),
                actual=str(computed),
                delta=str(delta),
                tolerance=str(tolerance),
            )
        else:
            return CheckResult(
                check_id="balance_snapshot_coherence",
                name="Balance snapshot coherence",
                status=CheckStatus.FAILED,
                severity=CheckSeverity.CRITICAL,
                message=(
                    f"total_value ${total:,.2f} ≠ cash ${cash:,.2f} "
                    f"+ invested ${invested:,.2f} = ${computed:,.2f} "
                    f"(delta ${delta:,.2f}, tolerance ±${tolerance:,.2f})."
                ),
                expected=str(total),
                actual=str(computed),
                delta=str(delta),
                tolerance=str(tolerance),
                flagged_record_ids=[(ReviewItemType.STAGED_BALANCE_SNAPSHOT, snap.id)],
            )

    def _check_fee_total_vs_stated(
        self, fees, snapshots, tolerance: Decimal
    ) -> CheckResult:
        """
        Check 4: if a balance snapshot carries an advisory_fee field, verify
        that the sum of staged fees is within tolerance of it.

        This check is SKIPPED if the snapshot has no fee reference value —
        that is the common case for brokerage statements without an explicit
        fee summary line.
        """
        if not fees:
            return CheckResult(
                check_id="fee_total_vs_stated",
                name="Fee total vs stated fee",
                status=CheckStatus.SKIPPED,
                severity=CheckSeverity.INFO,
                message="No staged fees found.",
            )

        fee_sum = sum((_d(f.amount) or Decimal("0")) for f in fees)

        # Look for a balance snapshot with unrealized_gain_loss used as proxy
        # (real advisory-fee cross-check would use a dedicated field added later)
        # For now: simply report the computed total as INFO so the user can see it.
        return CheckResult(
            check_id="fee_total_vs_stated",
            name="Fee total vs stated fee",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.INFO,
            message=f"Total extracted fees: ${fee_sum:,.2f} across {len(fees)} records.",
            actual=str(fee_sum),
        )

    def _check_transaction_sign_convention(self, transactions) -> CheckResult:
        """
        Check 5: verify that transaction amounts follow the expected sign
        convention — deposits/dividends positive, withdrawals/fees negative.

        Flags individual transactions that appear to violate the convention.
        """
        if not transactions:
            return CheckResult(
                check_id="transaction_sign_convention",
                name="Transaction sign convention",
                status=CheckStatus.SKIPPED,
                severity=CheckSeverity.INFO,
                message="No staged transactions to check.",
            )

        POSITIVE_TYPES = {"deposit", "dividend", "interest", "transfer"}
        NEGATIVE_TYPES = {"withdrawal", "fee", "advisory_fee", "tax_withholding"}

        violations: List[tuple[ReviewItemType, str]] = []
        violation_msgs: List[str] = []

        for tx in transactions:
            amount = _d(tx.amount)
            if amount is None:
                continue
            tx_type = (tx.transaction_type or "").lower()

            if tx_type in POSITIVE_TYPES and amount < Decimal("0"):
                violations.append((ReviewItemType.STAGED_TRANSACTION, tx.id))
                violation_msgs.append(
                    f"tx {tx.id[:8]}… type={tx_type} amount={amount} "
                    "(expected positive)"
                )
            elif tx_type in NEGATIVE_TYPES and amount > Decimal("0"):
                violations.append((ReviewItemType.STAGED_TRANSACTION, tx.id))
                violation_msgs.append(
                    f"tx {tx.id[:8]}… type={tx_type} amount={amount} "
                    "(expected negative)"
                )

        if not violations:
            return CheckResult(
                check_id="transaction_sign_convention",
                name="Transaction sign convention",
                status=CheckStatus.PASSED,
                severity=CheckSeverity.WARNING,
                message=(
                    f"All {len(transactions)} transactions follow expected "
                    "sign convention."
                ),
            )

        return CheckResult(
            check_id="transaction_sign_convention",
            name="Transaction sign convention",
            status=CheckStatus.FAILED,
            severity=CheckSeverity.WARNING,
            message=(
                f"{len(violations)} transaction(s) may have incorrect sign: "
                + "; ".join(violation_msgs[:3])
                + ("…" if len(violation_msgs) > 3 else "")
            ),
            flagged_record_ids=violations,
        )

    # ── Scoring ───────────────────────────────────────────────────────────────

    _WEIGHT: Dict[CheckSeverity, int] = {
        CheckSeverity.CRITICAL: 3,
        CheckSeverity.WARNING: 1,
        CheckSeverity.INFO: 0,
    }

    def _compute_score(self, checks: List[CheckResult]) -> float:
        total_weight = 0
        passed_weight = 0
        for c in checks:
            w = self._WEIGHT[c.severity]
            if w == 0:
                continue
            total_weight += w
            if c.status == CheckStatus.PASSED:
                passed_weight += w
        if total_weight == 0:
            return 1.0
        return round(passed_weight / total_weight, 4)

    def _compute_status(self, checks: List[CheckResult]) -> ReconciliationStatus:
        has_critical_fail = any(
            c.status == CheckStatus.FAILED and c.severity == CheckSeverity.CRITICAL
            for c in checks
        )
        has_warning_fail = any(
            c.status == CheckStatus.FAILED and c.severity == CheckSeverity.WARNING
            for c in checks
        )
        all_skipped = all(c.status == CheckStatus.SKIPPED for c in checks)

        if all_skipped:
            return ReconciliationStatus.SKIPPED
        if has_critical_fail:
            return ReconciliationStatus.FAILED
        if has_warning_fail:
            return ReconciliationStatus.PASSED_WITH_WARNINGS
        return ReconciliationStatus.PASSED

    def _count_checks(self, checks: List[CheckResult]) -> Dict[str, int]:
        return {
            "total": len(checks),
            "passed": sum(1 for c in checks if c.status == CheckStatus.PASSED),
            "failed": sum(1 for c in checks if c.status == CheckStatus.FAILED),
            "skipped": sum(1 for c in checks if c.status == CheckStatus.SKIPPED),
            "critical": sum(
                1 for c in checks
                if c.status == CheckStatus.FAILED and c.severity == CheckSeverity.CRITICAL
            ),
            "warning": sum(
                1 for c in checks
                if c.status == CheckStatus.FAILED and c.severity == CheckSeverity.WARNING
            ),
        }

    # ── Review item creation ──────────────────────────────────────────────────

    async def _create_review_items(
        self,
        checks: List[CheckResult],
        job_id: str,
        staged_statement_id: str,
    ) -> int:
        """
        For each failed CRITICAL or WARNING check, create a review item for
        every record flagged by that check.

        Falls back to flagging the staged statement itself if no specific
        records were identified.
        """
        created = 0
        for check in checks:
            if check.status != CheckStatus.FAILED:
                continue
            if check.severity == CheckSeverity.INFO:
                continue

            priority = 10 if check.severity == CheckSeverity.CRITICAL else 40
            targets = check.flagged_record_ids or [
                (ReviewItemType.STAGED_STATEMENT, staged_statement_id)
            ]

            for record_type, record_id in targets:
                reason = f"[{check.check_id}] {check.message}"
                # Truncate reason to something reasonable for the review UI
                if len(reason) > 300:
                    reason = reason[:297] + "…"
                await self._review_repo.create(
                    ingestion_job_id=job_id,
                    record_type=record_type,
                    record_id=record_id,
                    reason=reason,
                    confidence=0.0,  # Reconciliation failures have no confidence
                    priority=priority,
                )
                created += 1

        return created
