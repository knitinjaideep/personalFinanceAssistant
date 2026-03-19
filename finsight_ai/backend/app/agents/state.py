"""
LangGraph shared agent state definition.

All nodes in the ingestion graph read/write this TypedDict.
Using TypedDict (not a class) keeps state serializable and
compatible with LangGraph's state management.

Design notes:
- State fields are progressively populated as the graph executes.
- Optional fields are None until the relevant node runs.
- Error fields accumulate across nodes (a parse warning doesn't
  stop extraction from running).
"""

from __future__ import annotations

import uuid
from typing import TypedDict

from app.domain.entities import ExtractionResult, StatementDocument
from app.domain.enums import DocumentStatus, ExtractionStatus, InstitutionType, StatementType
from app.parsers.base import ParsedDocument


class IngestionState(TypedDict, total=False):
    """
    State that flows through the document ingestion LangGraph pipeline.

    Fields:
        document_id: UUID of the StatementDocument record
        file_path: Absolute path to the uploaded file
        original_filename: User-provided filename
        document: The StatementDocument domain entity
        parsed_document: Result of PDF parsing
        institution_type: Classified institution
        statement_type: Classified statement type
        classification_confidence: How certain the classifier was
        extraction_result: Full extraction output from institution agent
        errors: List of error messages encountered
        warnings: List of non-fatal warnings
        document_status: Current lifecycle status
        page_count: Number of pages in the document
    """

    document_id: str
    file_path: str
    original_filename: str
    document: StatementDocument
    parsed_document: ParsedDocument
    institution_type: InstitutionType
    statement_type: StatementType
    classification_confidence: float
    extraction_result: ExtractionResult
    errors: list[str]
    warnings: list[str]
    document_status: str   # DocumentStatus enum value
    page_count: int


class ChatState(TypedDict, total=False):
    """
    State for the chat/RAG query graph.

    Fields:
        question: The user's question
        conversation_history: Prior messages for context
        retrieved_chunks: Text chunks from vector search
        sql_results: Results from structured DB queries
        sql_query: The SQL query that was generated
        answer: The final generated answer
        source_ids: IDs of Chroma chunks used
    """

    question: str
    conversation_history: list[dict]
    retrieved_chunks: list[str]
    sql_results: list[dict]
    sql_query: str | None
    answer: str
    source_ids: list[str]
