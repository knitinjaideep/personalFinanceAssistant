"""
ChatPipeline — reliable 5-stage chat orchestrator (Phase 4).

Stages:
  1. Retrieve context           (5s timeout)
  2. Build prompt               (sync, no timeout)
  3. LLM generation             (30s timeout + watchdog)
  3b. Fallback: retrieval-only  (if Stage 3 times out / stalls)
  3c. Safe error                (if Stage 3b also fails)
  4. Build structured answer    (sync)
  5. Cache result               (fire-and-forget)

The pipeline never raises HTTP 500.  Every public method returns a
``PipelineResult`` that includes:
- The final answer (StructuredAnswer)
- The prose text
- Sources
- Which stage produced the answer (pipeline_stage)
- Whether a fallback was triggered
- Warning messages

SSE progress events are yielded via an async generator so the chat route
can stream them to the browser.

Usage (non-streaming)::

    pipeline = ChatPipeline()
    result = await pipeline.run(question="...", bucket_ids=[...])

Usage (streaming SSE)::

    async for event in pipeline.stream(question="...", bucket_ids=[...]):
        yield event  # ProcessingEvent dict — caller serialises to SSE
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, List, Optional

import structlog

from app.api.schemas.answer_schemas import PipelineMeta, StructuredAnswer
from app.domain.errors import (
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaStalledException,
)
from app.ollama.model_router import TaskType, get_model_router
from app.rag.prompt_builder import SYSTEM_PROMPT, build_chat_prompt
from app.rag.retriever import HybridRetriever, RetrievalResult
from app.services.answer_builder import build_structured_answer
from app.services.chat.data_availability import (
    build_data_availability_answer,
    is_data_availability_question,
)
from app.services.chat.fallback import build_retrieval_only_answer, build_safe_error_answer
from app.services.chat.no_data import build_no_data_answer, build_partial_data_answer
from app.domain.entities import EmbeddingRecord
from app.domain.enums import InstitutionType

logger = structlog.get_logger(__name__)

# Stage timeouts
_RETRIEVE_TIMEOUT = 5.0    # seconds
_GENERATE_TIMEOUT = 30.0   # seconds


class PipelineStage(str, Enum):
    """Which pipeline stage produced the final answer."""
    LLM = "llm"
    NO_DATA = "no_data"                 # deterministic: zero retrieval results
    PARTIAL_DATA = "partial_data"       # deterministic: sparse retrieval, skip LLM
    RETRIEVAL_ONLY = "retrieval_only"   # fallback 3b: LLM failed, use chunks
    SAFE_ERROR = "safe_error"           # fallback 3c: everything failed


@dataclass
class PipelineResult:
    """Return value of ChatPipeline.run()."""

    answer_text: str
    structured: StructuredAnswer
    sources: List[EmbeddingRecord]
    sql_query_used: Optional[str]
    pipeline_stage: PipelineStage
    fallback_triggered: bool
    fallback_reason: Optional[str]
    warnings: List[str]
    processing_time_seconds: float
    pipeline_meta: PipelineMeta = field(default_factory=PipelineMeta)


class ChatPipeline:
    """
    Reliable 5-stage chat pipeline.  Never raises — all failures produce
    meaningful fallback answers.

    The same instance can be shared across requests (it holds no request state).
    """

    def __init__(self) -> None:
        self._router = get_model_router()
        self._retriever = HybridRetriever()

    # ------------------------------------------------------------------
    # Public: simple awaitable (no SSE)
    # ------------------------------------------------------------------

    async def run(
        self,
        question: str,
        conversation_history: Optional[List[dict]] = None,
        bucket_ids: Optional[List[str]] = None,
        bucket_label: Optional[str] = None,
        institution_labels: Optional[List[str]] = None,
    ) -> PipelineResult:
        """Run the full pipeline and return a PipelineResult."""
        events = []
        result: Optional[PipelineResult] = None
        async for item in self._execute(
            question=question,
            conversation_history=conversation_history or [],
            bucket_ids=bucket_ids,
            session_id=str(uuid.uuid4()),
            bucket_label=bucket_label,
            institution_labels=institution_labels,
        ):
            if isinstance(item, PipelineResult):
                result = item
            # events are discarded in non-streaming mode
        assert result is not None
        return result

    # ------------------------------------------------------------------
    # Public: streaming generator
    # ------------------------------------------------------------------

    async def stream(
        self,
        question: str,
        conversation_history: Optional[List[dict]] = None,
        bucket_ids: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        bucket_label: Optional[str] = None,
        institution_labels: Optional[List[str]] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Yield SSE-ready event dicts, then the final PipelineResult.

        Callers should check ``isinstance(item, PipelineResult)`` to
        distinguish the final result from intermediate events.
        """
        sid = session_id or str(uuid.uuid4())
        async for item in self._execute(
            question=question,
            conversation_history=conversation_history or [],
            bucket_ids=bucket_ids,
            session_id=sid,
            bucket_label=bucket_label,
            institution_labels=institution_labels,
        ):
            yield item

    # ------------------------------------------------------------------
    # Internal pipeline execution
    # ------------------------------------------------------------------

    async def _execute(
        self,
        question: str,
        conversation_history: List[dict],
        bucket_ids: Optional[List[str]],
        session_id: str,
        bucket_label: Optional[str] = None,
        institution_labels: Optional[List[str]] = None,
    ) -> AsyncIterator[Any]:
        """
        Core pipeline — yields event dicts then a PipelineResult.

        Short-circuit paths (no LLM call):
          - 0 chunks AND 0 SQL rows  →  no_data deterministic answer
          - 1–2 chunks AND 0 SQL rows  →  partial_data deterministic answer
        Full LLM path:
          - ≥3 chunks OR any SQL rows  →  generate → structured answer
        """
        pipeline_start = time.monotonic()
        warnings: List[str] = []
        fallback_triggered = False
        fallback_reason: Optional[str] = None

        # ── Stage 0: Data-availability short-circuit ──────────────────
        # Questions like "What data is available?" or "What institutions
        # do I have?" are answered deterministically from metadata tables.
        if is_data_availability_question(question):
            yield _event(
                session_id=session_id,
                event_type="chat_data_availability",
                stage="data_availability",
                message="Checking your data summary…",
                status="started",
                progress=0.10,
            )
            try:
                structured = await build_data_availability_answer(
                    question=question,
                    bucket_ids=bucket_ids,
                )
                processing_time = time.monotonic() - pipeline_start
                meta = PipelineMeta(
                    pipeline_stage="data_availability",
                    fallback_triggered=False,
                    fallback_reason=None,
                    warnings=[],
                )
                yield PipelineResult(
                    answer_text=structured.text,
                    structured=structured,
                    sources=[],
                    sql_query_used=None,
                    pipeline_stage=PipelineStage.LLM,  # reuse LLM stage for compatibility
                    fallback_triggered=False,
                    fallback_reason=None,
                    warnings=[],
                    processing_time_seconds=round(processing_time, 2),
                    pipeline_meta=meta,
                )
                return
            except Exception as exc:
                logger.warning("pipeline.data_availability_error", error=str(exc))
                # Fall through to normal retrieval pipeline

        # ── Stage 1: Retrieve (5s timeout) ────────────────────────────
        yield _event(
            session_id=session_id,
            event_type="chat_retrieve_started",
            stage="retrieve",
            message="Searching your documents…",
            status="started",
            progress=0.05,
        )

        retrieval: Optional[RetrievalResult] = None
        retrieve_warning = False
        try:
            retrieval = await asyncio.wait_for(
                self._retriever.retrieve(question=question, bucket_ids=bucket_ids),
                timeout=_RETRIEVE_TIMEOUT,
            )
            chunk_count = len(retrieval.vector_chunks)
            sql_count = len(retrieval.sql_results or [])
            yield _event(
                session_id=session_id,
                event_type="chat_retrieve_done",
                stage="retrieve",
                message=(
                    f"Found {chunk_count} matching record{'' if chunk_count == 1 else 's'}"
                    + (f" + {sql_count} database rows" if sql_count else "")
                    if chunk_count or sql_count
                    else "No matching records found"
                ),
                status="complete",
                progress=0.20,
                payload={
                    "chunks_found": chunk_count,
                    "sql_rows": sql_count,
                    "has_sql": retrieval.sql_query is not None,
                },
            )
        except asyncio.TimeoutError:
            retrieve_warning = True
            warnings.append("Retrieval timed out after 5s — proceeding with empty context.")
            yield _event(
                session_id=session_id,
                event_type="chat_retrieve_done",
                stage="retrieve",
                message="Search timed out — proceeding without context",
                status="warning",
                progress=0.20,
            )
            retrieval = RetrievalResult(
                vector_chunks=[],
                sql_results=[],
                sql_query=None,
                context_text="",
            )
        except Exception as exc:
            retrieve_warning = True
            warnings.append(f"Retrieval error: {exc}")
            logger.warning("pipeline.retrieve_error", error=str(exc))
            retrieval = RetrievalResult(
                vector_chunks=[],
                sql_results=[],
                sql_query=None,
                context_text="",
            )

        chunk_count = len(retrieval.vector_chunks)
        sql_count = len(retrieval.sql_results or [])
        sources: List[EmbeddingRecord] = _build_sources(retrieval.vector_chunks)

        # ── Short-circuit: zero results → deterministic no-data answer ──
        if chunk_count == 0 and sql_count == 0:
            yield _event(
                session_id=session_id,
                event_type="chat_no_data",
                stage="no_data",
                message="Preparing response…",
                status="complete",
                progress=0.90,
                payload={"skipped_llm": True, "reason": "no_retrieval_results"},
            )
            structured = build_no_data_answer(
                question=question,
                retrieval=retrieval,
                bucket_label=bucket_label,
                institution_labels=institution_labels,
            )
            processing_time = time.monotonic() - pipeline_start
            meta = PipelineMeta(
                pipeline_stage=PipelineStage.NO_DATA.value,
                fallback_triggered=False,
                fallback_reason=None,
                warnings=warnings,
            )
            yield PipelineResult(
                answer_text=structured.summary,
                structured=structured,
                sources=sources,
                sql_query_used=retrieval.sql_query,
                pipeline_stage=PipelineStage.NO_DATA,
                fallback_triggered=False,
                fallback_reason=None,
                warnings=warnings,
                processing_time_seconds=round(processing_time, 2),
                pipeline_meta=meta,
            )
            return

        # ── Short-circuit: sparse results → deterministic partial-data answer ──
        if chunk_count <= 2 and sql_count == 0:
            yield _event(
                session_id=session_id,
                event_type="chat_partial_data",
                stage="partial_data",
                message="Preparing response…",
                status="complete",
                progress=0.90,
                payload={"skipped_llm": True, "reason": "sparse_retrieval", "chunks": chunk_count},
            )
            structured = build_partial_data_answer(
                question=question,
                retrieval=retrieval,
                bucket_label=bucket_label,
                institution_labels=institution_labels,
            )
            processing_time = time.monotonic() - pipeline_start
            meta = PipelineMeta(
                pipeline_stage=PipelineStage.PARTIAL_DATA.value,
                fallback_triggered=False,
                fallback_reason=None,
                warnings=warnings,
            )
            yield PipelineResult(
                answer_text=structured.summary,
                structured=structured,
                sources=sources,
                sql_query_used=retrieval.sql_query,
                pipeline_stage=PipelineStage.PARTIAL_DATA,
                fallback_triggered=False,
                fallback_reason=None,
                warnings=warnings,
                processing_time_seconds=round(processing_time, 2),
                pipeline_meta=meta,
            )
            return

        # ── Stage 2: Build prompt (sync) ──────────────────────────────
        prompt = build_chat_prompt(
            question=question,
            context=retrieval.context_text,
            conversation_history=conversation_history,
        )

        # ── Stage 3: LLM generate (30s + watchdog) ───────────────────
        model = self._router._config.chat_model  # type: ignore[attr-defined]
        yield _event(
            session_id=session_id,
            event_type="chat_generate_started",
            stage="generate",
            message="Generating answer…",
            status="started",
            progress=0.30,
            payload={"model": model},
        )

        gen_start = time.monotonic()
        answer_text: Optional[str] = None
        gen_error: Optional[str] = None
        stage = PipelineStage.LLM

        gen_task = asyncio.create_task(self._generate(prompt, model))

        try:
            answer_text = await asyncio.wait_for(gen_task, timeout=_GENERATE_TIMEOUT)
        except asyncio.TimeoutError:
            gen_task.cancel()
            gen_error = f"LLM generation timed out after {_GENERATE_TIMEOUT}s"
            fallback_triggered = True
            fallback_reason = "timeout"
            warnings.append(gen_error)
        except OllamaStalledException as exc:
            gen_task.cancel()
            gen_error = str(exc)
            fallback_triggered = True
            fallback_reason = "stall"
            warnings.append(f"Generation stalled: {exc}")
        except (OllamaConnectionError, OllamaModelNotFoundError) as exc:
            gen_task.cancel()
            gen_error = str(exc)
            fallback_triggered = True
            fallback_reason = "connection"
            warnings.append(f"Ollama error: {exc}")
        except Exception as exc:
            gen_task.cancel()
            gen_error = str(exc)
            fallback_triggered = True
            fallback_reason = "error"
            warnings.append(f"Generation error: {exc}")

        gen_elapsed_ms = int((time.monotonic() - gen_start) * 1000)

        if fallback_triggered:
            yield _event(
                session_id=session_id,
                event_type="chat_fallback_triggered",
                stage="generate",
                message=f"Generation unavailable ({fallback_reason}) — using retrieval answer",
                status="warning",
                progress=0.75,
                payload={"reason": fallback_reason, "error": gen_error},
            )
        else:
            yield _event(
                session_id=session_id,
                event_type="chat_generate_done",
                stage="generate",
                message="Answer ready",
                status="complete",
                progress=0.75,
                payload={"elapsed_ms": gen_elapsed_ms},
            )

        # ── Stage 3b / 3c: Fallbacks ──────────────────────────────────
        structured: StructuredAnswer

        if fallback_triggered:
            # 3b — retrieval-only answer
            try:
                fallback_structured = build_retrieval_only_answer(
                    question=question,
                    retrieval=retrieval,
                    reason=fallback_reason or "unknown",
                )
                # Extract prose text for backward-compat answer_text field.
                answer_text = getattr(fallback_structured, "text", None) or getattr(fallback_structured, "summary_text", None) or question
                structured = fallback_structured  # type: ignore[assignment]
                stage = PipelineStage.RETRIEVAL_ONLY
            except Exception as exc:
                # 3c — safe error message
                warnings.append(f"Retrieval-only fallback also failed: {exc}")
                safe = build_safe_error_answer(
                    question=question,
                    chunks_found=chunk_count,
                    error_reason=gen_error or str(exc),
                )
                answer_text = safe.text
                structured = safe  # type: ignore[assignment]
                stage = PipelineStage.SAFE_ERROR
        else:
            assert answer_text is not None
            # ── Stage 4: Build structured answer (sync) ───────────────
            structured = build_structured_answer(
                question=question,
                prose_answer=answer_text,
                retrieval=retrieval,
            )

        processing_time = time.monotonic() - pipeline_start

        # Build typed pipeline metadata — carried in the single terminal
        # response_complete event so the frontend has one clean source of truth.
        meta = PipelineMeta(
            pipeline_stage=stage.value,
            fallback_triggered=fallback_triggered,
            fallback_reason=fallback_reason,
            warnings=warnings,
        )

        # NOTE: response_complete (emitted by the route) is the sole terminal
        # event.  No chat_answer_ready emitted here to avoid duplicates.

        yield PipelineResult(
            answer_text=answer_text or "",
            structured=structured,
            sources=sources,
            sql_query_used=retrieval.sql_query,
            pipeline_stage=stage,
            fallback_triggered=fallback_triggered,
            fallback_reason=fallback_reason,
            warnings=warnings,
            processing_time_seconds=round(processing_time, 2),
            pipeline_meta=meta,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _generate(self, prompt: str, model: str) -> str:
        """Call the model router for chat generation."""
        return await self._router.generate(
            task=TaskType.CHAT,
            prompt=prompt,
            system=SYSTEM_PROMPT,
            timeout=int(_GENERATE_TIMEOUT),
        )


# ---------------------------------------------------------------------------
# Event builder helper
# ---------------------------------------------------------------------------

def _event(
    session_id: str,
    event_type: str,
    stage: str,
    message: str,
    status: str = "complete",
    progress: Optional[float] = None,
    payload: Optional[dict] = None,
) -> dict:
    """Build a pipeline event dict compatible with the SSE route."""
    import datetime
    return {
        "session_id": session_id,
        "event_type": event_type,
        "step_name": stage,
        "stage": stage,
        "message": message,
        "status": status,
        "agent_name": "chat_pipeline",
        "progress": progress,
        "payload": payload or {},
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# Source builder (mirrors ChatService._build_sources)
# ---------------------------------------------------------------------------

def _build_sources(chunks: List[dict]) -> List[EmbeddingRecord]:
    import uuid as _uuid
    sources: List[EmbeddingRecord] = []
    for chunk in chunks:
        meta = chunk.get("metadata", {})
        try:
            doc_id = _uuid.UUID(meta.get("document_id", str(_uuid.uuid4())))
            stmt_id_str = meta.get("statement_id", "")
            stmt_id = _uuid.UUID(stmt_id_str) if stmt_id_str else None
            inst_str = meta.get("institution_type", "unknown")
            try:
                inst_type = InstitutionType(inst_str)
            except ValueError:
                inst_type = InstitutionType.UNKNOWN
            sources.append(
                EmbeddingRecord(
                    id=chunk.get("id", str(_uuid.uuid4())),
                    document_id=doc_id,
                    statement_id=stmt_id,
                    chunk_index=meta.get("chunk_index", 0),
                    chunk_text=chunk.get("text", ""),
                    page_number=meta.get("page_number"),
                    section=meta.get("section") or None,
                    institution_type=inst_type,
                    statement_period=meta.get("statement_period") or None,
                )
            )
        except Exception:
            continue
    return sources
