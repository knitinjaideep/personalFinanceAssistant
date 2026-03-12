"""
Chat endpoint — RAG-powered financial question answering.

Routes:
  POST /api/v1/chat/query         Answer a question (request/response)
  POST /api/v1/chat/stream        Answer a question with streaming SSE events
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.deps import get_chat_service
from app.domain.entities import BucketScopedChatRequest, ChatRequest, ChatResponse
from app.services.chat_service import ChatService

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.post(
    "/query",
    response_model=ChatResponse,
    summary="Ask a financial question",
)
async def query(
    request: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    """
    Answer a natural language question about your financial statements.

    Examples:
    - "How much did I pay in fees in the last 6 months?"
    - "What is my current Morgan Stanley account balance?"
    - "Compare my balances month over month."
    - "What recurring charges do I have?"
    """
    try:
        return await chat_service.answer(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat error: {exc}")


@router.post(
    "/stream",
    summary="Ask a financial question with streaming SSE events + answer",
    response_class=StreamingResponse,
)
async def stream_query(
    request: BucketScopedChatRequest,
    http_request: Request,
    chat_service: ChatService = Depends(get_chat_service),
) -> StreamingResponse:
    """
    Answer a question and stream structured agent trace events via SSE,
    followed by the final answer.

    Event types (in order):
      supervisor_routing → bucket_selected → retrieval_started →
      retrieval_complete → generating_response → response_complete

    The last event has type "response_complete" and includes the full answer
    and source citations in its metadata field.

    Bucket scope:
    - bucket_ids: null  → query all buckets
    - bucket_ids: [id]  → query specific bucket(s)
    """
    session_id = request.session_id or str(uuid.uuid4())

    async def _generate():
        def _sse(data: dict) -> str:
            return f"data: {json.dumps(data)}\n\n"

        def _event(
            event_type: str,
            step: str,
            message: str,
            status: str = "complete",
            agent: str = "supervisor",
            progress: float | None = None,
            metadata: dict | None = None,
        ) -> str:
            return _sse({
                "session_id": session_id,
                "event_type": event_type,
                "step_name": step,
                "message": message,
                "status": status,
                "agent_name": agent,
                "progress": progress,
                "metadata": metadata or {},
                "timestamp": datetime.utcnow().isoformat(),
            })

        try:
            # Determine scope label for UX
            if not request.bucket_ids:
                scope_label = "all buckets"
            elif len(request.bucket_ids) == 1:
                scope_label = f"1 bucket"
            else:
                scope_label = f"{len(request.bucket_ids)} buckets"

            yield _event(
                "supervisor_routing", "route_request",
                f"Routing question to {scope_label}",
                status="started", progress=0.1,
            )

            yield _event(
                "bucket_selected", "select_buckets",
                f"Querying {scope_label}",
                status="complete", progress=0.2,
            )

            yield _event(
                "retrieval_started", "vector_retrieval",
                "Searching document embeddings for relevant context",
                status="started", progress=0.3,
            )

            # Build a ChatRequest from the scoped request
            chat_req = ChatRequest(
                question=request.question,
                conversation_history=request.conversation_history,
            )

            # Pass bucket filter if provided (chat_service needs to support it)
            try:
                if hasattr(chat_service, "answer_scoped") and request.bucket_ids:
                    response = await chat_service.answer_scoped(
                        chat_req, [str(bid) for bid in request.bucket_ids]
                    )
                else:
                    response = await chat_service.answer(chat_req)
            except Exception as exc:
                yield _event(
                    "error", "chat_error",
                    f"An error occurred: {exc}",
                    status="failed",
                )
                yield _sse({"type": "stream_done", "session_id": session_id})
                return

            yield _event(
                "retrieval_complete", "vector_retrieval",
                f"Found {len(response.sources)} relevant document chunk(s)",
                status="complete", progress=0.6,
            )

            yield _event(
                "generating_response", "llm_generation",
                "Generating answer with local Ollama model",
                status="started", agent="ollama", progress=0.8,
            )

            # Final event carries the full answer
            yield _event(
                "response_complete", "finalize",
                "Answer ready",
                status="complete", progress=1.0,
                metadata={
                    "answer": response.answer,
                    "sources": [
                        {
                            "id": s.id,
                            "document_id": s.document_id,
                            "chunk_text": s.chunk_text,
                            "page_number": s.page_number,
                            "section": s.section,
                            "institution_type": s.institution_type,
                            "statement_period": s.statement_period,
                        }
                        for s in response.sources
                    ],
                    "processing_time_seconds": response.processing_time_seconds,
                },
            )

            yield _sse({"type": "stream_done", "session_id": session_id})

        except Exception as exc:
            logger.exception("chat.stream_error", session_id=session_id, error=str(exc))
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
