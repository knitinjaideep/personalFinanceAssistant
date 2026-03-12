"""
LangGraph Supervisor Agent — orchestrates the document ingestion pipeline.

Graph topology:
  START
    │
    ▼
  [ingest_node]        Validate file, create DB record
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

Design decisions:
- The supervisor does NOT contain business logic; it delegates to agents/services.
- Conditional routing (route_node) uses agent.can_handle() scores to pick
  the best-matching agent dynamically. Adding a new institution = adding an
  agent to INSTITUTION_AGENT_REGISTRY.
- Errors at any node add to state["errors"] but don't crash the graph;
  the report_node summarizes the final status.
"""

from __future__ import annotations

import structlog
from langgraph.graph import END, START, StateGraph

from app.agents.institutions.base import BaseInstitutionAgent
from app.agents.institutions.morgan_stanley import MorganStanleyAgent
from app.agents.institutions.chase import ChaseAgent
from app.agents.institutions.etrade import ETradeAgent
from app.agents.state import IngestionState
from app.domain.enums import DocumentStatus, ExtractionStatus, InstitutionType
from app.parsers.pdf_parser import PDFParser

logger = structlog.get_logger(__name__)

# Registry of all available institution agents.
# To add a new institution: instantiate its agent and append it here.
INSTITUTION_AGENT_REGISTRY: list[BaseInstitutionAgent] = [
    MorganStanleyAgent(),
    ChaseAgent(),
    ETradeAgent(),
]


# ── Node functions ─────────────────────────────────────────────────────────────

async def parse_node(state: IngestionState) -> IngestionState:
    """Parse the raw document file into a ParsedDocument."""
    from pathlib import Path

    file_path = state.get("file_path")
    if not file_path:
        state.setdefault("errors", []).append("No file_path in state")
        return state

    parser = PDFParser()
    try:
        parsed = await parser.parse(Path(file_path))
        state["parsed_document"] = parsed
        state["page_count"] = parsed.page_count
        logger.info(
            "parse_node.done",
            pages=parsed.page_count,
            document_id=state.get("document_id"),
        )
    except Exception as exc:
        logger.exception("parse_node.error", error=str(exc))
        state.setdefault("errors", []).append(f"Parse failed: {exc}")
        state["document_status"] = DocumentStatus.FAILED.value

    return state


async def classify_node(state: IngestionState) -> IngestionState:
    """
    Run all institution agents' can_handle() and select the best match.

    Stores the winning institution_type and classification_confidence in state.
    """
    parsed = state.get("parsed_document")
    if not parsed:
        state["institution_type"] = InstitutionType.UNKNOWN
        state["classification_confidence"] = 0.0
        return state

    best_agent: BaseInstitutionAgent | None = None
    best_confidence: float = 0.0

    for agent in INSTITUTION_AGENT_REGISTRY:
        try:
            can_handle, confidence = await agent.can_handle(parsed)
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
        logger.info(
            "classify_node.result",
            institution=best_agent.institution_type.value,
            confidence=best_confidence,
        )
    else:
        state["institution_type"] = InstitutionType.UNKNOWN
        state["classification_confidence"] = 0.0
        state.setdefault("warnings", []).append(
            "Could not identify institution. Document marked as unknown."
        )

    return state


async def morgan_stanley_node(state: IngestionState) -> IngestionState:
    """Run the Morgan Stanley agent."""
    agent = next(
        a for a in INSTITUTION_AGENT_REGISTRY
        if a.institution_type == InstitutionType.MORGAN_STANLEY
    )
    return await agent.run(state)


async def chase_node(state: IngestionState) -> IngestionState:
    """Run the Chase agent."""
    agent = next(
        a for a in INSTITUTION_AGENT_REGISTRY
        if a.institution_type == InstitutionType.CHASE
    )
    return await agent.run(state)


async def etrade_node(state: IngestionState) -> IngestionState:
    """Run the E*TRADE agent."""
    agent = next(
        a for a in INSTITUTION_AGENT_REGISTRY
        if a.institution_type == InstitutionType.ETRADE
    )
    return await agent.run(state)


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
    if not result or not result.statement:
        logger.info("persist_node.skip", reason="no extraction result or statement")
        return state

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
            doc_id = state.get("document_id")
            if doc_id:
                await doc_repo.update_status(
                    uuid.UUID(doc_id), DocumentStatus.PROCESSED
                )

        logger.info("persist_node.done", statement_id=str(result.statement.id))

    except Exception as exc:
        logger.exception("persist_node.error", error=str(exc))
        state.setdefault("errors", []).append(f"Persistence failed: {exc}")

    return state


async def embed_node(state: IngestionState) -> IngestionState:
    """Chunk and embed the document text into Chroma."""
    from app.services.embedding_service import EmbeddingService

    parsed = state.get("parsed_document")
    result = state.get("extraction_result")
    doc_id = state.get("document_id")

    if not parsed or not doc_id:
        return state

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
        logger.info("embed_node.done", document_id=doc_id)
    except Exception as exc:
        logger.exception("embed_node.error", error=str(exc))
        state.setdefault("warnings", []).append(f"Embedding failed (non-fatal): {exc}")

    return state


async def report_node(state: IngestionState) -> IngestionState:
    """Finalize state and log summary."""
    result = state.get("extraction_result")
    errors = state.get("errors", [])

    logger.info(
        "ingestion.complete",
        document_id=state.get("document_id"),
        institution=state.get("institution_type", InstitutionType.UNKNOWN).value
        if state.get("institution_type")
        else "unknown",
        status=result.status.value if result else "unknown",
        confidence=result.overall_confidence if result else 0.0,
        error_count=len(errors),
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
