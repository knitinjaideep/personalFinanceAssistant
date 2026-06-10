"""
Conversation context service — lightweight in-memory follow-up resolution.

Stores the last resolved entities and intent per conversation so that follow-up
questions can inherit context without repeating themselves:

  User: "How much did I spend on Amex Gold in May?"
  Coral: answers
  User: "What about April?"         ← inherits account=gold, intent=spending_summary
  User: "Break that down by merchant."  ← inherits account, date, changes intent

Design notes:
  - No sensitive raw data (transaction rows) is stored in memory.
  - Only lightweight classification metadata is retained.
  - Sessions are keyed by conversation_id (a UUID from the frontend).
  - TTL of 30 minutes per session; idle sessions are evicted on access.
  - Entirely in-process — no Redis/DB required for local dev.
  - Thread-safe via asyncio.Lock per session.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.logger import get_logger
from app.domain.classification import ExtractedEntities, IntentClassificationResult

logger = get_logger(__name__)

_SESSION_TTL_SECONDS = 1800  # 30 minutes of inactivity evicts the session


@dataclass
class ConversationTurn:
    """One turn of resolved state — what we actually used to answer."""

    intent: str = ""
    data_source: str = ""
    # Normalized entities (post-normalization, not raw LLM output)
    institution: str | None = None
    account_name: str | None = None
    category: str | None = None
    merchant: str | None = None
    date_from: str | None = None       # ISO string
    date_to: str | None = None         # ISO string
    timeframe_label: str = ""
    amount_min: float | None = None
    amount_max: float | None = None
    # Summary of what was returned (not raw rows, just the human label)
    answer_summary: str = ""


@dataclass
class ConversationSession:
    last_access: float = field(default_factory=time.time)
    turns: list[ConversationTurn] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def touch(self) -> None:
        self.last_access = time.time()

    def is_expired(self) -> bool:
        return (time.time() - self.last_access) > _SESSION_TTL_SECONDS

    @property
    def last_turn(self) -> ConversationTurn | None:
        return self.turns[-1] if self.turns else None


class ConversationContextService:
    """Manages per-conversation context for follow-up question resolution."""

    def __init__(self) -> None:
        self._sessions: dict[str, ConversationSession] = {}
        self._global_lock = asyncio.Lock()

    async def _get_or_create(self, conversation_id: str) -> ConversationSession:
        async with self._global_lock:
            session = self._sessions.get(conversation_id)
            if session is None or session.is_expired():
                if session and session.is_expired():
                    logger.info(
                        "conversation_context.evicted",
                        extra={"conversation_id": conversation_id},
                    )
                session = ConversationSession()
                self._sessions[conversation_id] = session
            session.touch()
            return session

    async def record_turn(
        self,
        conversation_id: str,
        *,
        classification: IntentClassificationResult,
        institution: str | None,
        account_name: str | None,
        category: str | None,
        merchant: str | None,
        date_from: str | None,
        date_to: str | None,
        timeframe_label: str,
        amount_min: float | None = None,
        amount_max: float | None = None,
        answer_summary: str = "",
    ) -> None:
        """Save the resolved state for a completed turn."""
        session = await self._get_or_create(conversation_id)
        async with session.lock:
            turn = ConversationTurn(
                intent=classification.intent.value,
                data_source=classification.data_source.value,
                institution=institution,
                account_name=account_name,
                category=category,
                merchant=merchant,
                date_from=date_from,
                date_to=date_to,
                timeframe_label=timeframe_label,
                amount_min=amount_min,
                amount_max=amount_max,
                answer_summary=answer_summary,
            )
            session.turns.append(turn)
            # Keep only the last 10 turns to bound memory usage
            if len(session.turns) > 10:
                session.turns = session.turns[-10:]

        logger.info(
            "conversation_context.turn_recorded",
            extra={
                "conversation_id": conversation_id,
                "intent": turn.intent,
                "institution": turn.institution,
                "account_name": turn.account_name,
                "timeframe_label": turn.timeframe_label,
            },
        )

    async def resolve_followup(
        self,
        conversation_id: str,
        current_classification: IntentClassificationResult,
    ) -> IntentClassificationResult:
        """Merge prior session context into the current classification.

        Rules (applied in order):
        1. If the current classification already has a specific entity, keep it.
        2. If an entity is missing but the prior turn had one, inherit it.
        3. Date range is inherited ONLY when the current question has no time signal
           (type == "none") — explicit date overrides always win.
        4. Intent is never inherited — it is always re-classified per turn.
        """
        session = await self._get_or_create(conversation_id)
        prior = session.last_turn
        if prior is None:
            return current_classification

        ents = current_classification.entities
        changed: list[str] = []

        # Inherit institution
        if not ents.institution and prior.institution:
            ents = ents.model_copy(update={"institution": prior.institution})
            changed.append(f"institution←{prior.institution}")

        # Inherit account
        if not ents.account and prior.account_name:
            ents = ents.model_copy(update={"account": prior.account_name})
            changed.append(f"account←{prior.account_name}")

        # Inherit category (only when no category and no merchant specified)
        if not ents.category and not ents.merchant and prior.category:
            ents = ents.model_copy(update={"category": prior.category})
            changed.append(f"category←{prior.category}")

        # Inherit date range only when question carries no time signal
        if ents.time_range.type == "none" and prior.timeframe_label:
            tr = ents.time_range.model_copy(update={
                "type": "absolute",
                "value": prior.timeframe_label,
                "start_date": prior.date_from,
                "end_date": prior.date_to,
            })
            ents = ents.model_copy(update={"time_range": tr})
            changed.append(f"date←{prior.timeframe_label}")

        # Inherit amount filters
        if ents.amount_min is None and prior.amount_min is not None:
            ents = ents.model_copy(update={"amount_min": prior.amount_min})
            changed.append(f"amount_min←{prior.amount_min}")
        if ents.amount_max is None and prior.amount_max is not None:
            ents = ents.model_copy(update={"amount_max": prior.amount_max})
            changed.append(f"amount_max←{prior.amount_max}")

        if not changed:
            return current_classification

        logger.info(
            "conversation_context.followup_resolved",
            extra={
                "conversation_id": conversation_id,
                "inherited": ", ".join(changed),
            },
        )

        return current_classification.model_copy(update={"entities": ents})

    async def clear_session(self, conversation_id: str) -> None:
        async with self._global_lock:
            self._sessions.pop(conversation_id, None)

    async def evict_expired(self) -> int:
        async with self._global_lock:
            expired = [cid for cid, s in self._sessions.items() if s.is_expired()]
            for cid in expired:
                del self._sessions[cid]
        return len(expired)


# Module-level singleton — imported by chat_router and streaming
conversation_context = ConversationContextService()
