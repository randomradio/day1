"""Observation engine: tool call capture and retrieval."""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from branchedmind.core.embedding import (
    EmbeddingProvider,
    embedding_to_bytes,
    get_embedding_provider,
)
from branchedmind.db.models import Observation


class ObservationEngine:
    """Manages observation records from tool calls."""

    def __init__(
        self,
        session: AsyncSession,
        embedder: EmbeddingProvider | None = None,
    ) -> None:
        self._session = session
        self._embedder = embedder or get_embedding_provider()

    async def write_observation(
        self,
        session_id: str,
        observation_type: str,
        summary: str,
        tool_name: str | None = None,
        raw_input: str | None = None,
        raw_output: str | None = None,
        branch_name: str = "main",
        metadata: dict | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
    ) -> Observation:
        """Write an observation record.

        Args:
            session_id: Session that generated this observation.
            observation_type: Type (tool_use, discovery, decision, error, insight).
            summary: Compressed observation summary.
            tool_name: Tool that was used (Bash, Edit, Read, etc.).
            raw_input: Truncated raw input.
            raw_output: Truncated raw output.
            branch_name: Target branch.
            metadata: Additional metadata.
            task_id: Associated task ID.
            agent_id: Associated agent ID.

        Returns:
            Created Observation object.
        """
        embedding = await self._embedder.embed(summary)

        obs = Observation(
            session_id=session_id,
            observation_type=observation_type,
            tool_name=tool_name,
            summary=summary,
            embedding_blob=embedding_to_bytes(embedding),
            raw_input=raw_input,
            raw_output=raw_output,
            branch_name=branch_name,
            metadata_json=metadata,
            task_id=task_id,
            agent_id=agent_id,
        )
        self._session.add(obs)
        await self._session.flush()

        # Update FTS index
        await self._session.execute(
            text(
                "INSERT INTO observations_fts(id, summary, tool_name) "
                "VALUES (:id, :summary, :tool)"
            ),
            {"id": obs.id, "summary": summary, "tool": tool_name or ""},
        )
        await self._session.commit()
        return obs

    async def get_observation(self, obs_id: str) -> Observation | None:
        """Get single observation by ID."""
        result = await self._session.execute(
            select(Observation).where(Observation.id == obs_id)
        )
        return result.scalar_one_or_none()

    async def list_observations(
        self,
        branch_name: str = "main",
        session_id: str | None = None,
        observation_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Observation]:
        """List observations with filters."""
        stmt = (
            select(Observation)
            .where(Observation.branch_name == branch_name)
            .order_by(Observation.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if session_id:
            stmt = stmt.where(Observation.session_id == session_id)
        if observation_type:
            stmt = stmt.where(Observation.observation_type == observation_type)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def timeline(
        self,
        branch_name: str = "main",
        session_id: str | None = None,
        after: str | None = None,
        before: str | None = None,
        limit: int = 50,
    ) -> list[Observation]:
        """Get chronological observation timeline."""
        stmt = (
            select(Observation)
            .where(Observation.branch_name == branch_name)
            .order_by(Observation.created_at.asc())
            .limit(limit)
        )
        if session_id:
            stmt = stmt.where(Observation.session_id == session_id)
        if after:
            stmt = stmt.where(Observation.created_at >= after)
        if before:
            stmt = stmt.where(Observation.created_at <= before)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
