"""Replay engine: fork a conversation at any message, re-execute with changes."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.conversation_engine import ConversationEngine
from day1.core.exceptions import (
    ConversationNotFoundError,
    MessageNotFoundError,
    ReplayError,
)
from day1.core.message_engine import MessageEngine
from day1.db.models import Conversation, Message

logger = logging.getLogger(__name__)


@dataclass
class ReplayConfig:
    """What to change during replay.

    Attrs:
        system_prompt: Override the system prompt.
        model: Override the model identifier.
        temperature: Override temperature (stored as metadata).
        max_tokens: Override max tokens (stored as metadata).
        tool_filter: If set, only allow these tool names.
        extra_context: Additional text injected before the replay point.
        branch_name: Target branch for the forked conversation.
        title: Title for the replayed conversation.
    """

    system_prompt: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    tool_filter: list[str] | None = None
    extra_context: str | None = None
    branch_name: str | None = None
    title: str | None = None


@dataclass
class ReplayResult:
    """Result of a replay operation.

    Attrs:
        replay_id: Unique identifier for this replay.
        original_conversation_id: Source conversation.
        forked_conversation_id: New conversation created by replay.
        fork_point_message_id: Where the fork happened.
        config: Config used for replay.
        status: pending | ready | error.
        messages_copied: Number of messages copied from original.
        created_at: When the replay was initiated.
        error: Error message if replay failed.
    """

    replay_id: str
    original_conversation_id: str
    forked_conversation_id: str
    fork_point_message_id: str
    config: dict = field(default_factory=dict)
    status: str = "pending"
    messages_copied: int = 0
    created_at: str | None = None
    error: str | None = None


class ReplayEngine:
    """Fork a conversation at any message and prepare for re-execution.

    The replay engine handles the data-layer operations:
    1. Fork the conversation at the specified message
    2. Inject config changes (system prompt, context, model override)
    3. Return the prepared state for the caller to drive LLM execution

    The engine does NOT call the LLM directly — that is the caller's
    responsibility.  This keeps the engine transport-agnostic and testable.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def start_replay(
        self,
        conversation_id: str,
        from_message_id: str,
        config: ReplayConfig | None = None,
    ) -> ReplayResult:
        """Fork a conversation at a message and prepare for replay.

        Args:
            conversation_id: Source conversation to replay from.
            from_message_id: Fork at this message (inclusive — this message
                and all prior are copied to the new conversation).
            config: Optional overrides for the replay.

        Returns:
            ReplayResult with the forked conversation ready for new messages.

        Raises:
            ConversationNotFoundError: Source conversation not found.
            MessageNotFoundError: Fork-point message not found.
            ReplayError: Fork operation failed.
        """
        config = config or ReplayConfig()

        conv_engine = ConversationEngine(self._session)

        try:
            forked = await conv_engine.fork_conversation(
                conversation_id=conversation_id,
                fork_at_message_id=from_message_id,
                branch_name=config.branch_name,
                title=config.title or "Replay",
            )
        except ConversationNotFoundError:
            raise
        except MessageNotFoundError:
            raise
        except Exception as e:
            raise ReplayError(f"Failed to fork conversation: {e}") from e
        copied_count = forked.message_count

        # Apply config overrides to the forked conversation
        update_vals: dict = {}
        metadata = forked.metadata_json or {}

        if config.model:
            update_vals["model"] = config.model
        metadata["replay_of"] = conversation_id
        metadata["replay_from_message"] = from_message_id
        if config.system_prompt:
            metadata["system_prompt_override"] = config.system_prompt
        if config.temperature is not None:
            metadata["temperature"] = config.temperature
        if config.max_tokens is not None:
            metadata["max_tokens"] = config.max_tokens
        if config.tool_filter is not None:
            metadata["tool_filter"] = config.tool_filter

        update_vals["metadata_json"] = metadata
        update_vals["status"] = "replaying"

        await self._session.execute(
            update(Conversation)
            .where(Conversation.id == forked.id)
            .values(**update_vals)
        )
        await self._session.commit()

        # If extra_context is provided, inject it as a system message
        if config.extra_context:
            msg_engine = MessageEngine(self._session, embedder=None)
            await msg_engine.write_message(
                conversation_id=forked.id,
                role="system",
                content=config.extra_context,
                branch_name=config.branch_name or forked.branch_name,
                embed=False,
            )

        config_dict = {
            k: v for k, v in {
                "system_prompt": config.system_prompt,
                "model": config.model,
                "temperature": config.temperature,
                "max_tokens": config.max_tokens,
                "tool_filter": config.tool_filter,
                "extra_context": config.extra_context,
            }.items() if v is not None
        }

        return ReplayResult(
            replay_id=forked.id,
            original_conversation_id=conversation_id,
            forked_conversation_id=forked.id,
            fork_point_message_id=from_message_id,
            config=config_dict,
            status="ready",
            messages_copied=copied_count,
            created_at=(
                forked.created_at.isoformat() if forked.created_at else None
            ),
        )

    async def complete_replay(self, replay_conversation_id: str) -> dict:
        """Mark a replay as completed.

        Args:
            replay_conversation_id: The forked conversation ID.

        Returns:
            Summary dict with message counts and status.
        """
        result = await self._session.execute(
            select(Conversation).where(
                Conversation.id == replay_conversation_id
            )
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            raise ConversationNotFoundError(
                f"Replay conversation {replay_conversation_id} not found"
            )

        await self._session.execute(
            update(Conversation)
            .where(Conversation.id == replay_conversation_id)
            .values(status="completed")
        )
        await self._session.commit()

        return {
            "replay_id": replay_conversation_id,
            "status": "completed",
            "message_count": conv.message_count,
            "total_tokens": conv.total_tokens,
        }

    async def get_replay_context(
        self,
        replay_conversation_id: str,
    ) -> dict:
        """Get the message history for a replay, ready for LLM submission.

        Returns messages in the format expected by most LLM APIs:
        [{role, content, ...}, ...].

        Args:
            replay_conversation_id: The forked conversation ID.

        Returns:
            Dict with messages list, config overrides, and metadata.
        """
        result = await self._session.execute(
            select(Conversation).where(
                Conversation.id == replay_conversation_id
            )
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            raise ConversationNotFoundError(
                f"Replay conversation {replay_conversation_id} not found"
            )

        msgs_result = await self._session.execute(
            select(Message)
            .where(Message.conversation_id == replay_conversation_id)
            .order_by(Message.sequence_num.asc())
        )
        messages = []
        for m in msgs_result.scalars().all():
            msg_dict: dict = {"role": m.role, "content": m.content}
            if m.thinking:
                msg_dict["thinking"] = m.thinking
            if m.tool_calls_json:
                msg_dict["tool_calls"] = m.tool_calls_json
            messages.append(msg_dict)

        metadata = conv.metadata_json or {}
        return {
            "conversation_id": replay_conversation_id,
            "original_conversation_id": metadata.get("replay_of"),
            "messages": messages,
            "model": conv.model,
            "system_prompt_override": metadata.get("system_prompt_override"),
            "temperature": metadata.get("temperature"),
            "max_tokens": metadata.get("max_tokens"),
            "tool_filter": metadata.get("tool_filter"),
        }

    async def diff_replay(
        self,
        replay_conversation_id: str,
    ) -> dict:
        """Diff a replay against its original conversation.

        Args:
            replay_conversation_id: The forked conversation.

        Returns:
            Diff result from ConversationEngine.diff_conversations.

        Raises:
            ConversationNotFoundError: If conversation not found.
            ReplayError: If conversation is not a replay.
        """
        result = await self._session.execute(
            select(Conversation).where(
                Conversation.id == replay_conversation_id
            )
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            raise ConversationNotFoundError(
                f"Conversation {replay_conversation_id} not found"
            )

        metadata = conv.metadata_json or {}
        original_id = metadata.get("replay_of") or conv.parent_conversation_id
        if not original_id:
            raise ReplayError(
                f"Conversation {replay_conversation_id} is not a replay"
            )

        conv_engine = ConversationEngine(self._session)
        diff = await conv_engine.diff_conversations(
            original_id, replay_conversation_id
        )
        diff["replay_config"] = {
            k: metadata.get(k) for k in (
                "system_prompt_override", "temperature",
                "max_tokens", "tool_filter",
            ) if metadata.get(k) is not None
        }
        return diff

    async def list_replays(
        self,
        conversation_id: str | None = None,
        session_id: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """List replay conversations.

        Args:
            conversation_id: Filter replays of a specific conversation.
            session_id: Filter by session.
            limit: Max results.

        Returns:
            List of replay summary dicts.
        """
        stmt = (
            select(Conversation)
            .where(Conversation.status.in_(["replaying", "completed"]))
            .order_by(Conversation.created_at.desc())
            .limit(limit)
        )
        if conversation_id:
            stmt = stmt.where(
                Conversation.parent_conversation_id == conversation_id
            )
        if session_id:
            stmt = stmt.where(Conversation.session_id == session_id)

        result = await self._session.execute(stmt)
        replays = []
        for c in result.scalars().all():
            metadata = c.metadata_json or {}
            replays.append({
                "replay_id": c.id,
                "original_conversation_id": (
                    metadata.get("replay_of") or c.parent_conversation_id
                ),
                "status": c.status,
                "message_count": c.message_count,
                "total_tokens": c.total_tokens,
                "model": c.model,
                "config": {
                    k: metadata.get(k) for k in (
                        "system_prompt_override", "temperature",
                        "max_tokens", "tool_filter",
                    ) if metadata.get(k) is not None
                },
                "created_at": (
                    c.created_at.isoformat() if c.created_at else None
                ),
            })
        return replays
