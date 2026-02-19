"""Conversation engine: lifecycle, fork, and diff for conversations."""

from __future__ import annotations

from difflib import SequenceMatcher

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.exceptions import (
    ConversationNotFoundError,
    MessageNotFoundError,
)
from day1.core.message_engine import MessageEngine
from day1.db.models import Conversation, Message


class ConversationEngine:
    """Manages conversation lifecycle: create, fork, diff, list."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_conversation(
        self,
        session_id: str | None = None,
        agent_id: str | None = None,
        task_id: str | None = None,
        branch_name: str = "main",
        title: str | None = None,
        model: str | None = None,
        metadata: dict | None = None,
    ) -> Conversation:
        """Create a new conversation."""
        conv = Conversation(
            session_id=session_id,
            agent_id=agent_id,
            task_id=task_id,
            branch_name=branch_name,
            title=title,
            model=model,
            metadata_json=metadata,
        )
        self._session.add(conv)
        await self._session.commit()
        await self._session.refresh(conv)
        return conv

    async def get_conversation(self, conversation_id: str) -> Conversation:
        """Get a conversation by ID."""
        result = await self._session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            raise ConversationNotFoundError(
                f"Conversation {conversation_id} not found"
            )
        return conv

    async def list_conversations(
        self,
        session_id: str | None = None,
        agent_id: str | None = None,
        task_id: str | None = None,
        branch_name: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]:
        """List conversations with optional filters."""
        stmt = (
            select(Conversation)
            .order_by(Conversation.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if session_id:
            stmt = stmt.where(Conversation.session_id == session_id)
        if agent_id:
            stmt = stmt.where(Conversation.agent_id == agent_id)
        if task_id:
            stmt = stmt.where(Conversation.task_id == task_id)
        if branch_name:
            stmt = stmt.where(Conversation.branch_name == branch_name)
        if status:
            stmt = stmt.where(Conversation.status == status)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def complete_conversation(self, conversation_id: str) -> Conversation:
        """Mark a conversation as completed."""
        await self._session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(status="completed")
        )
        await self._session.commit()
        return await self.get_conversation(conversation_id)

    async def fork_conversation(
        self,
        conversation_id: str,
        fork_at_message_id: str,
        branch_name: str | None = None,
        title: str | None = None,
    ) -> Conversation:
        """Fork a conversation at a specific message point.

        Creates a new conversation that shares history up to the fork point.
        Messages up to (and including) fork_at_message_id are copied.

        Args:
            conversation_id: Source conversation to fork from.
            fork_at_message_id: Message ID to fork at (inclusive).
            branch_name: Optional new branch for the fork.
            title: Optional title for the forked conversation.

        Returns:
            The new forked Conversation.
        """
        source = await self.get_conversation(conversation_id)

        # Verify the fork message exists and belongs to the conversation
        msg_result = await self._session.execute(
            select(Message).where(
                Message.id == fork_at_message_id,
                Message.conversation_id == conversation_id,
            )
        )
        fork_msg = msg_result.scalar_one_or_none()
        if fork_msg is None:
            raise MessageNotFoundError(
                f"Message {fork_at_message_id} not found in conversation {conversation_id}"
            )

        target_branch = branch_name or source.branch_name

        # Create the forked conversation
        forked = Conversation(
            session_id=source.session_id,
            agent_id=source.agent_id,
            task_id=source.task_id,
            branch_name=target_branch,
            title=title or f"Fork of {source.title or source.id[:8]}",
            parent_conversation_id=conversation_id,
            fork_point_message_id=fork_at_message_id,
            model=source.model,
        )
        self._session.add(forked)
        await self._session.commit()
        await self._session.refresh(forked)

        # Copy messages up to and including the fork point
        messages = await self._session.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.sequence_num <= fork_msg.sequence_num,
            )
            .order_by(Message.sequence_num.asc())
        )
        copied_count = 0
        total_tokens = 0
        for msg in messages.scalars().all():
            new_msg = Message(
                conversation_id=forked.id,
                session_id=msg.session_id,
                agent_id=msg.agent_id,
                role=msg.role,
                content=msg.content,
                thinking=msg.thinking,
                tool_calls_json=msg.tool_calls_json,
                token_count=msg.token_count,
                model=msg.model,
                parent_message_id=msg.parent_message_id,
                sequence_num=msg.sequence_num,
                embedding=msg.embedding,
                branch_name=target_branch,
                metadata_json=msg.metadata_json,
            )
            self._session.add(new_msg)
            copied_count += 1
            total_tokens += msg.token_count

        # Update counts on the forked conversation
        await self._session.execute(
            update(Conversation)
            .where(Conversation.id == forked.id)
            .values(message_count=copied_count, total_tokens=total_tokens)
        )

        # Mark source as forked
        await self._session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(status="forked")
        )

        await self._session.commit()
        return await self.get_conversation(forked.id)

    async def diff_conversations(
        self,
        conversation_a_id: str,
        conversation_b_id: str,
    ) -> dict:
        """Compare two conversations using LCS-based diff.

        Returns a summary of how the two conversations diverge.
        """
        msgs_a = await self._session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_a_id)
            .order_by(Message.sequence_num.asc())
        )
        msgs_b = await self._session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_b_id)
            .order_by(Message.sequence_num.asc())
        )

        list_a = list(msgs_a.scalars().all())
        list_b = list(msgs_b.scalars().all())

        # Build content sequences for diffing
        seq_a = [f"{m.role}:{(m.content or '')[:200]}" for m in list_a]
        seq_b = [f"{m.role}:{(m.content or '')[:200]}" for m in list_b]

        matcher = SequenceMatcher(None, seq_a, seq_b)
        ops = matcher.get_opcodes()

        diff_entries = []
        for tag, i1, i2, j1, j2 in ops:
            if tag == "equal":
                continue
            entry = {"op": tag}
            if tag in ("delete", "replace"):
                entry["a_messages"] = [
                    {"seq": list_a[i].sequence_num, "role": list_a[i].role,
                     "content": (list_a[i].content or "")[:200]}
                    for i in range(i1, i2)
                ]
            if tag in ("insert", "replace"):
                entry["b_messages"] = [
                    {"seq": list_b[j].sequence_num, "role": list_b[j].role,
                     "content": (list_b[j].content or "")[:200]}
                    for j in range(j1, j2)
                ]
            diff_entries.append(entry)

        return {
            "conversation_a": conversation_a_id,
            "conversation_b": conversation_b_id,
            "a_message_count": len(list_a),
            "b_message_count": len(list_b),
            "similarity": round(matcher.ratio(), 3),
            "diff": diff_entries,
        }

    async def get_conversation_by_session(
        self, session_id: str, status: str = "active"
    ) -> Conversation | None:
        """Get the active conversation for a session."""
        result = await self._session.execute(
            select(Conversation)
            .where(
                Conversation.session_id == session_id,
                Conversation.status == status,
            )
            .order_by(Conversation.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
