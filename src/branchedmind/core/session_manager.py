"""Session manager: tracking session lifecycle."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from branchedmind.db.models import Session


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
