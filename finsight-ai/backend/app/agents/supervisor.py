"""
LangGraph Supervisor Agent — orchestrates the document ingestion pipeline.

Graph topology:
  START
    │
    ▼
  [parse_node]         PDF → ParsedDocument
    │
    ▼
  [classify_node]      Identify institution via agent can_handle()
    │
    ▼
  [route_node]  ───────► [morgan_stanley_node]
                         [chase_node]
                         [etrade_node]
                         [unknown_node]
    │ (all routes converge)
    ▼
  [persist_node]       Write Statement to SQLite
    │
    ▼
  [embed_node]         Chunk + embed into Chroma
    │
    ▼
  [report_node]        Finalize ExtractionResult
    │
    ▼
  END

Phase 2.4 upgrade:
  Every node emits typed ``SSEEvent`` messages to the per-document ``EventBus``
  via ``bus_registry.emit()``.  If no bus is registered (job was not started
  via the streaming-aware upload path, or the bus was already closed), the
  emit is a silent no-op — no crashes.

Design decisions:
- The supervisor does NOT contain business logic; it delegates to agents/services.
- Conditional routing (route_node) uses agent.can_handle() scores to pick
  the best-matching agent dynamically. Adding a new institution = adding an
  agent to INSTITUTION_AGENT_REGISTRY.
- Errors at any node add to state["errors"] but don't crash the graph;
  the report_node summarizes the final status.
"""

from __future__ import annotations

import time

import structlog
from langgraph.graph import END, START, StateGraph

from app.agents.institutions.base import BaseInstitutionAgent
from app.agents.institutions.morgan_stanley import MorganStanleyAgent
from app.agents.institutions.chase import ChaseAgent
from app.agents.institutions.etrade import ETradeAgent
from app.agents.state import IngestionState
from app.api.schemas.sse_schemas import (
    EmbeddingCompletedPayload,
    EmbeddingStartedPayload,
    ExtractionStartedPayload,
    FieldsDetectedPayload,
    InstitutionHypothesesPayload,
    IngestionCompletePayload,
    ParseStartedPayload,
    PersistCompletedPayload,
    PersistStartedPayload,
    TextExtractedPayload,
)
from app.domain.enums import DocumentStatus, ExtractionStatus, InstitutionType
from app.parsers.pdf_parser import PDFParser
from app.services.event_bus import bus_registry, make_ingestion_event

logger = structlog.get_logger(__name__)

# Registry of all available institution agents.
# To add a new institution: instantiate its agent and append it here.
INSTITUTION_AGENT_REGISTRY: list[BaseInstitutionAgent] = [
    MorganStanleyAgent(),
    ChaseAgent(),
    ETradeAgent(),
]


# ── Internal emit helper ────────────────────────────────────────────────────────

async def _emit(state: IngestionState, **kwargs) -> None:
    """
    Emit an ingestion event to the document's EventBus.

    Silent no-op if no bus is registered for this document_id.
    """
    doc_id = state.get("document_id")
    if not doc_id:
        return
    event = make_ingestion_event(session_id=doc_id, document_id=doc_id, **kwargs)
    await bus_registry.emit(doc_id, event)


# ── Node functions ─────────────────────────────────────────────────────────────

async def parse_node(state: IngestionState) -> IngestionState:
    """Parse the raw document file into a ParsedDocument."""
    from pathlib import Path

    file_path = state.get("file_path")
    doc_id = state.get("document_id", "unknown")

    if not file_path:
        state.setdefault("errors", []).append("No file_path in state")
        return state

    await _emit(
        state,
        event_type="parse_started",
        stage="parse_pdf",
        message="Extracting text and structure from PDF",
        status="started",
        progress=0.05,
        payload=ParseStartedPayload(
            document_id=doc_id,
            file_path=file_path,
        ).model_dump(),
    )

    t0 = time.monotonic()
    parser = PDFParser()
    try:
        parsed = await parser.parse(Path(file_path))
        state["parsed_document"] = parsed
        state["page_count"] = parsed.page_count
        duration_ms = int((time.monotonic() - t0) * 1000)

        # Estimate char count from all pages
        char_count = sum(len(p.text or "") for p in parsed.pages)
        has_tables = any(p.tables for p in parsed.pages if hasattr(p, "tables"))

        logger.info(
            "parse_node.done",
            pages=parsed.page_count,
            document_id=doc_id,
        )
        await _emit(
            state,
            event_type="text_extracted",
            stage="parse_pdf",
            message=f"Extracted {parsed.page_count} page(s), {char_count:,} characters",
            status="complete",
            progress=0.15,
            duration_ms=duration_ms,
            payload=TextExtractedPayload(
                document_id=doc_id,
                page_count=parsed.page_count,
                char_count=char_count,
                has_tables=has_tables,
            ).model_dump(),
        )

    except Exception as exc:
        logger.exception("parse_node.error", error=str(exc))
        state.setdefault("errors", []).append(f"Parse failed: {exc}")
        state["document_status"] = DocumentStatus.FAILED.value
        await _emit(
            state,
            event_type="error",
            stage="parse_pdf",
            message=f"PDF parsing failed: {exc}",
            status="failed",
            progress=0.15,
        )

    return state


async def classify_node(state: IngestionState) -> IngestionState:
    """
    Run all institution agents' can_handle() and select the best match.

    Stores the winning institution_type and classification_confidence in state.
    """
    parsed = state.get("parsed_document")
    doc_id = state.get("document_id", "unknown")

    if not parsed:
        state["institution_type"] = InstitutionType.UNKNOWN
        state["classification_confidence"] = 0.0
        return state

    t0 = time.monotonic()
    best_agent: BaseInstitutionAgent | None = None
    best_confidence: float = 0.0
    hypotheses: list[dict] = []

    for agent in INSTITUTION_AGENT_REGISTRY:
        try:
            can_handle, confidence = await agent.can_handle(parsed)
            hypothesis = {
                "institution": agent.institution_type.value,
                "confidence": confidence,
                "can_handle": can_handle,
            }
            hypotheses.append(hypothesis)
            logger.debug(
                "classify_node.agent_check",
                agent=agent.institution_type.value,
                can_handle=can_handle,
                confidence=confidence,
            )
            if can_handle and confidence > best_confidence:
                best_confidence = confidence
                best_agent = agent
        except Exception as exc:
            logger.warning(
                "classify_node.agent_error",
                agent=agent.institution_type.value,
                error=str(exc),
            )

    if best_agent:
        state["institution_type"] = best_agent.institution_type
        state["classification_confidence"] = best_confidence
        selected = best_agent.institution_type.value
        logger.info(
            "classify_node.result",
            institution=selected,
            confidence=best_confidence,
        )
    else:
        state["institution_type"] = InstitutionType.UNKNOWN
        state["classification_confidence"] = 0.0
        selected = "unknown"
        state.setdefault("warnings", []).append(
            "Could not identify institution. Document marked as unknown."
        )

    duration_ms = int((time.monotonic() - t0) * 1000)
    await _emit(
        state,
        event_type="institution_hypotheses",
        stage="classify_document",
        message=f"Institution identified: {selected} (confidence {best_confidence:.0%})",
        status="complete",
        progress=0.25,
        duration_ms=duration_ms,
        payload=InstitutionHypothesesPayload(
            document_id=doc_id,
            hypotheses=hypotheses,
            selected_institution=selected,
            selected_confidence=best_confidence,
        ).model_dump(),
    )

    return state


async def morgan_stanley_node(state: IngestionState) -> IngestionState:
    """Run the Morgan Stanley agent."""
    await _emit(
        state,
        event_type="extraction_started_v2",
        stage="extract_fields",
        message="Running Morgan Stanley field extractor",
        status="started",
        progress=0.35,
        payload=ExtractionStartedPayload(
            document_id=state.get("document_id", ""),
            institution="morgan_stanley",
            agent="MorganStanleyAgent",
        ).model_dump(),
    )
    agent = next(
        a for a in INSTITUTION_AGENT_REGISTRY
        if a.institution_type == InstitutionType.MORGAN_STANLEY
    )
    state = await agent.run(state)
    await _emit_extraction_complete(state)
    return state


async def chase_node(state: IngestionState) -> IngestionState:
    """Run the Chase agent."""
    await _emit(
        state,
        event_type="extraction_started_v2",
        stage="extract_fields",
        message="Running Chase field extractor",
        status="started",
        progress=0.35,
        payload=ExtractionStartedPayload(
            document_id=state.get("document_id", ""),
            institution="chase",
            agent="ChaseAgent",
        ).model_dump(),
    )
    agent = next(
        a for a in INSTITUTION_AGENT_REGISTRY
        if a.institution_type == InstitutionType.CHASE
    )
    state = await agent.run(state)
    await _emit_extraction_complete(state)
    return state


async def etrade_node(state: IngestionState) -> IngestionState:
    """Run the E*TRADE agent."""
    await _emit(
        state,
        event_type="extraction_started_v2",
        stage="extract_fields",
        message="Running E*TRADE field extractor",
        status="started",
        progress=0.35,
        payload=ExtractionStartedPayload(
            document_id=state.get("document_id", ""),
            institution="etrade",
            agent="ETradeAgent",
        ).model_dump(),
    )
    agent = next(
        a for a in INSTITUTION_AGENT_REGISTRY
        if a.institution_type == InstitutionType.ETRADE
    )
    state = await agent.run(state)
    await _emit_extraction_complete(state)
    return state


async def _emit_extraction_complete(state: IngestionState) -> None:
    """
    Emit ``fields_detected`` after any institution agent finishes.

    Pulls counts from the extraction result when available.
    """
    result = state.get("extraction_result")
    doc_id = state.get("document_id", "")
    institution = state.get("institution_type", InstitutionType.UNKNOWN)

    if result and result.statement:
        stmt = result.statement
        tx_count = len(getattr(stmt, "transactions", []))
        fee_count = len(getattr(stmt, "fees", []))
        holding_count = len(getattr(stmt, "holdings", []))
        snapshot_count = len(getattr(stmt, "balance_snapshots", []))
        confidence = getattr(result, "overall_confidence", 0.0)
        low_conf_fields: list[str] = []
    else:
        tx_count = fee_count = holding_count = snapshot_count = 0
        confidence = 0.0
        low_conf_fields = []

    needs_review = confidence < 0.7 or bool(state.get("errors"))

    await _emit(
        state,
        event_type="fields_detected",
        stage="extract_fields",
        message=(
            f"Extraction complete — {tx_count} transactions, "
            f"{fee_count} fees, {holding_count} holdings "
            f"(confidence {confidence:.0%})"
        ),
        status="complete" if not state.get("errors") else "warning",
        progress=0.5,
        warnings=state.get("warnings", []),
        payload=FieldsDetectedPayload(
            document_id=doc_id,
            institution=institution.value if hasattr(institution, "value") else str(institution),
            transaction_count=tx_count,
            fee_count=fee_count,
            holding_count=holding_count,
            balance_snapshot_count=snapshot_count,
            overall_confidence=confidence,
            low_confidence_fields=low_conf_fields,
        ).model_dump(),
    )

    if needs_review:
        await _emit(
            state,
            event_type="fields_needing_review",
            stage="extract_fields",
            message="Some extracted fields require human review",
            status="warning",
            progress=0.5,
            payload={
                "document_id": doc_id,
                "review_item_count": 0,  # Phase 2.2 review service populates this
                "reasons": (
                    ["Overall extraction confidence below threshold"]
                    if confidence < 0.7 else []
                ) + state.get("errors", []),
            },
        )


async def unknown_institution_node(state: IngestionState) -> IngestionState:
    """Handle documents whose institution could not be identified."""
    import uuid
    from app.domain.entities import ExtractionResult

    logger.warning("unknown_institution_node", document_id=state.get("document_id"))
    doc_id_str = state.get("document_id", str(uuid.uuid4()))
    state["extraction_result"] = ExtractionResult(
        document_id=uuid.UUID(doc_id_str),
        institution_type=InstitutionType.UNKNOWN,
        status=ExtractionStatus.FAILED,
        errors=[
            "Unable to identify institution. "
            "Ensure the document is from a supported institution "
            "(Morgan Stanley, Chase, E*TRADE)."
        ],
    )
    state["document_status"] = DocumentStatus.FAILED.value

    await _emit(
        state,
        event_type="error",
        stage="classify_document",
        message=(
            "Could not identify institution. "
            "Supported: Morgan Stanley, Chase, E*TRADE."
        ),
        status="failed",
        progress=0.3,
    )
    return state


async def persist_node(state: IngestionState) -> IngestionState:
    """Persist the extracted Statement to the relational database."""
    from app.database.engine import get_session
    from app.database.repositories.account_repo import AccountRepository, InstitutionRepository
    from app.database.repositories.statement_repo import (
        StatementDocumentRepository,
        StatementRepository,
    )
    from app.domain.entities import FinancialInstitution
    from app.domain.enums import DocumentStatus

    result = state.get("extraction_result")
    doc_id = state.get("document_id", "")

    if not result or not result.statement:
        logger.info("persist_node.skip", reason="no extraction result or statement")
        return state

    stmt = result.statement
    record_counts = {
        "transactions": len(getattr(stmt, "transactions", [])),
        "fees": len(getattr(stmt, "fees", [])),
        "holdings": len(getattr(stmt, "holdings", [])),
        "balance_snapshots": len(getattr(stmt, "balance_snapshots", [])),
    }

    await _emit(
        state,
        event_type="persist_started",
        stage="persist_canonical",
        message=f"Writing {sum(record_counts.values())} records to database",
        status="started",
        progress=0.6,
        payload=PersistStartedPayload(
            document_id=doc_id,
            record_counts=record_counts,
        ).model_dump(),
    )

    t0 = time.monotonic()
    try:
        async with get_session() as session:
            inst_repo = InstitutionRepository(session)
            acct_repo = AccountRepository(session)
            stmt_repo = StatementRepository(session)
            doc_repo = StatementDocumentRepository(session)

            # Upsert institution
            institution = FinancialInstitution(
                id=result.statement.institution_id,
                name=result.institution_type.value.replace("_", " ").title(),
                institution_type=result.institution_type,
            )
            inst_model = await inst_repo.get_or_create(institution)

            # Upsert account (from statement)
            from app.domain.entities import Account
            from app.domain.enums import AccountType
            account = Account(
                id=result.statement.account_id,
                institution_id=result.statement.institution_id,
                account_number_masked="****0000",
                account_type=AccountType.BROKERAGE,
            )
            acct_model = await acct_repo.get_or_create(account, inst_model.id)

            # Update statement IDs to match DB
            import uuid
            result.statement.institution_id = uuid.UUID(inst_model.id)
            result.statement.account_id = uuid.UUID(acct_model.id)
            for bs in result.statement.balance_snapshots:
                bs.account_id = uuid.UUID(acct_model.id)
            for tx in result.statement.transactions:
                tx.account_id = uuid.UUID(acct_model.id)
            for fee in result.statement.fees:
                fee.account_id = uuid.UUID(acct_model.id)
            for h in result.statement.holdings:
                h.account_id = uuid.UUID(acct_model.id)

            # Persist statement
            await stmt_repo.create(result.statement)

            # Update document status
            if doc_id:
                await doc_repo.update_status(
                    uuid.UUID(doc_id), DocumentStatus.PROCESSED
                )

        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.info("persist_node.done", statement_id=str(result.statement.id))

        await _emit(
            state,
            event_type="persist_completed",
            stage="persist_canonical",
            message="All records written to database",
            status="complete",
            progress=0.7,
            duration_ms=duration_ms,
            payload=PersistCompletedPayload(
                document_id=doc_id,
                statement_id=str(result.statement.id),
                promoted_counts=record_counts,
            ).model_dump(),
        )

    except Exception as exc:
        logger.exception("persist_node.error", error=str(exc))
        state.setdefault("errors", []).append(f"Persistence failed: {exc}")
        await _emit(
            state,
            event_type="error",
            stage="persist_canonical",
            message=f"Database write failed: {exc}",
            status="failed",
            progress=0.7,
        )

    return state


async def embed_node(state: IngestionState) -> IngestionState:
    """Chunk and embed the document text into Chroma."""
    from app.services.embedding_service import EmbeddingService

    parsed = state.get("parsed_document")
    result = state.get("extraction_result")
    doc_id = state.get("document_id")

    if not parsed or not doc_id:
        return state

    # Estimate chunk count (embedding service decides final split)
    total_chars = sum(len(p.text or "") for p in parsed.pages)
    estimated_chunks = max(1, total_chars // 512)

    await _emit(
        state,
        event_type="embedding_started_v2",
        stage="embed_chunks",
        message=f"Embedding ~{estimated_chunks} text chunk(s) into vector store",
        status="started",
        progress=0.75,
        payload=EmbeddingStartedPayload(
            document_id=doc_id,
            chunk_count=estimated_chunks,
        ).model_dump(),
    )

    t0 = time.monotonic()
    try:
        service = EmbeddingService()
        statement_id = str(result.statement.id) if result and result.statement else None
        institution = state.get("institution_type", InstitutionType.UNKNOWN)
        await service.embed_document(
            document=parsed,
            document_id=doc_id,
            statement_id=statement_id,
            institution_type=institution,
        )
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.info("embed_node.done", document_id=doc_id)

        await _emit(
            state,
            event_type="embedding_completed",
            stage="embed_chunks",
            message="Document indexed in vector store — now searchable",
            status="complete",
            progress=0.9,
            duration_ms=duration_ms,
            payload=EmbeddingCompletedPayload(
                document_id=doc_id,
                embedded_count=estimated_chunks,
                skipped_count=0,
            ).model_dump(),
        )

    except Exception as exc:
        logger.exception("embed_node.error", error=str(exc))
        state.setdefault("warnings", []).append(f"Embedding failed (non-fatal): {exc}")
        await _emit(
            state,
            event_type="warning",
            stage="embed_chunks",
            message=f"Embedding failed (document still usable): {exc}",
            status="warning",
            progress=0.9,
        )

    return state


async def report_node(state: IngestionState) -> IngestionState:
    """Finalize state, log summary, emit terminal ingestion event."""
    result = state.get("extraction_result")
    errors = state.get("errors", [])
    warnings = state.get("warnings", [])
    doc_id = state.get("document_id", "")
    institution = state.get("institution_type", InstitutionType.UNKNOWN)

    overall_status = "success" if not errors else "partial" if result else "failed"
    overall_confidence = result.overall_confidence if result else 0.0

    logger.info(
        "ingestion.complete",
        document_id=doc_id,
        institution=institution.value if hasattr(institution, "value") else str(institution),
        status=result.status.value if result else "unknown",
        confidence=overall_confidence,
        error_count=len(errors),
    )

    await _emit(
        state,
        event_type="ingestion_pipeline_complete",
        stage="finalize",
        message=(
            f"Ingestion complete — {overall_status} "
            f"({len(errors)} error(s), {len(warnings)} warning(s))"
        ),
        status="complete" if not errors else "warning",
        progress=1.0,
        warnings=warnings,
        payload=IngestionCompletePayload(
            document_id=doc_id,
            institution=institution.value if hasattr(institution, "value") else str(institution),
            statement_type=state.get("statement_type", "unknown"),
            overall_status=overall_status,
            overall_confidence=overall_confidence,
            error_count=len(errors),
            warning_count=len(warnings),
            review_item_count=0,  # Phase 2.2 will populate this
        ).model_dump(),
    )

    return state


# ── Routing logic ──────────────────────────────────────────────────────────────

def route_to_institution(state: IngestionState) -> str:
    """
    Conditional edge function — routes to the correct institution node.

    LangGraph calls this after classify_node to determine which node runs next.
    """
    institution = state.get("institution_type", InstitutionType.UNKNOWN)
    route_map = {
        InstitutionType.MORGAN_STANLEY: "morgan_stanley",
        InstitutionType.CHASE: "chase",
        InstitutionType.ETRADE: "etrade",
        InstitutionType.UNKNOWN: "unknown",
    }
    return route_map.get(institution, "unknown")


# ── Graph construction ─────────────────────────────────────────────────────────

def build_ingestion_graph() -> StateGraph:
    """
    Build and compile the document ingestion LangGraph.

    Returns a compiled StateGraph ready to be invoked with an IngestionState.
    """
    graph = StateGraph(IngestionState)

    # Register nodes
    graph.add_node("parse", parse_node)
    graph.add_node("classify", classify_node)
    graph.add_node("morgan_stanley", morgan_stanley_node)
    graph.add_node("chase", chase_node)
    graph.add_node("etrade", etrade_node)
    graph.add_node("unknown", unknown_institution_node)
    graph.add_node("persist", persist_node)
    graph.add_node("embed", embed_node)
    graph.add_node("report", report_node)

    # Linear edges
    graph.add_edge(START, "parse")
    graph.add_edge("parse", "classify")

    # Conditional routing after classification
    graph.add_conditional_edges(
        "classify",
        route_to_institution,
        {
            "morgan_stanley": "morgan_stanley",
            "chase": "chase",
            "etrade": "etrade",
            "unknown": "unknown",
        },
    )

    # All institution paths converge to persist → embed → report
    for institution_node in ("morgan_stanley", "chase", "etrade", "unknown"):
        graph.add_edge(institution_node, "persist")

    graph.add_edge("persist", "embed")
    graph.add_edge("embed", "report")
    graph.add_edge("report", END)

    return graph.compile()


# Module-level compiled graph — import and invoke this
ingestion_graph = build_ingestion_graph()
