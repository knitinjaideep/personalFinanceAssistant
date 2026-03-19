"""
Tests for deterministic no-data and partial-data answer builders.

Covers:
- build_no_data_answer: bucket-aware text, no LLM calls
- build_partial_data_answer: sparse-chunk path
- pipeline short-circuits: 0-chunk path → no_data stage
- pipeline short-circuits: 1-2-chunk path → partial_data stage
- LLM NOT called when retrieval is empty
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.schemas.answer_schemas import NoDataAnswer, PartialDataAnswer
from app.rag.retriever import RetrievalResult
from app.services.chat.no_data import (
    build_no_data_answer,
    build_partial_data_answer,
)
from app.services.chat.pipeline import ChatPipeline, PipelineStage


# ── Unit tests for deterministic builders ─────────────────────────────────────


def _empty_retrieval() -> RetrievalResult:
    return RetrievalResult(
        vector_chunks=[],
        sql_results=[],
        sql_query=None,
        context_text="",
    )


def _sparse_retrieval(n: int = 1) -> RetrievalResult:
    return RetrievalResult(
        vector_chunks=[
            {
                "id": f"chunk-{i}",
                "text": "Some excerpt about fees.",
                "metadata": {
                    "institution_type": "chase",
                    "statement_period": "2026-01",
                    "document_id": "doc-1",
                },
                "score": 0.7,
            }
            for i in range(n)
        ],
        sql_results=[],
        sql_query=None,
        context_text="Some excerpt about fees.",
    )


class TestBuildNoDataAnswer:
    def test_returns_no_data_answer_type(self):
        result = build_no_data_answer(
            question="What are my recent transactions?",
            retrieval=_empty_retrieval(),
        )
        assert isinstance(result, NoDataAnswer)
        assert result.answer_type == "no_data"

    def test_confidence_is_zero(self):
        result = build_no_data_answer(
            question="Show my fees.",
            retrieval=_empty_retrieval(),
        )
        assert result.confidence == 0.0

    def test_bucket_aware_summary_with_bucket_and_institution(self):
        result = build_no_data_answer(
            question="Show recent Chase transactions.",
            retrieval=_empty_retrieval(),
            bucket_label="Banking",
            institution_labels=["Chase"],
        )
        assert "Chase" in result.summary
        assert "Banking" in result.summary

    def test_bucket_aware_summary_with_institution_only(self):
        result = build_no_data_answer(
            question="Show Morgan Stanley holdings.",
            retrieval=_empty_retrieval(),
            institution_labels=["Morgan Stanley"],
        )
        assert "Morgan Stanley" in result.summary

    def test_summary_does_not_contain_raw_llm_phrases(self):
        result = build_no_data_answer(
            question="What are my Chase transactions?",
            retrieval=_empty_retrieval(),
        )
        assert "provided context does not" not in result.summary.lower()
        assert "no relevant data was found" not in result.summary.lower()

    def test_has_what_was_checked(self):
        result = build_no_data_answer(
            question="Show my fees.",
            retrieval=_empty_retrieval(),
            bucket_label="Banking",
        )
        assert len(result.what_was_checked) >= 2
        assert any("Banking" in item for item in result.what_was_checked)

    def test_has_possible_reasons(self):
        result = build_no_data_answer(
            question="Show my fees.",
            retrieval=_empty_retrieval(),
        )
        assert len(result.possible_reasons) >= 2

    def test_has_suggested_followups(self):
        result = build_no_data_answer(
            question="Show my transactions.",
            retrieval=_empty_retrieval(),
        )
        assert len(result.suggested_followups) >= 1

    def test_topic_inferred_from_question(self):
        result = build_no_data_answer(
            question="What fees did I pay?",
            retrieval=_empty_retrieval(),
        )
        assert "fee" in result.title.lower()


class TestBuildPartialDataAnswer:
    def test_returns_partial_data_answer_type(self):
        result = build_partial_data_answer(
            question="Show my fees.",
            retrieval=_sparse_retrieval(2),
        )
        assert isinstance(result, PartialDataAnswer)
        assert result.answer_type == "partial_data"

    def test_confidence_is_low(self):
        result = build_partial_data_answer(
            question="Show my fees.",
            retrieval=_sparse_retrieval(2),
        )
        assert result.confidence is not None
        assert result.confidence < 0.5

    def test_summary_mentions_chunk_count(self):
        result = build_partial_data_answer(
            question="Show my fees.",
            retrieval=_sparse_retrieval(2),
        )
        assert "2" in result.summary

    def test_has_what_was_found(self):
        result = build_partial_data_answer(
            question="Show my fees.",
            retrieval=_sparse_retrieval(2),
        )
        assert len(result.what_was_found) >= 1

    def test_has_what_is_missing(self):
        result = build_partial_data_answer(
            question="Show my fees.",
            retrieval=_sparse_retrieval(1),
        )
        assert len(result.what_is_missing) >= 1


# ── Pipeline integration tests ────────────────────────────────────────────────


@pytest.mark.asyncio
class TestPipelineShortCircuit:
    """
    Verify the pipeline takes the deterministic short-circuit path when
    retrieval returns zero or sparse results.
    """

    async def _run_pipeline_collect(
        self, retrieval: RetrievalResult, **kwargs
    ):
        """Patch the retriever and run the pipeline, collecting all items."""
        pipeline = ChatPipeline.__new__(ChatPipeline)
        pipeline._router = MagicMock()
        pipeline._router._config.chat_model = "qwen3:8b"
        pipeline._retriever = MagicMock()
        pipeline._retriever.retrieve = AsyncMock(return_value=retrieval)

        items = []
        from app.services.chat.pipeline import PipelineResult
        async for item in pipeline._execute(
            question="Show my Chase transactions.",
            conversation_history=[],
            bucket_ids=None,
            session_id="test-session",
            bucket_label=kwargs.get("bucket_label"),
            institution_labels=kwargs.get("institution_labels"),
        ):
            items.append(item)
        return items

    async def test_empty_retrieval_uses_no_data_stage(self):
        """0 chunks + 0 SQL rows → PipelineStage.NO_DATA, LLM never called."""
        items = await self._run_pipeline_collect(_empty_retrieval())
        from app.services.chat.pipeline import PipelineResult
        results = [i for i in items if isinstance(i, PipelineResult)]
        assert len(results) == 1
        assert results[0].pipeline_stage == PipelineStage.NO_DATA

    async def test_empty_retrieval_returns_no_data_answer(self):
        items = await self._run_pipeline_collect(_empty_retrieval())
        from app.services.chat.pipeline import PipelineResult
        result = next(i for i in items if isinstance(i, PipelineResult))
        assert result.structured.answer_type == "no_data"

    async def test_empty_retrieval_llm_never_called(self):
        """LLM generate must NOT be called when retrieval is empty."""
        pipeline = ChatPipeline.__new__(ChatPipeline)
        pipeline._router = MagicMock()
        generate_mock = AsyncMock(return_value="some text")
        pipeline._router.generate = generate_mock
        pipeline._router._config.chat_model = "qwen3:8b"
        pipeline._retriever = MagicMock()
        pipeline._retriever.retrieve = AsyncMock(return_value=_empty_retrieval())

        from app.services.chat.pipeline import PipelineResult
        async for _ in pipeline._execute(
            question="Show fees.",
            conversation_history=[],
            bucket_ids=None,
            session_id="test",
        ):
            pass

        generate_mock.assert_not_called()

    async def test_sparse_retrieval_uses_partial_data_stage(self):
        """1–2 chunks + 0 SQL rows → PipelineStage.PARTIAL_DATA, LLM never called."""
        items = await self._run_pipeline_collect(_sparse_retrieval(2))
        from app.services.chat.pipeline import PipelineResult
        results = [i for i in items if isinstance(i, PipelineResult)]
        assert len(results) == 1
        assert results[0].pipeline_stage == PipelineStage.PARTIAL_DATA

    async def test_no_data_answer_is_bucket_aware(self):
        items = await self._run_pipeline_collect(
            _empty_retrieval(),
            bucket_label="Banking",
            institution_labels=["Chase"],
        )
        from app.services.chat.pipeline import PipelineResult
        result = next(i for i in items if isinstance(i, PipelineResult))
        assert result.structured.answer_type == "no_data"
        answer = result.structured
        assert answer.bucket_label == "Banking"
        assert "Chase" in answer.institution_labels

    async def test_no_data_path_emits_chat_no_data_event(self):
        """The chat_no_data SSE event must be emitted on the zero-result path."""
        items = await self._run_pipeline_collect(_empty_retrieval())
        event_types = [
            i.get("event_type")
            for i in items
            if isinstance(i, dict)
        ]
        assert "chat_no_data" in event_types

    async def test_partial_data_path_emits_chat_partial_data_event(self):
        items = await self._run_pipeline_collect(_sparse_retrieval(1))
        event_types = [
            i.get("event_type")
            for i in items
            if isinstance(i, dict)
        ]
        assert "chat_partial_data" in event_types

    async def test_sufficient_data_uses_llm_stage(self):
        """3+ chunks → full LLM path."""
        from app.rag.retriever import RetrievalResult
        rich_retrieval = RetrievalResult(
            vector_chunks=[
                {"id": f"c{i}", "text": "text", "metadata": {}, "score": 0.9}
                for i in range(5)
            ],
            sql_results=[],
            sql_query=None,
            context_text="context",
        )
        pipeline = ChatPipeline.__new__(ChatPipeline)
        pipeline._router = MagicMock()
        pipeline._router._config.chat_model = "qwen3:8b"
        pipeline._router.generate = AsyncMock(return_value="Generated answer text.")
        pipeline._retriever = MagicMock()
        pipeline._retriever.retrieve = AsyncMock(return_value=rich_retrieval)

        from app.services.chat.pipeline import PipelineResult
        results = []
        async for item in pipeline._execute(
            question="Show my fees.",
            conversation_history=[],
            bucket_ids=None,
            session_id="test",
        ):
            if isinstance(item, PipelineResult):
                results.append(item)

        assert len(results) == 1
        assert results[0].pipeline_stage == PipelineStage.LLM
