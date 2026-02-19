"""Session manager: tracking session lifecycle and context handoff."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from branchedmind.db.models import Conversation, Fact, Message, Observation, Session


class SessionManager:
    """Manages session lifecycle and metadata."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_session(
        self,
        session_id: str,
        branch_name: str = "main",
        project_path: str | None = None,
        parent_session: str | None = None,
        metadata: dict | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
    ) -> Session:
        """Register a new session."""
        sess = Session(
            session_id=session_id,
            branch_name=branch_name,
            project_path=project_path,
            parent_session=parent_session,
            metadata_json=metadata,
            task_id=task_id,
            agent_id=agent_id,
        )
        self._session.add(sess)
        await self._session.commit()
        return sess

    async def get_session(self, session_id: str) -> Session | None:
        """Get session by ID."""
        result = await self._session.execute(
            select(Session).where(Session.session_id == session_id)
        )
        return result.scalar_one_or_none()

    async def end_session(self, session_id: str, summary: str | None = None) -> None:
        """Mark a session as completed."""
        await self._session.execute(
            update(Session)
            .where(Session.session_id == session_id)
            .values(
                status="completed",
                summary=summary,
                ended_at=datetime.utcnow(),
            )
        )
        await self._session.commit()

    async def get_recent_sessions(
        self,
        branch_name: str | None = None,
        limit: int = 5,
    ) -> list[Session]:
        """Get recent sessions."""
        stmt = select(Session).order_by(Session.started_at.desc()).limit(limit)
        if branch_name:
            stmt = stmt.where(Session.branch_name == branch_name)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_session_context(
        self,
        session_id: str,
        message_limit: int = 50,
        fact_limit: int = 20,
    ) -> dict:
        """Get full context package from a session for handoff.

        Returns everything a new agent needs to continue where a
        previous session left off: session metadata, conversations
        with messages, facts, and observation summary.

        Args:
            session_id: Session to retrieve context from.
            message_limit: Max messages per conversation.
            fact_limit: Max facts to include.

        Returns:
            Full session context dict.
        """
        sess = await self.get_session(session_id)
        if sess is None:
            return {"error": f"Session {session_id} not found"}

        # Session metadata
        context: dict = {
            "session": {
                "session_id": sess.session_id,
                "status": sess.status,
                "branch_name": sess.branch_name,
                "project_path": sess.project_path,
                "task_id": sess.task_id,
                "agent_id": sess.agent_id,
                "summary": sess.summary,
                "started_at": sess.started_at.isoformat() if sess.started_at else None,
                "ended_at": sess.ended_at.isoformat() if sess.ended_at else None,
            }
        }

        # Conversations from this session
        conv_result = await self._session.execute(
            select(Conversation)
            .where(Conversation.session_id == session_id)
            .order_by(Conversation.created_at.desc())
        )
        conversations = conv_result.scalars().all()

        context["conversations"] = []
        for conv in conversations:
            # Get messages for each conversation
            msg_result = await self._session.execute(
                select(Message)
                .where(Message.conversation_id == conv.id)
                .order_by(Message.sequence_num.asc())
                .limit(message_limit)
            )
            messages = msg_result.scalars().all()

            context["conversations"].append({
                "id": conv.id,
                "title": conv.title,
                "status": conv.status,
                "message_count": conv.message_count,
                "total_tokens": conv.total_tokens,
                "messages": [
                    {
                        "role": m.role,
                        "content": (m.content or "")[:1000],
                        "thinking": (m.thinking or "")[:500] if m.thinking else None,
                        "tool_calls": m.tool_calls_json,
                        "sequence_num": m.sequence_num,
                        "created_at": m.created_at.isoformat() if m.created_at else None,
                    }
                    for m in messages
                ],
            })

        # Facts produced during this session
        fact_result = await self._session.execute(
            select(Fact)
            .where(Fact.session_id == session_id, Fact.status == "active")
            .order_by(Fact.created_at.desc())
            .limit(fact_limit)
        )
        facts = fact_result.scalars().all()
        context["facts"] = [
            {
                "id": f.id,
                "fact_text": f.fact_text,
                "category": f.category,
                "confidence": f.confidence,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in facts
        ]

        # Observation summary (count by type, not full records)
        obs_result = await self._session.execute(
            select(Observation.observation_type, Observation.tool_name)
            .where(Observation.session_id == session_id)
        )
        obs_rows = obs_result.fetchall()
        obs_by_type: dict[str, int] = {}
        tools_used: set[str] = set()
        for obs_type, tool_name in obs_rows:
            obs_by_type[obs_type] = obs_by_type.get(obs_type, 0) + 1
            if tool_name:
                tools_used.add(tool_name)

        context["observations_summary"] = {
            "total": len(obs_rows),
            "by_type": obs_by_type,
            "tools_used": sorted(tools_used),
        }

        return context
