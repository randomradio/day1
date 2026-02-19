"""Scoring engine: pluggable scorers for messages, conversations, and replays."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from branchedmind.core.exceptions import ConversationNotFoundError
from branchedmind.db.models import Conversation, Message, Score

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Scorer protocol
# ---------------------------------------------------------------------------


class Scorer(ABC):
    """Base class for all scorers."""

    name: str = "base"

    @abstractmethod
    async def score(
        self,
        messages: list[Message],
        dimension: str,
    ) -> tuple[float, str]:
        """Score a sequence of messages on a dimension.

        Args:
            messages: The messages to score.
            dimension: What aspect to score.

        Returns:
            (value, explanation) tuple. Value in [0.0, 1.0].
        """


class HeuristicScorer(Scorer):
    """Rule-based scorer using message statistics."""

    name = "heuristic"

    async def score(
        self,
        messages: list[Message],
        dimension: str,
    ) -> tuple[float, str]:
        """Score based on heuristic rules."""
        if dimension == "token_efficiency":
            return self._score_token_efficiency(messages)
        elif dimension == "error_rate":
            return self._score_error_rate(messages)
        elif dimension == "tool_success":
            return self._score_tool_success(messages)
        elif dimension == "conciseness":
            return self._score_conciseness(messages)
        else:
            return 0.5, f"Unknown heuristic dimension: {dimension}"

    def _score_token_efficiency(
        self, messages: list[Message]
    ) -> tuple[float, str]:
        """Lower tokens per assistant message = more efficient."""
        assistant_msgs = [m for m in messages if m.role == "assistant"]
        if not assistant_msgs:
            return 0.5, "No assistant messages"
        total_tokens = sum(m.token_count for m in messages)
        avg = total_tokens / len(assistant_msgs)
        # Heuristic: <500 tokens/response = excellent, >5000 = poor
        if avg <= 500:
            score = 1.0
        elif avg >= 5000:
            score = 0.0
        else:
            score = 1.0 - (avg - 500) / 4500
        return round(score, 3), f"Avg {avg:.0f} tokens per assistant response"

    def _score_error_rate(
        self, messages: list[Message]
    ) -> tuple[float, str]:
        """Fewer errors in tool results = better."""
        tool_results = [m for m in messages if m.role == "tool_result"]
        if not tool_results:
            return 1.0, "No tool results"
        errors = sum(
            1 for m in tool_results
            if m.content and any(
                kw in m.content.lower()
                for kw in ("error", "exception", "failed", "traceback")
            )
        )
        rate = errors / len(tool_results)
        score = max(0.0, 1.0 - rate)
        return round(score, 3), f"{errors}/{len(tool_results)} tool calls errored"

    def _score_tool_success(
        self, messages: list[Message]
    ) -> tuple[float, str]:
        """Ratio of successful tool calls."""
        tool_calls = [m for m in messages if m.role == "tool_call"]
        tool_results = [m for m in messages if m.role == "tool_result"]
        if not tool_calls:
            return 1.0, "No tool calls"
        success = len(tool_results)
        rate = min(1.0, success / len(tool_calls))
        return round(rate, 3), f"{success}/{len(tool_calls)} tool calls got results"

    def _score_conciseness(
        self, messages: list[Message]
    ) -> tuple[float, str]:
        """Fewer messages for same result = more concise."""
        total = len(messages)
        if total <= 5:
            score = 1.0
        elif total >= 50:
            score = 0.2
        else:
            score = 1.0 - (total - 5) / 45 * 0.8
        return round(score, 3), f"{total} total messages"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


SCORERS: dict[str, Scorer] = {
    "heuristic": HeuristicScorer(),
}

HEURISTIC_DIMENSIONS = [
    "token_efficiency",
    "error_rate",
    "tool_success",
    "conciseness",
]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ScoringEngine:
    """Score conversations, messages, and replays."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def score_conversation(
        self,
        conversation_id: str,
        dimensions: list[str] | None = None,
        scorer_name: str = "heuristic",
        session_id: str | None = None,
    ) -> list[dict]:
        """Score a conversation on one or more dimensions.

        Args:
            conversation_id: Conversation to score.
            dimensions: List of dimension names. Defaults to all heuristic.
            scorer_name: Which scorer to use.
            session_id: Session context for the score.

        Returns:
            List of score dicts.
        """
        scorer = SCORERS.get(scorer_name)
        if scorer is None:
            return [{"error": f"Unknown scorer: {scorer_name}"}]

        dims = dimensions or HEURISTIC_DIMENSIONS

        # Load messages
        msgs_result = await self._session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.sequence_num.asc())
        )
        messages = list(msgs_result.scalars().all())
        if not messages:
            raise ConversationNotFoundError(
                f"No messages for conversation {conversation_id}"
            )

        # Get branch from conversation
        conv_result = await self._session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = conv_result.scalar_one_or_none()
        branch = conv.branch_name if conv else "main"

        results = []
        for dim in dims:
            value, explanation = await scorer.score(messages, dim)
            score = Score(
                target_type="conversation",
                target_id=conversation_id,
                scorer=scorer_name,
                dimension=dim,
                value=value,
                explanation=explanation,
                branch_name=branch,
                session_id=session_id,
            )
            self._session.add(score)
            results.append({
                "id": score.id,
                "dimension": dim,
                "value": value,
                "explanation": explanation,
                "scorer": scorer_name,
            })

        await self._session.commit()
        return results

    async def score_message(
        self,
        message_id: str,
        dimensions: list[str] | None = None,
        scorer_name: str = "heuristic",
    ) -> list[dict]:
        """Score a single message."""
        scorer = SCORERS.get(scorer_name)
        if scorer is None:
            return [{"error": f"Unknown scorer: {scorer_name}"}]

        msg_result = await self._session.execute(
            select(Message).where(Message.id == message_id)
        )
        msg = msg_result.scalar_one_or_none()
        if msg is None:
            return [{"error": f"Message {message_id} not found"}]

        dims = dimensions or HEURISTIC_DIMENSIONS
        results = []
        for dim in dims:
            value, explanation = await scorer.score([msg], dim)
            score = Score(
                target_type="message",
                target_id=message_id,
                scorer=scorer_name,
                dimension=dim,
                value=value,
                explanation=explanation,
                branch_name=msg.branch_name,
            )
            self._session.add(score)
            results.append({
                "id": score.id,
                "dimension": dim,
                "value": value,
                "explanation": explanation,
                "scorer": scorer_name,
            })

        await self._session.commit()
        return results

    async def create_score(
        self,
        target_type: str,
        target_id: str,
        scorer: str,
        dimension: str,
        value: float,
        explanation: str | None = None,
        metadata: dict | None = None,
        branch_name: str = "main",
        session_id: str | None = None,
    ) -> dict:
        """Create a score directly (for human annotation or external scorers)."""
        score = Score(
            target_type=target_type,
            target_id=target_id,
            scorer=scorer,
            dimension=dimension,
            value=max(0.0, min(1.0, value)),
            explanation=explanation,
            metadata_json=metadata,
            branch_name=branch_name,
            session_id=session_id,
        )
        self._session.add(score)
        await self._session.commit()
        await self._session.refresh(score)
        return {
            "id": score.id,
            "target_type": target_type,
            "target_id": target_id,
            "dimension": dimension,
            "value": score.value,
            "scorer": scorer,
            "created_at": (
                score.created_at.isoformat() if score.created_at else None
            ),
        }

    async def list_scores(
        self,
        target_type: str | None = None,
        target_id: str | None = None,
        dimension: str | None = None,
        scorer: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """List scores with filters."""
        stmt = (
            select(Score)
            .order_by(Score.created_at.desc())
            .limit(limit)
        )
        if target_type:
            stmt = stmt.where(Score.target_type == target_type)
        if target_id:
            stmt = stmt.where(Score.target_id == target_id)
        if dimension:
            stmt = stmt.where(Score.dimension == dimension)
        if scorer:
            stmt = stmt.where(Score.scorer == scorer)

        result = await self._session.execute(stmt)
        return [
            {
                "id": s.id,
                "target_type": s.target_type,
                "target_id": s.target_id,
                "scorer": s.scorer,
                "dimension": s.dimension,
                "value": s.value,
                "explanation": s.explanation,
                "created_at": (
                    s.created_at.isoformat() if s.created_at else None
                ),
            }
            for s in result.scalars().all()
        ]

    async def get_score_summary(
        self,
        target_type: str,
        target_id: str,
    ) -> dict:
        """Get aggregate scores for a target."""
        result = await self._session.execute(
            select(
                Score.dimension,
                func.avg(Score.value),
                func.count(Score.id),
                func.min(Score.value),
                func.max(Score.value),
            )
            .where(
                Score.target_type == target_type,
                Score.target_id == target_id,
            )
            .group_by(Score.dimension)
        )
        dimensions = {}
        for row in result.fetchall():
            dimensions[row[0]] = {
                "avg": round(float(row[1]), 3),
                "count": row[2],
                "min": round(float(row[3]), 3),
                "max": round(float(row[4]), 3),
            }
        return {
            "target_type": target_type,
            "target_id": target_id,
            "dimensions": dimensions,
        }
