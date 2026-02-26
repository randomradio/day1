"""Conversation cherry-pick: copy conversations or message ranges between branches."""

from __future__ import annotations

import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.branch_manager import BranchManager
from day1.core.exceptions import ConversationNotFoundError
from day1.db.models import Conversation, Fact, Message

logger = logging.getLogger(__name__)


class ConversationCherryPick:
    """Cherry-pick conversations or message ranges between branches."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _rollback_write_failure(self, op_name: str) -> None:
        """Rollback and close the session after failed write-path operations."""
        logger.exception("Write path failed in ConversationCherryPick.%s", op_name)
        await self._session.rollback()
        await self._session.close()

    async def cherry_pick_conversation(
        self,
        conversation_id: str,
        target_branch: str,
        include_messages: bool = True,
    ) -> dict:
        """Copy an entire conversation and its messages to a target branch.

        Args:
            conversation_id: Source conversation to copy.
            target_branch: Branch to copy into.
            include_messages: Whether to copy messages (default True).

        Returns:
            Dict with new conversation_id and messages_copied count.

        Raises:
            ConversationNotFoundError: If source conversation doesn't exist.
        """
        # Load source conversation
        result = await self._session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            raise ConversationNotFoundError(
                f"Conversation {conversation_id} not found"
            )

        try:
            # Create copy on target branch
            new_conv = Conversation(
                session_id=conv.session_id,
                agent_id=conv.agent_id,
                task_id=conv.task_id,
                branch_name=target_branch,
                title=conv.title,
                parent_conversation_id=conv.id,
                status=conv.status,
                message_count=conv.message_count,
                total_tokens=conv.total_tokens,
                model=conv.model,
                metadata_json=conv.metadata_json,
            )
            self._session.add(new_conv)
            await self._session.flush()

            messages_copied = 0
            if include_messages:
                messages_copied = await self._copy_messages(
                    source_conversation_id=conv.id,
                    target_conversation_id=new_conv.id,
                    target_branch=target_branch,
                )

            await self._session.commit()
        except Exception:
            await self._rollback_write_failure("cherry_pick_conversation")
            raise
        await self._session.refresh(new_conv)

        return {
            "conversation_id": new_conv.id,
            "source_conversation_id": conversation_id,
            "target_branch": target_branch,
            "messages_copied": messages_copied,
        }

    async def cherry_pick_message_range(
        self,
        conversation_id: str,
        from_sequence: int,
        to_sequence: int,
        target_branch: str,
        title: str | None = None,
    ) -> dict:
        """Extract a contiguous message range into a new conversation on target branch.

        Creates a new conversation containing only the selected messages,
        renumbered from sequence 1.

        Args:
            conversation_id: Source conversation.
            from_sequence: Start of message range (inclusive).
            to_sequence: End of message range (inclusive).
            target_branch: Branch to create the new conversation on.
            title: Optional title for the new conversation.

        Returns:
            Dict with new conversation_id and messages_copied count.

        Raises:
            ConversationNotFoundError: If source conversation doesn't exist.
        """
        # Load source conversation
        result = await self._session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            raise ConversationNotFoundError(
                f"Conversation {conversation_id} not found"
            )

        # Load messages in range
        msg_result = await self._session.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.sequence_num >= from_sequence,
                Message.sequence_num <= to_sequence,
            )
            .order_by(Message.sequence_num.asc())
        )
        messages = list(msg_result.scalars().all())

        try:
            # Create new conversation on target branch
            new_title = title or (
                f"Extract from {conv.title or conv.id[:8]} "
                f"(seq {from_sequence}-{to_sequence})"
            )
            new_conv = Conversation(
                session_id=conv.session_id,
                agent_id=conv.agent_id,
                task_id=conv.task_id,
                branch_name=target_branch,
                title=new_title,
                parent_conversation_id=conv.id,
                status="active",
                message_count=len(messages),
                total_tokens=sum(m.token_count for m in messages),
                model=conv.model,
                metadata_json={
                    "cherry_picked_from": conversation_id,
                    "original_range": [from_sequence, to_sequence],
                },
            )
            self._session.add(new_conv)
            await self._session.flush()

            # Copy messages with renumbered sequences starting from 1
            for idx, msg in enumerate(messages, start=1):
                new_msg = Message(
                    conversation_id=new_conv.id,
                    session_id=msg.session_id,
                    agent_id=msg.agent_id,
                    role=msg.role,
                    content=msg.content,
                    thinking=msg.thinking,
                    tool_calls_json=msg.tool_calls_json,
                    token_count=msg.token_count,
                    model=msg.model,
                    sequence_num=idx,
                    embedding=msg.embedding,
                    branch_name=target_branch,
                    metadata_json=msg.metadata_json,
                )
                self._session.add(new_msg)

            await self._session.commit()
        except Exception:
            await self._rollback_write_failure("cherry_pick_message_range")
            raise
        await self._session.refresh(new_conv)

        return {
            "conversation_id": new_conv.id,
            "source_conversation_id": conversation_id,
            "target_branch": target_branch,
            "messages_copied": len(messages),
            "original_range": [from_sequence, to_sequence],
        }

    async def cherry_pick_to_curated_branch(
        self,
        branch_name: str,
        parent_branch: str = "main",
        conversation_ids: list[str] | None = None,
        fact_ids: list[str] | None = None,
        description: str | None = None,
    ) -> dict:
        """Create a new branch containing only selected conversations and facts.

        Creates an empty branch (no DATA BRANCH table copies), then cherry-picks
        the specified conversations (with messages) and facts into it.

        Args:
            branch_name: Name for the new curated branch.
            parent_branch: Branch to register as parent.
            conversation_ids: Conversations to include (with all messages).
            fact_ids: Facts to include.
            description: Optional branch description.

        Returns:
            Dict with branch_name and counts of copied items.
        """
        conversation_ids = conversation_ids or []
        fact_ids = fact_ids or []

        # Create branch with no table copies (tables=[])
        mgr = BranchManager(self._session)
        await mgr.create_branch(
            branch_name=branch_name,
            parent_branch=parent_branch,
            description=description or f"Curated branch with {len(conversation_ids)} conversations and {len(fact_ids)} facts",
            tables=[],
        )

        # Cherry-pick conversations
        conversations_copied = 0
        messages_copied = 0
        for conv_id in conversation_ids:
            try:
                result = await self.cherry_pick_conversation(
                    conversation_id=conv_id,
                    target_branch=branch_name,
                    include_messages=True,
                )
                conversations_copied += 1
                messages_copied += result["messages_copied"]
            except ConversationNotFoundError:
                logger.warning("Skipping missing conversation %s", conv_id)

        # Cherry-pick facts
        facts_copied = 0
        try:
            for fact_id in fact_ids:
                result = await self._session.execute(
                    select(Fact).where(Fact.id == fact_id)
                )
                fact = result.scalar_one_or_none()
                if fact is None:
                    logger.warning("Skipping missing fact %s", fact_id)
                    continue
                new_fact = Fact(
                    fact_text=fact.fact_text,
                    embedding=fact.embedding,
                    category=fact.category,
                    confidence=fact.confidence,
                    source_type="cherry_pick",
                    source_id=fact.id,
                    session_id=fact.session_id,
                    branch_name=branch_name,
                    metadata_json=fact.metadata_json,
                )
                self._session.add(new_fact)
                facts_copied += 1

            await self._session.commit()
        except Exception:
            await self._rollback_write_failure("cherry_pick_to_curated_branch")
            raise

        return {
            "branch_name": branch_name,
            "parent_branch": parent_branch,
            "conversations_copied": conversations_copied,
            "messages_copied": messages_copied,
            "facts_copied": facts_copied,
        }

    async def _copy_messages(
        self,
        source_conversation_id: str,
        target_conversation_id: str,
        target_branch: str,
    ) -> int:
        """Copy all messages from one conversation to another.

        Returns:
            Number of messages copied.
        """
        result = await self._session.execute(
            select(Message)
            .where(Message.conversation_id == source_conversation_id)
            .order_by(Message.sequence_num.asc())
        )
        messages = list(result.scalars().all())

        for msg in messages:
            new_msg = Message(
                conversation_id=target_conversation_id,
                session_id=msg.session_id,
                agent_id=msg.agent_id,
                role=msg.role,
                content=msg.content,
                thinking=msg.thinking,
                tool_calls_json=msg.tool_calls_json,
                token_count=msg.token_count,
                model=msg.model,
                sequence_num=msg.sequence_num,
                embedding=msg.embedding,
                branch_name=target_branch,
                metadata_json=msg.metadata_json,
            )
            self._session.add(new_msg)

        return len(messages)
