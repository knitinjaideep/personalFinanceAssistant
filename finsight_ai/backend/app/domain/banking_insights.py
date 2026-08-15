"""
Deterministic Banking Insights for the Banking page (PR 10).

This module is deliberately pure and DB-free. It consumes facts already
computed by the Plan vs Actual engine, merchant driver aggregation, and
classification review queue, then ranks at most three user-facing insights.
No LLM call is made here; if narration is ever added later, these objects are
the immutable facts it must restyle rather than recompute.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.classification_review import TransactionReviewItem
from app.domain.plan_vs_actual import BucketDrift, DriftStatus, MerchantDriver, PlanVsActualResult
from app.domain.transaction_classification import MasterBucket

BankingInsightType = Literal[
    "merchant_overspend",
    "category_overspend",
    "persistent_wants_overspend",
    "unusual_spending_spike",
    "savings_shortfall",
    "recurring_charge_increase",
    "merchant_concentration",
    "classification_uncertainty",
    "positive_improvement",
]
InsightSeverity = Literal["positive", "info", "warning", "critical"]
InsightTone = Literal["good", "neutral", "warning", "danger"]

_CENTS = Decimal("0.01")
_MATERIALITY = Decimal("25.00")
_MERCHANT_CONCENTRATION_RATIO = Decimal("0.35")
_CONSUMPTION_BUCKETS = frozenset({MasterBucket.NEEDS, MasterBucket.WANTS})


class BankingInsightFact(BaseModel):
    """One auditable fact behind a Banking insight."""

    label: str
    value: str


class BankingInsight(BaseModel):
    """One deterministic insight shown on Banking."""

    model_config = ConfigDict(frozen=True)

    type: BankingInsightType
    severity: InsightSeverity
    tone: InsightTone
    title: str
    summary: str
    impact_amount: str | None
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    action: str
    supporting_facts: list[BankingInsightFact]
    rank_score: Decimal = Field(exclude=True)


class BankingInsightsResult(BaseModel):
    period: str
    insights: list[BankingInsight]


def _dec(value: str | None) -> Decimal | None:
    return Decimal(value) if value is not None else None


def _money(value: Decimal) -> str:
    value = value.copy_abs().quantize(_CENTS)
    if value == value.to_integral_value():
        return f"${value:,.0f}"
    return f"${value:,.2f}"


def _bucket_label(bucket: MasterBucket) -> str:
    return {
        MasterBucket.NEEDS: "Needs",
        MasterBucket.WANTS: "Wants",
        MasterBucket.SAVINGS: "Savings",
        MasterBucket.INVESTMENTS: "Investments",
        MasterBucket.UNCLASSIFIED: "Unclassified",
    }[bucket]


def _severity_for(status: DriftStatus, impact: Decimal) -> InsightSeverity:
    if status == DriftStatus.OFF_TRACK or impact >= Decimal("500"):
        return "critical"
    if status == DriftStatus.WATCH or impact >= Decimal("100"):
        return "warning"
    return "info"


def _tone_for(severity: InsightSeverity) -> InsightTone:
    if severity == "critical":
        return "danger"
    if severity == "warning":
        return "warning"
    if severity == "positive":
        return "good"
    return "neutral"


def _status_adverse_amount(bucket: MasterBucket, variance: Decimal | None) -> Decimal:
    if variance is None:
        return Decimal("0")
    return variance if bucket in _CONSUMPTION_BUCKETS else -variance


def _confidence_for_transactions(count: int) -> Decimal:
    if count >= 6:
        return Decimal("0.95")
    if count >= 3:
        return Decimal("0.85")
    if count >= 1:
        return Decimal("0.70")
    return Decimal("0.50")


def _score(
    *,
    impact: Decimal,
    confidence: Decimal,
    actionability: Decimal,
    deviation: Decimal = Decimal("1"),
) -> Decimal:
    return (impact.copy_abs() * confidence * actionability * deviation).quantize(_CENTS)


def _bucket_by_name(result: PlanVsActualResult) -> dict[MasterBucket, BucketDrift]:
    return {b.bucket: b for b in result.buckets}


def _merchant_insights(
    result: PlanVsActualResult,
    merchant_drivers: list[MerchantDriver],
) -> list[BankingInsight]:
    buckets = _bucket_by_name(result)
    insights: list[BankingInsight] = []
    for merchant in merchant_drivers:
        if merchant.bucket not in _CONSUMPTION_BUCKETS:
            continue
        amount = Decimal(merchant.amount)
        if amount < _MATERIALITY:
            continue
        bucket = buckets.get(merchant.bucket)
        bucket_actual = _dec(bucket.actual_amount) if bucket else None
        bucket_variance = _dec(bucket.variance_amount) if bucket else None
        if bucket_variance is None or bucket_variance <= 0:
            continue
        concentration = (
            amount / bucket_actual if bucket_actual and bucket_actual > 0 else Decimal("0")
        )
        confidence = _confidence_for_transactions(merchant.transaction_count)
        bucket_label = _bucket_label(merchant.bucket)
        if concentration >= _MERCHANT_CONCENTRATION_RATIO:
            insight_type: BankingInsightType = "merchant_concentration"
            title = f"{merchant.merchant} dominates {bucket_label}"
            summary = (
                f"{merchant.merchant} represents {_money(amount)} of {bucket_label} "
                f"spending this period."
            )
            action = f"Review whether {merchant.merchant} should stay at this level next period."
            actionability = Decimal("0.90")
        else:
            insight_type = "merchant_overspend"
            title = f"{merchant.merchant} is driving {bucket_label} overspend"
            summary = (
                f"{merchant.merchant} accounts for {_money(amount)} while "
                f"{bucket_label} is {_money(bucket_variance)} over plan."
            )
            action = f"Trim or recategorize {merchant.merchant} spending before next period."
            actionability = Decimal("1.00")
        insights.append(BankingInsight(
            type=insight_type,
            severity=_severity_for(bucket.status if bucket else DriftStatus.WATCH, amount),
            tone=_tone_for(_severity_for(bucket.status if bucket else DriftStatus.WATCH, amount)),
            title=title,
            summary=summary,
            impact_amount=str(amount.quantize(_CENTS)),
            confidence=confidence,
            action=action,
            supporting_facts=[
                BankingInsightFact(label="Merchant spend", value=str(amount.quantize(_CENTS))),
                BankingInsightFact(label="Transactions", value=str(merchant.transaction_count)),
                BankingInsightFact(label="Bucket", value=bucket_label),
            ],
            rank_score=_score(
                impact=amount,
                confidence=confidence,
                actionability=actionability,
                deviation=(concentration if concentration > 0 else Decimal("1")),
            ),
        ))
    return insights


def _bucket_insights(result: PlanVsActualResult) -> list[BankingInsight]:
    insights: list[BankingInsight] = []
    for bucket in result.buckets:
        variance = _dec(bucket.variance_amount)
        adverse = _status_adverse_amount(bucket.bucket, variance)
        if bucket.status not in (DriftStatus.WATCH, DriftStatus.OFF_TRACK):
            continue
        if adverse < _MATERIALITY:
            continue
        label = _bucket_label(bucket.bucket)
        confidence = _confidence_for_transactions(bucket.transaction_count)
        if bucket.bucket == MasterBucket.WANTS:
            insight_type: BankingInsightType = "persistent_wants_overspend"
            title = "Wants are running above plan"
            summary = f"Wants are {_money(adverse)} over target for the selected period."
            action = "Pick one discretionary category to pull back next period."
        elif bucket.bucket == MasterBucket.NEEDS:
            insight_type = "category_overspend"
            title = "Needs are above the plan"
            summary = f"Needs are {_money(adverse)} over target for the selected period."
            action = "Review required-spend categories and confirm classifications are right."
        elif bucket.bucket == MasterBucket.SAVINGS:
            insight_type = "savings_shortfall"
            title = "Savings are behind target"
            summary = f"Savings are {_money(adverse)} short of target this period."
            action = "Schedule or increase one savings transfer next period."
        else:
            continue
        insights.append(BankingInsight(
            type=insight_type,
            severity=_severity_for(bucket.status, adverse),
            tone=_tone_for(_severity_for(bucket.status, adverse)),
            title=title,
            summary=summary,
            impact_amount=str(adverse.quantize(_CENTS)),
            confidence=confidence,
            action=action,
            supporting_facts=[
                BankingInsightFact(label="Bucket", value=label),
                BankingInsightFact(label="Target", value=bucket.target_amount or ""),
                BankingInsightFact(label="Actual", value=bucket.actual_amount),
                BankingInsightFact(label="Variance", value=bucket.variance_amount or ""),
            ],
            rank_score=_score(
                impact=adverse,
                confidence=confidence,
                actionability=Decimal("0.95"),
                deviation=(abs(_dec(bucket.variance_percentage_points) or Decimal("1"))),
            ),
        ))
    return insights


def _classification_uncertainty_insight(
    review_items: list[TransactionReviewItem],
) -> BankingInsight | None:
    if not review_items:
        return None
    impact = sum((Decimal(item.amount).copy_abs() for item in review_items), Decimal("0"))
    if impact < _MATERIALITY:
        return None
    count = len(review_items)
    confidence = Decimal("0.90")
    return BankingInsight(
        type="classification_uncertainty",
        severity="warning",
        tone="warning",
        title="Classifications need attention",
        summary=(
            f"{count} transaction{'s' if count != 1 else ''} need review, "
            f"covering {_money(impact)}."
        ),
        impact_amount=str(impact.quantize(_CENTS)),
        confidence=confidence,
        action="Confirm or correct these rows so Banking drift reflects your intent.",
        supporting_facts=[
            BankingInsightFact(label="Rows needing review", value=str(count)),
            BankingInsightFact(label="Amount needing review", value=str(impact.quantize(_CENTS))),
        ],
        rank_score=_score(impact=impact, confidence=confidence, actionability=Decimal("0.85")),
    )


def _positive_insight(result: PlanVsActualResult) -> BankingInsight | None:
    known_consumption = [
        b for b in result.buckets
        if b.bucket in _CONSUMPTION_BUCKETS and b.status != DriftStatus.UNKNOWN
    ]
    if len(known_consumption) < 2:
        return None
    favorable = []
    for bucket in known_consumption:
        variance = _dec(bucket.variance_amount)
        if variance is not None and variance <= -_MATERIALITY:
            favorable.append((bucket, variance.copy_abs()))
    if len(favorable) < 2:
        return None
    impact = sum((amount for _, amount in favorable), Decimal("0"))
    return BankingInsight(
        type="positive_improvement",
        severity="positive",
        tone="good",
        title="Core spending is under plan",
        summary=f"Needs and Wants are together {_money(impact)} under target this period.",
        impact_amount=str(impact.quantize(_CENTS)),
        confidence=Decimal("0.85"),
        action="Keep the current spending pattern into the next period.",
        supporting_facts=[
            BankingInsightFact(
                label=_bucket_label(bucket.bucket),
                value=str(amount.quantize(_CENTS)),
            )
            for bucket, amount in favorable
        ],
        rank_score=_score(
            impact=impact,
            confidence=Decimal("0.85"),
            actionability=Decimal("0.40"),
        ),
    )


def build_banking_insights(
    result: PlanVsActualResult,
    merchant_drivers: list[MerchantDriver] | None = None,
    review_items: list[TransactionReviewItem] | None = None,
    *,
    max_items: int = 3,
) -> BankingInsightsResult:
    """Build ranked Banking insights from deterministic facts.

    Ranking follows the PR10 contract: financial impact x deviation x
    confidence x actionability, with stable type/title tie-breakers. At most
    one insight per type is selected so the top three do not repeat the same
    message.
    """
    candidates: list[BankingInsight] = []
    candidates.extend(_merchant_insights(result, merchant_drivers or []))
    candidates.extend(_bucket_insights(result))
    uncertainty = _classification_uncertainty_insight(review_items or [])
    if uncertainty:
        candidates.append(uncertainty)
    positive = _positive_insight(result)
    if positive:
        candidates.append(positive)

    candidates.sort(key=lambda i: (-i.rank_score, i.type, i.title))
    picked: list[BankingInsight] = []
    seen_types: set[str] = set()
    for insight in candidates:
        if insight.type in seen_types:
            continue
        picked.append(insight)
        seen_types.add(insight.type)
        if len(picked) >= max_items:
            break
    return BankingInsightsResult(period=result.period.label, insights=picked)
