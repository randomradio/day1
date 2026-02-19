"""Scoring engine: LLM-as-judge for conversations and messages."""

from __future__ import annotations

import json
import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from branchedmind.core.exceptions import ConversationNotFoundError
from branchedmind.db.models import Conversation, Message, Score

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default dimensions an LLM judge evaluates
# ---------------------------------------------------------------------------

DEFAULT_DIMENSIONS = [
    "helpfulness",
    "correctness",
    "coherence",
    "efficiency",
]

SYSTEM_PROMPT = """\
You are an expert evaluator of AI agent conversations. You score conversations \
on specific quality dimensions.

For each dimension you are asked to evaluate, return a JSON object with:
- "value": a float from 0.0 (worst) to 1.0 (best)
- "explanation": a 1-2 sentence justification

Be calibrated: 0.5 is mediocre, 0.7 is good, 0.9+ is exceptional.

Dimension definitions:
- helpfulness: Did the agent actually solve the user's problem or answer their question?
- correctness: Are the agent's statements, code, and tool calls factually/technically correct?
- coherence: Is the conversation logical, well-structured, and free of contradictions?
- efficiency: Did the agent solve the problem without unnecessary steps, tool calls, or verbosity?
- safety: Did the agent avoid harmful, biased, or insecure outputs?
- instruction_following: Did the agent follow the user's instructions precisely?
- creativity: Did the agent show novel or insightful problem-solving?
- completeness: Did the agent fully address all parts of the request?

You may also receive custom dimensions not listed above. Evaluate them as best you can.
"""

EVAL_PROMPT_TEMPLATE = """\
Evaluate the following conversation on these dimensions: {dimensions}

<conversation>
{conversation_text}
</conversation>

Return ONLY valid JSON in this exact format:
{{
  "scores": {{
    "<dimension>": {{
      "value": <float 0.0-1.0>,
      "explanation": "<1-2 sentence justification>"
    }}
  }}
}}
"""


def _format_messages_for_eval(messages: list[Message], max_chars: int = 30000) -> str:
    """Format messages into readable text for the LLM judge."""
    lines = []
    total = 0
    for msg in messages:
        role = msg.role.upper()
        content = msg.content or ""

        # Include tool call info
        if msg.tool_calls:
            try:
                tools = (
                    json.loads(msg.tool_calls)
                    if isinstance(msg.tool_calls, str)
                    else msg.tool_calls
                )
                tool_names = (
                    [t.get("name", "?") for t in tools]
                    if isinstance(tools, list)
                    else []
                )
                if tool_names:
                    content += f"\n[Tool calls: {', '.join(tool_names)}]"
            except (json.JSONDecodeError, TypeError):
                pass

        line = f"[{role}] {content}"

        # Truncate individual messages
        if len(line) > 2000:
            line = line[:2000] + "..."

        total += len(line)
        if total > max_chars:
            lines.append("[... conversation truncated ...]")
            break
        lines.append(line)

    return "\n\n".join(lines)


async def _call_llm_judge(
    messages_text: str,
    dimensions: list[str],
    llm_client: object | None = None,
) -> dict[str, tuple[float, str]]:
    """Call LLM to judge a conversation.

    Returns dict of dimension -> (value, explanation).
    Falls back to a neutral score if LLM is unavailable.
    """
    if llm_client is None:
        from branchedmind.core.llm import get_llm_client

        llm_client = get_llm_client()

    if llm_client is None:
        logger.warning("No LLM configured - returning neutral scores")
        return {
            dim: (0.5, "LLM scorer unavailable - configure BM_LLM_API_KEY")
            for dim in dimensions
        }

    prompt = EVAL_PROMPT_TEMPLATE.format(
        dimensions=", ".join(dimensions),
        conversation_text=messages_text,
    )

    try:
        result = await llm_client.complete_structured(
            prompt=prompt,
            schema={
                "type": "object",
                "properties": {
                    "scores": {
                        "type": "object",
                        "additionalProperties": {
                            "type": "object",
                            "properties": {
                                "value": {"type": "number"},
                                "explanation": {"type": "string"},
                            },
                        },
                    },
                },
            },
            temperature=0.2,
            system_prompt=SYSTEM_PROMPT,
        )
    except Exception as e:
        logger.error("LLM judge call failed: %s", e)
        return {
            dim: (0.5, f"LLM judge error: {e}")
            for dim in dimensions
        }

    scores_raw = result.get("scores", {})
    out: dict[str, tuple[float, str]] = {}
    for dim in dimensions:
        entry = scores_raw.get(dim, {})
        value = float(entry.get("value", 0.5))
        value = max(0.0, min(1.0, value))
        explanation = entry.get("explanation", "No explanation provided")
        out[dim] = (round(value, 3), explanation)

    return out


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ScoringEngine:
    """Score conversations and messages using LLM-as-judge."""

    def __init__(
        self,
        session: AsyncSession,
        llm_client: object | None = None,
    ) -> None:
        self._session = session
        self._llm = llm_client

    async def score_conversation(
        self,
        conversation_id: str,
        dimensions: list[str] | None = None,
        session_id: str | None = None,
    ) -> list[dict]:
        """Score a conversation using LLM-as-judge.

        Args:
            conversation_id: Conversation to score.
            dimensions: Dimensions to evaluate (default: helpfulness,
                        correctness, coherence, efficiency).
            session_id: Session context for the score.

        Returns:
            List of score dicts with id, dimension, value, explanation.
        """
        dims = dimensions or DEFAULT_DIMENSIONS

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

        # Format and judge
        text = _format_messages_for_eval(messages)
        judge_results = await _call_llm_judge(text, dims, self._llm)

        # Persist scores
        results = []
        for dim in dims:
            value, explanation = judge_results.get(
                dim, (0.5, "Dimension not scored")
            )
            score = Score(
                target_type="conversation",
                target_id=conversation_id,
                scorer="llm_judge",
                dimension=dim,
                value=value,
                explanation=explanation,
                branch_name=branch,
                session_id=session_id,
            )
            self._session.add(score)
            results.append(
                {
                    "id": score.id,
                    "dimension": dim,
                    "value": value,
                    "explanation": explanation,
                    "scorer": "llm_judge",
                }
            )

        await self._session.commit()
        return results

    async def score_message(
        self,
        message_id: str,
        dimensions: list[str] | None = None,
    ) -> list[dict]:
        """Score a single message using LLM-as-judge."""
        msg_result = await self._session.execute(
            select(Message).where(Message.id == message_id)
        )
        msg = msg_result.scalar_one_or_none()
        if msg is None:
            return [{"error": f"Message {message_id} not found"}]

        dims = dimensions or DEFAULT_DIMENSIONS
        text = _format_messages_for_eval([msg])
        judge_results = await _call_llm_judge(text, dims, self._llm)

        results = []
        for dim in dims:
            value, explanation = judge_results.get(
                dim, (0.5, "Dimension not scored")
            )
            score = Score(
                target_type="message",
                target_id=message_id,
                scorer="llm_judge",
                dimension=dim,
                value=value,
                explanation=explanation,
                branch_name=msg.branch_name,
            )
            self._session.add(score)
            results.append(
                {
                    "id": score.id,
                    "dimension": dim,
                    "value": value,
                    "explanation": explanation,
                    "scorer": "llm_judge",
                }
            )

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
        """Create a score directly (human annotation or external scorer)."""
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
            select(Score).order_by(Score.created_at.desc()).limit(limit)
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
