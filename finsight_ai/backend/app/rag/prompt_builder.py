"""
RAG prompt assembly.

Builds LLM prompts that combine:
- Conversation history (for multi-turn context)
- Retrieved document excerpts (vector search)
- Structured query results (SQL)
- The user's current question
"""

from __future__ import annotations

SYSTEM_PROMPT = """You are Coral, a private financial intelligence assistant.
You analyze financial statements from multiple institutions (Morgan Stanley, Chase, E*TRADE)
that the user has uploaded locally.

Key rules:
- Answer ONLY based on the provided context (document excerpts and database results)
- If the context doesn't contain enough information to answer, say so clearly
- For monetary amounts, always include the currency (USD unless otherwise noted)
- For fees, distinguish between one-time fees and recurring advisory/management fees
- When comparing periods or accounts, be specific about dates and account identifiers
- Never fabricate financial figures — only cite numbers present in the context
- Keep answers concise but complete

Format:
- Use bullet points for lists of fees, transactions, or accounts
- Use dollar amounts with commas (e.g., $1,234.56)
- Cite the source (institution name, period) when referencing specific data"""


def build_chat_prompt(
    question: str,
    context: str,
    conversation_history: list[dict] | None = None,
) -> str:
    """
    Build a RAG prompt for the chat model.

    Args:
        question: Current user question
        context: Pre-formatted retrieval context (from HybridRetriever)
        conversation_history: List of {"role": ..., "content": ...} dicts

    Returns:
        Complete prompt string ready to send to the LLM.
    """
    parts: list[str] = []

    # Prior conversation context (last 4 exchanges to stay within context window)
    if conversation_history:
        recent = conversation_history[-8:]  # 4 turns = 8 messages
        history_text = "\n".join(
            f"{msg['role'].upper()}: {msg['content']}" for msg in recent
        )
        parts.append(f"=== Prior Conversation ===\n{history_text}")

    # Retrieved context
    if context:
        parts.append(context)

    # Question
    parts.append(f"=== User Question ===\n{question}")
    parts.append("Please answer based on the context above:")

    return "\n\n".join(parts)
