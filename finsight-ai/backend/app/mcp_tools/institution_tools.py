"""
MCP tools that bridge the LangGraph supervisor and institution agent / RAG logic.

Each tool in this module corresponds to a typed contract pair defined in
``mcp_tools/contracts.py`` and is registered in ``mcp_tools/registry.py``.

Design principles:
- Tools are the ONLY entry point from the supervisor into institution agents.
  The supervisor never imports concrete agent classes directly after this
  refactor.
- All institution-agent look-ups are deferred to call-time (not import-time)
  to avoid circular imports between supervisor ↔ registry ↔ tools.
- All monetary values cross the tool boundary as Decimal strings.
- Each tool logs structured events via structlog.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import structlog

from app.mcp_tools.contracts import (
    AnswerRenderRequest,
    AnswerRenderResponse,
    ClassifyDocumentRequest,
    ClassifyDocumentResponse,
    ExtractDocumentRequest,
    ExtractDocumentResponse,
    FeeAnalysisRequest,
    FeeAnalysisResponse,
    HoldingsAnalysisRequest,
    HoldingsAnalysisResponse,
    HybridRetrievalRequest,
    HybridRetrievalResponse,
    TransactionSearchRequest,
    TransactionSearchResponse,
)
from app.mcp_tools.registry import MCPTool, ToolInput, ToolOutput

logger = structlog.get_logger(__name__)


# ── Classify Document ──────────────────────────────────────────────────────────

class ClassifyDocumentTool(MCPTool):
    """
    Identify the institution type and statement type for an unknown document.

    Iterates over every agent registered in ``INSTITUTION_AGENT_REGISTRY`` and
    calls ``agent.can_handle(parsed_document)`` using the provided text sample
    (the first 3 pages of the document, pre-joined by the caller).

    The agent with the highest confidence above 0.0 wins.  If no agent claims
    the document, ``institution_type`` is returned as ``"unknown"``.

    Note: this tool operates on a *text sample* rather than a full
    ``ParsedDocument`` so it can be called from contexts that do not have
    access to the in-flight document store (e.g. external testing, validation
    scripts).  For full classification within the ingestion pipeline, the
    ``classify_node`` in ``supervisor.py`` calls ``can_handle()`` directly and
    is more accurate.
    """

    @property
    def name(self) -> str:
        return "classify_document"

    @property
    def description(self) -> str:
        return (
            "Classify a financial document by institution and statement type "
            "using registered institution agents. "
            "Accepts the first 3 pages of text and original filename."
        )

    def _input_class(self) -> type[ToolInput]:
        return ClassifyDocumentRequest

    async def execute(  # type: ignore[override]
        self, input_data: ClassifyDocumentRequest
    ) -> ClassifyDocumentResponse:
        # Deferred import — avoids circular import at module load time.
        from app.agents.supervisor import INSTITUTION_AGENT_REGISTRY
        from app.domain.enums import InstitutionType, StatementType
        from app.parsers.base import ParsedDocument, ParsedPage

        # Build a minimal ParsedDocument from the text sample so we can call
        # the standard can_handle() interface on each agent.
        sample_page = ParsedPage(page_number=1, raw_text=input_data.document_text_sample)
        synthetic_doc = ParsedDocument(
            file_path=input_data.filename,
            page_count=1,
            pages=[sample_page],
            metadata={"filename": input_data.filename, "synthetic": True},
        )

        best_agent = None
        best_confidence: float = 0.0

        for agent in INSTITUTION_AGENT_REGISTRY:
            try:
                can_handle, confidence = await agent.can_handle(synthetic_doc)
                logger.debug(
                    "classify_tool.agent_check",
                    agent=agent.institution_type.value,
                    can_handle=can_handle,
                    confidence=confidence,
                )
                if can_handle and confidence > best_confidence:
                    best_confidence = confidence
                    best_agent = agent
            except Exception as exc:
                logger.warning(
                    "classify_tool.agent_error",
                    agent=agent.institution_type.value,
                    error=str(exc),
                )

        if best_agent is not None:
            institution_value = best_agent.institution_type.value
            statement_value = StatementType.UNKNOWN.value
            reasoning = (
                f"Agent {best_agent.institution_type.value} claimed the document "
                f"with confidence {best_confidence:.2f}."
            )
        else:
            institution_value = InstitutionType.UNKNOWN.value
            statement_value = StatementType.UNKNOWN.value
            best_confidence = 0.0
            reasoning = "No registered agent could identify the institution."

        logger.info(
            "classify_tool.result",
            institution=institution_value,
            confidence=best_confidence,
        )

        return ClassifyDocumentResponse(
            institution_type=institution_value,
            statement_type=statement_value,
            confidence=best_confidence,
            reasoning=reasoning,
        )


# ── Extract Document ───────────────────────────────────────────────────────────

class ExtractDocumentTool(MCPTool):
    """
    Route document extraction to the correct institution agent via the MCP boundary.

    Workflow:
    1. Look up the ``ParsedDocument`` from ``InFlightDocumentStore`` using
       ``document_id``.  The ``parse_node`` in ``supervisor.py`` stores it
       there immediately after parsing.
    2. Find the agent whose ``institution_type.value`` matches the requested
       ``institution_type`` string.
    3. Call ``agent.run(state)`` — the base class implementation in
       ``BaseInstitutionAgent`` delegates to ``agent.extract()`` and writes
       the ``ExtractionResult`` back into state.
    4. Translate the ``ExtractionResult`` into a typed ``ExtractDocumentResponse``
       and return it.

    This decouples the supervisor from importing concrete agent classes: adding
    a new institution only requires adding an agent to
    ``INSTITUTION_AGENT_REGISTRY`` and registering no new LangGraph nodes.
    """

    @property
    def name(self) -> str:
        return "extract_document"

    @property
    def description(self) -> str:
        return (
            "Extract structured financial data from a previously parsed document "
            "using the institution agent that matches the provided institution_type. "
            "Requires the document to be present in the in-flight document store."
        )

    def _input_class(self) -> type[ToolInput]:
        return ExtractDocumentRequest

    async def execute(  # type: ignore[override]
        self, input_data: ExtractDocumentRequest
    ) -> ExtractDocumentResponse:
        # Deferred imports to avoid circular dependencies.
        from app.agents.supervisor import INSTITUTION_AGENT_REGISTRY
        from app.agents.state import IngestionState
        from app.domain.enums import ExtractionStatus, InstitutionType
        from app.mcp_tools.document_store import document_store

        doc_id = input_data.document_id

        # 1. Retrieve the parsed document from the in-flight store.
        parsed = document_store.get(doc_id)
        if parsed is None:
            logger.error(
                "extract_tool.missing_document",
                document_id=doc_id,
                institution=input_data.institution_type,
            )
            return ExtractDocumentResponse(
                success=False,
                extraction_status=ExtractionStatus.FAILED.value,
                errors=[
                    f"ParsedDocument not found in InFlightDocumentStore for id={doc_id}. "
                    "Ensure parse_node ran successfully before extract_node."
                ],
            )

        # 2. Find the matching agent.
        target_agent = None
        for agent in INSTITUTION_AGENT_REGISTRY:
            if agent.institution_type.value == input_data.institution_type:
                target_agent = agent
                break

        if target_agent is None:
            logger.error(
                "extract_tool.unknown_institution",
                institution=input_data.institution_type,
                registered=[a.institution_type.value for a in INSTITUTION_AGENT_REGISTRY],
            )
            return ExtractDocumentResponse(
                success=False,
                extraction_status=ExtractionStatus.FAILED.value,
                errors=[
                    f"No agent registered for institution_type='{input_data.institution_type}'. "
                    f"Registered: {[a.institution_type.value for a in INSTITUTION_AGENT_REGISTRY]}"
                ],
            )

        # 3. Build a minimal IngestionState and delegate to agent.run().
        #    agent.run() populates state["extraction_result"] or state["errors"].
        try:
            institution_enum = InstitutionType(input_data.institution_type)
        except ValueError:
            institution_enum = InstitutionType.UNKNOWN

        minimal_state: IngestionState = {
            "document_id": doc_id,
            "parsed_document": parsed,
            "institution_type": institution_enum,
            "errors": [],
            "warnings": [],
        }

        logger.info(
            "extract_tool.run",
            document_id=doc_id,
            institution=input_data.institution_type,
        )

        updated_state = await target_agent.run(minimal_state)

        # 4. Translate ExtractionResult → ExtractDocumentResponse.
        #    Also persist the ExtractionResult back into InFlightDocumentStore
        #    so that extract_node in supervisor.py can retrieve it and write it
        #    into the LangGraph state dict (the minimal_state used here is
        #    separate from the supervisor's state dict).
        result = updated_state.get("extraction_result")
        if result is not None:
            document_store.put_result(doc_id, result)
        state_errors: list[str] = updated_state.get("errors", [])

        if result is None:
            logger.error("extract_tool.no_result", document_id=doc_id)
            return ExtractDocumentResponse(
                success=False,
                extraction_status=ExtractionStatus.FAILED.value,
                errors=state_errors or ["Agent run produced no ExtractionResult."],
            )

        stmt = result.statement
        tx_count = len(getattr(stmt, "transactions", [])) if stmt else 0
        fee_count = len(getattr(stmt, "fees", [])) if stmt else 0
        holding_count = len(getattr(stmt, "holdings", [])) if stmt else 0
        snapshot_count = len(getattr(stmt, "balance_snapshots", [])) if stmt else 0
        statement_id = str(stmt.id) if stmt else None

        success = result.status == ExtractionStatus.SUCCESS or (
            result.status == ExtractionStatus.PARTIAL and stmt is not None
        )

        logger.info(
            "extract_tool.done",
            document_id=doc_id,
            institution=input_data.institution_type,
            status=result.status.value,
            transactions=tx_count,
            fees=fee_count,
            confidence=result.overall_confidence,
        )

        return ExtractDocumentResponse(
            success=success,
            extraction_status=result.status.value,
            overall_confidence=result.overall_confidence,
            transaction_count=tx_count,
            fee_count=fee_count,
            holding_count=holding_count,
            balance_snapshot_count=snapshot_count,
            statement_id=statement_id,
            errors=result.errors or state_errors,
        )


# ── Fee Analysis ───────────────────────────────────────────────────────────────

class FeeAnalysisTool(MCPTool):
    """
    Aggregate and analyse fees stored in the database.

    Applies optional filters (statement_id, account_id, date range) and
    returns totals broken down by fee category.  Anomaly detection is applied
    to flag unusually large fees or exact duplicates within the same period.
    """

    @property
    def name(self) -> str:
        return "fee_analysis"

    @property
    def description(self) -> str:
        return (
            "Aggregate fee data from the database with optional filters by "
            "statement, account, and date range. "
            "Returns total fees, per-category breakdown, and anomaly flags."
        )

    def _input_class(self) -> type[ToolInput]:
        return FeeAnalysisRequest

    async def execute(  # type: ignore[override]
        self, input_data: FeeAnalysisRequest
    ) -> FeeAnalysisResponse:
        from datetime import date as date_type

        from sqlalchemy import select, and_, cast, func
        from sqlalchemy import String

        from app.database.engine import get_session
        from app.database.models import FeeModel

        filters: list[Any] = []

        if input_data.statement_id:
            filters.append(FeeModel.statement_id == input_data.statement_id)
        if input_data.account_id:
            filters.append(FeeModel.account_id == input_data.account_id)
        if input_data.start_date:
            start = date_type.fromisoformat(input_data.start_date)
            filters.append(FeeModel.fee_date >= start)
        if input_data.end_date:
            end = date_type.fromisoformat(input_data.end_date)
            filters.append(FeeModel.fee_date <= end)

        async with get_session() as session:
            stmt = select(FeeModel)
            if filters:
                stmt = stmt.where(and_(*filters))
            result = await session.execute(stmt)
            fees = result.scalars().all()

        # Aggregate totals
        total = Decimal("0")
        by_category: dict[str, Decimal] = {}
        anomalies: list[str] = []
        seen: dict[str, list[Decimal]] = {}  # for duplicate detection

        for fee in fees:
            amount = Decimal(str(fee.amount))
            total += amount
            category = fee.fee_category or "uncategorized"
            by_category[category] = by_category.get(category, Decimal("0")) + amount

            # Simple anomaly: fee > $1,000
            if amount > Decimal("1000"):
                anomalies.append(
                    f"Large fee: {fee.description!r} = ${amount} on {fee.fee_date}"
                )

            # Duplicate detection key: description + date + amount
            dup_key = f"{fee.description}|{fee.fee_date}|{amount}"
            seen.setdefault(dup_key, []).append(amount)

        for dup_key, occurrences in seen.items():
            if len(occurrences) > 1:
                parts = dup_key.split("|")
                anomalies.append(
                    f"Duplicate fee detected ({len(occurrences)}×): "
                    f"description='{parts[0]}', date={parts[1]}, amount=${parts[2]}"
                )

        logger.info(
            "fee_analysis_tool.done",
            fee_count=len(fees),
            total=str(total),
            categories=list(by_category.keys()),
            anomaly_count=len(anomalies),
        )

        return FeeAnalysisResponse(
            total_fees=str(total),
            fee_count=len(fees),
            by_category={k: str(v) for k, v in by_category.items()},
            anomalies=anomalies,
        )


# ── Holdings Analysis ──────────────────────────────────────────────────────────

class HoldingsAnalysisTool(MCPTool):
    """
    Summarise holdings recorded against a specific statement.

    Returns total market value, per-holding detail, top-N holdings by market
    value, and an asset-class breakdown.
    """

    @property
    def name(self) -> str:
        return "holdings_analysis"

    @property
    def description(self) -> str:
        return (
            "Analyse holdings for a given statement. "
            "Returns total market value, top holdings, and asset-class breakdown."
        )

    def _input_class(self) -> type[ToolInput]:
        return HoldingsAnalysisRequest

    async def execute(  # type: ignore[override]
        self, input_data: HoldingsAnalysisRequest
    ) -> HoldingsAnalysisResponse:
        from sqlalchemy import select

        from app.database.engine import get_session
        from app.database.models import HoldingModel

        async with get_session() as session:
            stmt = select(HoldingModel).where(
                HoldingModel.statement_id == input_data.statement_id
            )
            result = await session.execute(stmt)
            holdings = result.scalars().all()

        total_value = Decimal("0")
        asset_class_totals: dict[str, Decimal] = {}
        holding_dicts: list[dict[str, Any]] = []

        for h in holdings:
            mv = Decimal(str(h.market_value))
            total_value += mv
            ac = h.asset_class or "other"
            asset_class_totals[ac] = asset_class_totals.get(ac, Decimal("0")) + mv
            holding_dicts.append(
                {
                    "symbol": h.symbol,
                    "name": h.description,
                    "market_value": str(mv),
                    "asset_class": ac,
                    "quantity": str(h.quantity) if h.quantity is not None else None,
                    "price": str(h.price) if h.price is not None else None,
                    "pct_of_portfolio": (
                        str(h.percent_of_portfolio)
                        if h.percent_of_portfolio is not None
                        else None
                    ),
                }
            )

        # Sort by market_value descending; take top 10
        holding_dicts.sort(key=lambda x: Decimal(x["market_value"]), reverse=True)
        top_holdings = holding_dicts[:10]

        # Recalculate pct if not stored
        if total_value > 0:
            for hd in top_holdings:
                if hd["pct_of_portfolio"] is None:
                    pct = Decimal(hd["market_value"]) / total_value * Decimal("100")
                    hd["pct_of_portfolio"] = f"{pct:.2f}"

        logger.info(
            "holdings_analysis_tool.done",
            statement_id=input_data.statement_id,
            holding_count=len(holdings),
            total_value=str(total_value),
        )

        return HoldingsAnalysisResponse(
            total_market_value=str(total_value),
            holding_count=len(holdings),
            top_holdings=top_holdings,
            asset_class_breakdown={k: str(v) for k, v in asset_class_totals.items()},
        )


# ── Transaction Search ─────────────────────────────────────────────────────────

class TransactionSearchTool(MCPTool):
    """
    Search the transactions table using a combination of text matching and
    structured filters.

    ``query`` is matched against the transaction description using a SQL LIKE
    clause (case-insensitive).  All other filters are applied as exact-match
    or range predicates.
    """

    @property
    def name(self) -> str:
        return "transaction_search"

    @property
    def description(self) -> str:
        return (
            "Search transactions by free-text query and optional structured filters "
            "(statement, account, date range, transaction type). "
            "Returns matching rows up to the configured limit."
        )

    def _input_class(self) -> type[ToolInput]:
        return TransactionSearchRequest

    async def execute(  # type: ignore[override]
        self, input_data: TransactionSearchRequest
    ) -> TransactionSearchResponse:
        from datetime import date as date_type

        from sqlalchemy import and_, select

        from app.database.engine import get_session
        from app.database.models import TransactionModel

        filters: list[Any] = []

        # Text search on description (LIKE)
        if input_data.query.strip():
            filters.append(
                TransactionModel.description.ilike(f"%{input_data.query.strip()}%")
            )
        if input_data.statement_id:
            filters.append(TransactionModel.statement_id == input_data.statement_id)
        if input_data.account_id:
            filters.append(TransactionModel.account_id == input_data.account_id)
        if input_data.start_date:
            start = date_type.fromisoformat(input_data.start_date)
            filters.append(TransactionModel.transaction_date >= start)
        if input_data.end_date:
            end = date_type.fromisoformat(input_data.end_date)
            filters.append(TransactionModel.transaction_date <= end)
        if input_data.transaction_type:
            filters.append(
                TransactionModel.transaction_type == input_data.transaction_type
            )

        async with get_session() as session:
            stmt = (
                select(TransactionModel)
                .order_by(TransactionModel.transaction_date.desc())
                .limit(input_data.limit)
            )
            if filters:
                stmt = stmt.where(and_(*filters))
            result = await session.execute(stmt)
            transactions = result.scalars().all()

        tx_list: list[dict[str, Any]] = [
            {
                "id": str(tx.id),
                "transaction_date": str(tx.transaction_date),
                "description": tx.description,
                "transaction_type": tx.transaction_type,
                "amount": str(tx.amount),
                "symbol": tx.symbol,
                "account_id": str(tx.account_id),
                "statement_id": str(tx.statement_id),
            }
            for tx in transactions
        ]

        logger.info(
            "transaction_search_tool.done",
            query=input_data.query,
            found=len(tx_list),
        )

        return TransactionSearchResponse(
            transactions=tx_list,
            total_found=len(tx_list),
        )


# ── Hybrid Retrieval ───────────────────────────────────────────────────────────

class HybridRetrievalTool(MCPTool):
    """
    Run the hybrid vector + SQL retriever for a natural language financial question.

    Delegates to ``HybridRetriever.retrieve()``, which decides the correct
    strategy (vector-only, SQL-first, or hybrid) based on question content.

    ``bucket_ids`` is currently forwarded as the ``institution_filter`` if a
    single value is provided; multi-bucket scoping is deferred to Phase 3.
    """

    @property
    def name(self) -> str:
        return "hybrid_retrieval"

    @property
    def description(self) -> str:
        return (
            "Retrieve relevant financial context for a question using the hybrid "
            "vector + SQL retrieval strategy. "
            "Returns formatted context text plus raw chunks and SQL results for "
            "downstream answer rendering."
        )

    def _input_class(self) -> type[ToolInput]:
        return HybridRetrievalRequest

    async def execute(  # type: ignore[override]
        self, input_data: HybridRetrievalRequest
    ) -> HybridRetrievalResponse:
        from app.rag.retriever import HybridRetriever

        retriever = HybridRetriever()

        # Derive a single institution_filter from bucket_ids if provided.
        # Full multi-bucket scoping is a Phase 3 enhancement.
        institution_filter: str | None = None
        if input_data.bucket_ids and len(input_data.bucket_ids) == 1:
            institution_filter = input_data.bucket_ids[0]

        result = await retriever.retrieve(
            question=input_data.question,
            institution_filter=institution_filter,
            n_vector_results=input_data.top_k,
        )

        # Determine data_source label
        has_vector = bool(result.vector_chunks)
        has_sql = bool(result.sql_results)
        if has_vector and has_sql:
            data_source = "hybrid"
        elif has_sql:
            data_source = "sql"
        elif has_vector:
            data_source = "vector"
        else:
            data_source = "none"

        logger.info(
            "hybrid_retrieval_tool.done",
            question_len=len(input_data.question),
            vector_chunks=len(result.vector_chunks),
            sql_rows=len(result.sql_results),
            data_source=data_source,
        )

        return HybridRetrievalResponse(
            context_text=result.context_text,
            vector_chunks=result.vector_chunks,
            sql_results=result.sql_results,
            sql_query=result.sql_query,
            data_source=data_source,
        )


# ── Answer Rendering ───────────────────────────────────────────────────────────

# Intent labels and their required keys in the structured_answer dict
_INTENT_LAYOUTS: dict[str, list[str]] = {
    "fee_summary": ["total_fees", "fee_count", "by_category", "period"],
    "holdings_breakdown": ["total_market_value", "top_holdings", "asset_class_breakdown"],
    "transaction_list": ["transactions", "total_found", "filters_applied"],
    "balance_snapshot": ["balance_date", "total_value", "cash_value", "invested_value"],
    "general": ["prose"],
}

_INTENT_KEYWORDS: list[tuple[str, str]] = [
    ("fee_summary", r"fee|charge|expense|cost"),
    ("holdings_breakdown", r"holding|portfolio|position|asset|security|securities"),
    ("transaction_list", r"transaction|trade|buy|sell|deposit|withdraw"),
    ("balance_snapshot", r"balance|value|worth|total value"),
]


def _infer_intent(question: str) -> str:
    """Infer an answer layout intent from the question text."""
    import re

    q_lower = question.lower()
    for intent, pattern in _INTENT_KEYWORDS:
        if re.search(pattern, q_lower):
            return intent
    return "general"


class AnswerRenderTool(MCPTool):
    """
    Assemble a fully structured financial answer from RAG retrieval results.

    The tool:
    1. Infers (or accepts an override for) the answer intent / layout.
    2. Structures the ``sql_results`` and ``vector_chunks`` into the layout's
       typed dict shape.
    3. Returns a ``AnswerRenderResponse`` that the frontend can render as a
       card, table, or evidence drawer without further parsing.

    This keeps presentation logic out of the supervisor and makes answer shapes
    testable in isolation.
    """

    @property
    def name(self) -> str:
        return "answer_render"

    @property
    def description(self) -> str:
        return (
            "Build a structured, frontend-ready financial answer from RAG results. "
            "Accepts prose, vector chunks, and SQL rows; returns a typed answer "
            "dict suitable for rendering as cards, tables, or evidence drawers."
        )

    def _input_class(self) -> type[ToolInput]:
        return AnswerRenderRequest

    async def execute(  # type: ignore[override]
        self, input_data: AnswerRenderRequest
    ) -> AnswerRenderResponse:
        intent = input_data.intent_override or _infer_intent(input_data.question)

        # Base structured answer — always includes prose and data sources.
        structured: dict[str, Any] = {
            "prose": input_data.prose_answer,
            "confidence": 0.0,  # updated below
            "data_source_labels": [],
            "sql_query": input_data.sql_query,
            "evidence_count": len(input_data.vector_chunks),
        }

        caveats: list[str] = []
        confidence = 0.8  # default if SQL data present

        # Enrich based on intent
        if intent == "fee_summary" and input_data.sql_results:
            total = Decimal("0")
            by_cat: dict[str, Decimal] = {}
            for row in input_data.sql_results:
                amt_raw = row.get("amount") or row.get("total") or "0"
                try:
                    amt = Decimal(str(amt_raw))
                except Exception:
                    amt = Decimal("0")
                total += amt
                cat = str(row.get("fee_category") or "uncategorized")
                by_cat[cat] = by_cat.get(cat, Decimal("0")) + amt

            structured.update(
                {
                    "total_fees": str(total),
                    "fee_count": len(input_data.sql_results),
                    "by_category": {k: str(v) for k, v in by_cat.items()},
                    "period": None,  # caller may populate
                    "data_source_labels": ["sql"],
                }
            )

        elif intent == "holdings_breakdown" and input_data.sql_results:
            total_mv = Decimal("0")
            top: list[dict[str, Any]] = []
            ac_totals: dict[str, Decimal] = {}
            for row in input_data.sql_results:
                mv_raw = row.get("market_value") or "0"
                try:
                    mv = Decimal(str(mv_raw))
                except Exception:
                    mv = Decimal("0")
                total_mv += mv
                ac = str(row.get("asset_class") or "other")
                ac_totals[ac] = ac_totals.get(ac, Decimal("0")) + mv
                top.append(
                    {
                        "symbol": row.get("symbol"),
                        "name": row.get("description") or row.get("name"),
                        "market_value": str(mv),
                        "pct": None,
                    }
                )
            # Sort and cap at top 10
            top.sort(key=lambda x: Decimal(x["market_value"]), reverse=True)
            top = top[:10]
            if total_mv > 0:
                for item in top:
                    pct = Decimal(item["market_value"]) / total_mv * Decimal("100")
                    item["pct"] = f"{pct:.2f}%"

            structured.update(
                {
                    "total_market_value": str(total_mv),
                    "top_holdings": top,
                    "asset_class_breakdown": {k: str(v) for k, v in ac_totals.items()},
                    "data_source_labels": ["sql"],
                }
            )

        elif intent == "transaction_list" and input_data.sql_results:
            tx_list = [
                {
                    "date": str(row.get("transaction_date") or row.get("date") or ""),
                    "description": row.get("description", ""),
                    "type": row.get("transaction_type", ""),
                    "amount": str(row.get("amount", "0")),
                }
                for row in input_data.sql_results
            ]
            structured.update(
                {
                    "transactions": tx_list,
                    "total_found": len(tx_list),
                    "filters_applied": {},
                    "data_source_labels": ["sql"],
                }
            )

        elif intent == "balance_snapshot" and input_data.sql_results:
            row = input_data.sql_results[0] if input_data.sql_results else {}
            structured.update(
                {
                    "balance_date": str(row.get("snapshot_date") or ""),
                    "total_value": str(row.get("total_value") or "0"),
                    "cash_value": str(row.get("cash_value") or "0"),
                    "invested_value": str(row.get("invested_value") or "0"),
                    "data_source_labels": ["sql"],
                }
            )

        else:
            # general intent — prose only; lower confidence since no SQL backing
            confidence = 0.6 if input_data.vector_chunks else 0.4
            structured["data_source_labels"] = ["vector"] if input_data.vector_chunks else []
            if not input_data.sql_results and not input_data.vector_chunks:
                caveats.append("Answer based on general knowledge; no matching financial data found.")
                confidence = 0.3

        # Attach evidence chunk ids for the frontend's evidence drawer
        structured["source_chunk_ids"] = [
            c.get("id", "") for c in input_data.vector_chunks[:6]
        ]
        structured["confidence"] = confidence

        logger.info(
            "answer_render_tool.done",
            intent=intent,
            confidence=confidence,
            caveats=len(caveats),
        )

        return AnswerRenderResponse(
            answer_type=intent,
            structured_answer=structured,
            confidence=confidence,
            caveats=caveats,
        )
