"""
Coral chat guardrails — safety and privacy rules enforced at the boundary
between user input and backend pipeline.

Rules (v1):
  - No external LLM calls for financial data (enforced by architecture).
  - Questions that request destructive actions are rejected.
  - Full account numbers are masked in any answer text.
  - Stack traces are never surfaced to the frontend.
  - No arbitrary SQL execution via chat.

This module provides:
  - sanitize_question(q) -> str  — clean + reject dangerous inputs
  - mask_sensitive(text) -> str  — mask account numbers in answer text
  - is_destructive(q) -> bool    — detect write/delete intent
  - safe_error_message(exc) -> str — convert internal errors to chat-safe text
"""

from __future__ import annotations

import re


# ── Destructive action detection ──────────────────────────────────────────────
# These patterns signal the user wants to modify data — blocked in v1.

_DESTRUCTIVE_PATTERNS = [
    r"\b(?:delete|remove|drop|truncate|wipe|erase)\b.*\b(?:transaction|account|document|statement|data|table|record)\b",
    r"\b(?:update|modify|change|edit|alter|set)\b.*\b(?:amount|balance|transaction|record)\b",
    r"\b(?:insert|add|create|write)\b.*\b(?:transaction|record|entry)\b",
    r"\bexecute\b.*\b(?:sql|query|script)\b",
    r"\brun\b.*\b(?:sql|query|script|command)\b",
    r"\bdrop\s+table\b",
    r"\bdelete\s+from\b",
]

_DESTRUCTIVE_RE = [re.compile(p, re.IGNORECASE) for p in _DESTRUCTIVE_PATTERNS]


def is_destructive(question: str) -> bool:
    """Return True if the question attempts a destructive or write action."""
    return any(p.search(question) for p in _DESTRUCTIVE_RE)


# ── Account number masking ────────────────────────────────────────────────────
# Matches common credit/checking account number patterns.

_ACCOUNT_NUMBER_RE = re.compile(
    r"\b(\d{4})\s*[-–]?\s*\d{4}\s*[-–]?\s*\d{4}\s*[-–]?\s*(\d{4})\b"  # 16-digit card numbers
    r"|"
    r"\bx{4,}\d{4}\b"  # XXXX1234 masked forms (already masked, keep as-is)
    r"|"
    r"\b\d{10,17}\b"   # 10-17 digit bare account numbers
    , re.IGNORECASE,
)


def mask_account_numbers(text: str) -> str:
    """Mask full or partial account numbers in answer text."""
    def _replace(m: re.Match) -> str:
        full = m.group(0)
        # If already masked (XXXX form), leave it alone
        if "x" in full.lower():
            return full
        # Keep only last 4 digits
        digits = re.sub(r"\D", "", full)
        return f"****{digits[-4:]}" if len(digits) >= 4 else "****"

    return _ACCOUNT_NUMBER_RE.sub(_replace, text)


# ── Input sanitization ────────────────────────────────────────────────────────

_MAX_QUESTION_LENGTH = 1000


def sanitize_question(question: str) -> str:
    """Strip and truncate a user question. Raise ValueError if invalid."""
    q = question.strip()
    if not q:
        raise ValueError("Question cannot be empty.")
    if len(q) > _MAX_QUESTION_LENGTH:
        q = q[:_MAX_QUESTION_LENGTH]
    return q


# ── Chat-safe error messages ──────────────────────────────────────────────────

def safe_error_message(exc: BaseException) -> str:
    """Convert an internal exception to a chat-safe string (no stack traces)."""
    exc_type = type(exc).__name__
    msg = str(exc)

    # Connection errors
    if "OllamaConnectionError" in exc_type or "connect" in msg.lower():
        return "Coral's AI model is not reachable right now. Make sure Ollama is running (`ollama serve`)."
    if "OllamaModelNotFoundError" in exc_type or "not found in Ollama" in msg:
        return "The AI model is not installed. Run `ollama pull gemma4` to set it up."

    # Database errors — don't expose schema details
    if "OperationalError" in exc_type or "database" in msg.lower():
        return "There was a database error. Try reprocessing your statements."

    # Generic fallback
    return "Something went wrong. Please try again or rephrase your question."


# ── Answer validation ─────────────────────────────────────────────────────────

_HALLUCINATION_SIGNALS = [
    "as of my knowledge",
    "based on general",
    "i believe",
    "i think",
    "i'm not sure but",
    "it's possible that",
    "typically",
    "in general",
    "usually banks",
    "most financial institutions",
]


def contains_hallucination_signals(answer: str) -> bool:
    """Return True if the answer contains known LLM hallucination phrases."""
    lower = answer.lower()
    return any(signal in lower for signal in _HALLUCINATION_SIGNALS)


def apply_guardrails_to_answer(answer: str) -> str:
    """Apply post-generation guardrails to an answer string.

    - Masks account numbers.
    - Truncates excessively long responses.
    """
    answer = mask_account_numbers(answer)
    # Truncate if model went way over
    if len(answer) > 3000:
        answer = answer[:3000] + "…"
    return answer
