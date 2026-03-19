"""
Bucket-aware analytics services for Coral.

Two services — one per bucket type:
- InvestmentsAnalyticsService  → INVESTMENTS bucket
- BankingAnalyticsService      → BANKING bucket

Both follow the PartialResult pattern: they never raise HTTP 500.
Every method returns a PartialResult(data, warnings) so callers can
surface partial data + warnings to the UI rather than crashing.
"""

from app.services.analytics.investments_analytics import InvestmentsAnalyticsService
from app.services.analytics.banking_analytics import BankingAnalyticsService

__all__ = ["InvestmentsAnalyticsService", "BankingAnalyticsService"]
