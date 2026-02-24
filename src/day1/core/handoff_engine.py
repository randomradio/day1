"""Handoff engine: structured task handoff with verified facts.

Provides a protocol for handing off task context between agents/sessions:
1. Freeze context: collect verified facts, key conversations, summary
2. Create handoff record (audit trail)
3. Prepare handoff packet for the receiving agent
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.exceptions import HandoffError, TaskNotFoundError
from day1.db.models import (
    Conversation,
    Fact,
    HandoffRecord,
    Message,
    Task,
    TaskAgent,
)

logger = logging.getLogger(__name__)


class HandoffEngine:
    """Manages structured task handoffs between agents and sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_handoff(
        self,
        source_branch: str,
        target_branch: str,
        handoff_type: str = "task_continuation",
        source_task_id: str | None = None,
        target_task_id: str | None = None,
        source_agent_id: str | None = None,
        target_agent_id: str | None = None,
        include_unverified: bool = False,
        fact_ids: list[str] | None = None,
        conversation_ids: list[str] | None = None,
        context_summary: str | None = None,
    ) -> dict:
        """Create a handoff record with frozen context.

        By default, only includes verified facts. Unverified facts are
        excluded unless explicitly opted in.

        Args:
            source_branch: Branch with the source context.
            target_branch: Branch receiving the handoff.
            handoff_type: Type of handoff (task_continuation, agent_switch,
                         session_handoff, escalation).
            source_task_id: Source task ID (optional).
            target_task_id: Target task ID (optional).
            source_agent_id: Source agent ID (optional).
            target_agent_id: Target agent ID (optional).
            include_unverified: Whether to include unverified facts.
            fact_ids: Specific fact IDs to include (overrides auto-selection).
            conversation_ids: Specific conversation IDs to include.
            context_summary: Manual context summary.

        Returns:
            Dict with handoff_id and the handoff packet.
        """
        if handoff_type not in (
            "task_continuation", "agent_switch", "session_handoff", "escalation",
        ):
            raise HandoffError(f"Invalid handoff type: {handoff_type}")

        # Collect facts
        if fact_ids:
            selected_fact_ids = fact_ids
        else:
            selected_fact_ids = await self._collect_facts(
                source_branch, include_unverified
            )

        # Collect conversations
        if conversation_ids:
            selected_conv_ids = conversation_ids
        else:
            selected_conv_ids = await self._collect_conversations(
                source_branch, limit=5
            )

        # Generate summary if not provided
        if not context_summary:
            context_summary = await self._generate_summary(
                source_branch, selected_fact_ids, selected_conv_ids,
            )

        # Create handoff record
        record = HandoffRecord(
            source_task_id=source_task_id,
            target_task_id=target_task_id,
            source_branch=source_branch,
            target_branch=target_branch,
            source_agent_id=source_agent_id,
            target_agent_id=target_agent_id,
            handoff_type=handoff_type,
            fact_ids=selected_fact_ids,
            conversation_ids=selected_conv_ids,
            context_summary=context_summary,
            verification_status="verified" if not include_unverified else "partial",
        )
        self._session.add(record)
        await self._session.commit()
        await self._session.refresh(record)

        return {
            "handoff_id": record.id,
            "source_branch": source_branch,
            "target_branch": target_branch,
            "handoff_type": handoff_type,
            "fact_count": len(selected_fact_ids),
            "conversation_count": len(selected_conv_ids),
            "verification_status": record.verification_status,
            "context_summary": context_summary,
        }

    async def get_handoff_packet(
        self,
        handoff_id: str,
        include_messages: bool = True,
        message_limit: int = 50,
    ) -> dict:
        """Retrieve the full handoff packet for a receiving agent.

        Returns all facts, conversations (with messages), and the summary.

        Args:
            handoff_id: Handoff record ID.
            include_messages: Whether to include conversation messages.
            message_limit: Max messages per conversation.

        Returns:
            Full handoff packet dict.
        """
        result = await self._session.execute(
            select(HandoffRecord).where(HandoffRecord.id == handoff_id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise HandoffError(f"Handoff record {handoff_id} not found")

        # Load facts
        facts = []
        for fid in (record.fact_ids or []):
            fact_result = await self._session.execute(
                select(Fact).where(Fact.id == fid)
            )
            fact = fact_result.scalar_one_or_none()
            if fact:
                facts.append({
                    "id": fact.id,
                    "fact_text": fact.fact_text,
                    "category": fact.category,
                    "confidence": fact.confidence,
                    "verification_status": (fact.metadata_json or {}).get(
                        "verification_status", "unverified"
                    ),
                })

        # Load conversations
        conversations = []
        for cid in (record.conversation_ids or []):
            conv_result = await self._session.execute(
                select(Conversation).where(Conversation.id == cid)
            )
            conv = conv_result.scalar_one_or_none()
            if not conv:
                continue

            conv_dict: dict = {
                "id": conv.id,
                "title": conv.title,
                "status": conv.status,
                "message_count": conv.message_count,
            }

            if include_messages:
                msg_result = await self._session.execute(
                    select(Message)
                    .where(Message.conversation_id == cid)
                    .order_by(Message.sequence_num.asc())
                    .limit(message_limit)
                )
                messages = msg_result.scalars().all()
                conv_dict["messages"] = [
                    {
                        "role": m.role,
                        "content": m.content,
                        "sequence_num": m.sequence_num,
                    }
                    for m in messages
                ]

            conversations.append(conv_dict)

        return {
            "handoff_id": record.id,
            "handoff_type": record.handoff_type,
            "source_branch": record.source_branch,
            "target_branch": record.target_branch,
            "source_agent_id": record.source_agent_id,
            "target_agent_id": record.target_agent_id,
            "verification_status": record.verification_status,
            "context_summary": record.context_summary,
            "facts": facts,
            "conversations": conversations,
            "created_at": (
                record.created_at.isoformat() if record.created_at else None
            ),
        }

    async def list_handoffs(
        self,
        source_branch: str | None = None,
        target_branch: str | None = None,
        handoff_type: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """List handoff records with optional filters."""
        stmt = (
            select(HandoffRecord)
            .order_by(HandoffRecord.created_at.desc())
            .limit(limit)
        )
        if source_branch:
            stmt = stmt.where(HandoffRecord.source_branch == source_branch)
        if target_branch:
            stmt = stmt.where(HandoffRecord.target_branch == target_branch)
        if handoff_type:
            stmt = stmt.where(HandoffRecord.handoff_type == handoff_type)

        result = await self._session.execute(stmt)
        return [
            {
                "id": r.id,
                "source_branch": r.source_branch,
                "target_branch": r.target_branch,
                "handoff_type": r.handoff_type,
                "fact_count": len(r.fact_ids or []),
                "conversation_count": len(r.conversation_ids or []),
                "verification_status": r.verification_status,
                "context_summary": r.context_summary,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in result.scalars().all()
        ]

    async def _collect_facts(
        self,
        branch_name: str,
        include_unverified: bool = False,
    ) -> list[str]:
        """Collect fact IDs from a branch, preferring verified facts."""
        result = await self._session.execute(
            select(Fact).where(
                Fact.branch_name == branch_name,
                Fact.status == "active",
            )
        )
        facts = list(result.scalars().all())

        selected = []
        for fact in facts:
            status = (fact.metadata_json or {}).get("verification_status", "unverified")
            if status == "verified":
                selected.append(fact.id)
            elif include_unverified and status != "invalidated":
                selected.append(fact.id)

        return selected

    async def _collect_conversations(
        self,
        branch_name: str,
        limit: int = 5,
    ) -> list[str]:
        """Collect recent conversation IDs from a branch."""
        result = await self._session.execute(
            select(Conversation.id)
            .where(
                Conversation.branch_name == branch_name,
                Conversation.status.in_(["active", "completed"]),
            )
            .order_by(Conversation.created_at.desc())
            .limit(limit)
        )
        return [row[0] for row in result.fetchall()]

    async def _generate_summary(
        self,
        branch_name: str,
        fact_ids: list[str],
        conversation_ids: list[str],
    ) -> str:
        """Generate a text summary of the handoff context."""
        parts = [f"Handoff from branch '{branch_name}'."]

        if fact_ids:
            result = await self._session.execute(
                select(Fact).where(Fact.id.in_(fact_ids))
            )
            facts = result.scalars().all()
            fact_texts = [f.fact_text for f in facts]
            parts.append(f"{len(fact_texts)} facts included.")
            if fact_texts:
                parts.append("Key facts: " + "; ".join(fact_texts[:5]))

        if conversation_ids:
            result = await self._session.execute(
                select(Conversation).where(Conversation.id.in_(conversation_ids))
            )
            convs = result.scalars().all()
            titles = [c.title or c.id[:8] for c in convs]
            parts.append(f"{len(titles)} conversations: {', '.join(titles[:5])}")

        return " ".join(parts)
