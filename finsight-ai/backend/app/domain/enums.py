"""
Domain enumerations.

All enums live here to avoid circular imports across the domain layer.
"""

from __future__ import annotations

from enum import Enum


class InstitutionType(str, Enum):
    """Supported financial institutions."""

    MORGAN_STANLEY = "morgan_stanley"
    CHASE = "chase"
    ETRADE = "etrade"
    UNKNOWN = "unknown"


class StatementType(str, Enum):
    """Types of financial statements we can process."""

    BROKERAGE = "brokerage"          # Investments, holdings, trades
    BANK = "bank"                    # Checking/savings accounts
    CREDIT_CARD = "credit_card"      # Credit card statements
    RETIREMENT = "retirement"        # 401k, IRA statements
    ADVISORY = "advisory"            # Managed/advisory account statements
    UNKNOWN = "unknown"


class AccountType(str, Enum):
    """Types of financial accounts."""

    BROKERAGE = "brokerage"
    CHECKING = "checking"
    SAVINGS = "savings"
    CREDIT_CARD = "credit_card"
    IRA = "ira"
    ROTH_IRA = "roth_ira"
    FOUR_01K = "401k"
    ADVISORY = "advisory"
    UNKNOWN = "unknown"


class TransactionType(str, Enum):
    """Transaction classifications."""

    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER = "transfer"
    FEE = "fee"
    DIVIDEND = "dividend"
    INTEREST = "interest"
    TRADE_BUY = "trade_buy"
    TRADE_SELL = "trade_sell"
    TAX_WITHHOLDING = "tax_withholding"
    ADVISORY_FEE = "advisory_fee"
    OTHER = "other"


class ExtractionStatus(str, Enum):
    """Processing status for a statement document."""

    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    PARTIAL = "partial"       # Some fields extracted, some missing
    FAILED = "failed"


class DocumentStatus(str, Enum):
    """Upload/storage status of a raw document."""

    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    PARSED = "parsed"
    PARTIALLY_PARSED = "partially_parsed"
    EMBEDDED = "embedded"
    PROCESSED = "processed"
    FAILED = "failed"
    DELETED = "deleted"


class BucketStatus(str, Enum):
    """Lifecycle status of a bucket."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class ProcessingEventType(str, Enum):
    """Types of structured processing events streamed to the frontend."""

    # Ingestion pipeline events
    FILE_RECEIVED = "file_received"
    PARSING_STARTED = "parsing_started"
    PARSING_COMPLETE = "parsing_complete"
    CLASSIFICATION_STARTED = "classification_started"
    CLASSIFICATION_COMPLETE = "classification_complete"
    EXTRACTION_STARTED = "extraction_started"
    EXTRACTION_COMPLETE = "extraction_complete"
    NORMALIZATION_STARTED = "normalization_started"
    NORMALIZATION_COMPLETE = "normalization_complete"
    EMBEDDING_STARTED = "embedding_started"
    EMBEDDING_COMPLETE = "embedding_complete"
    PERSISTING = "persisting"
    INGESTION_COMPLETE = "ingestion_complete"
    INGESTION_FAILED = "ingestion_failed"

    # Chat / RAG pipeline events
    SUPERVISOR_ROUTING = "supervisor_routing"
    BUCKET_SELECTED = "bucket_selected"
    RETRIEVAL_STARTED = "retrieval_started"
    RETRIEVAL_COMPLETE = "retrieval_complete"
    ANALYSIS_STARTED = "analysis_started"
    GENERATING_RESPONSE = "generating_response"
    RESPONSE_COMPLETE = "response_complete"

    # Generic
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ProcessingEventStatus(str, Enum):
    """Status of an individual processing event."""

    STARTED = "started"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    FAILED = "failed"
    WARNING = "warning"
