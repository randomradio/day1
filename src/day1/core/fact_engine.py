"""Fact engine: CRUD operations for structured facts."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.embedding import (
    EmbeddingProvider,
    embedding_to_vecf32,
    get_embedding_provider,
)
from day1.core.exceptions import FactNotFoundError
from day1.db.models import Fact

logger = logging.getLogger(__name__)


class FactEngine:
    """Manages fact lifecycle: create, read, update, search."""

    def __init__(
        self,
        session: AsyncSession,
        embedder: EmbeddingProvider | None = None,
    ) -> None:
        self._session = session
        self._embedder = embedder or get_embedding_provider()

    async def write_fact(
        self,
        fact_text: str,
        category: str | None = None,
        confidence: float = 1.0,
        source_type: str | None = None,
        source_id: str | None = None,
        parent_id: str | None = None,
        session_id: str | None = None,
        branch_name: str = "main",
        metadata: dict | None = None,
    ) -> Fact:
        """Write a new fact to memory.

        Args:
            fact_text: Natural language description of the fact.
            category: Optional category (bug_fix, architecture, preference, etc.).
            confidence: Confidence score 0.0-1.0.
            source_type: Origin type (observation, manual, extraction, merge).
            source_id: Source record ID.
            parent_id: ID of superseded fact.
            session_id: Associated session.
            branch_name: Target branch.
            metadata: Additional metadata.

        Returns:
            The created Fact object.
        """
        # Embedding is non-fatal: capture always succeeds
        embedding_str = None
        try:
            vec = await self._embedder.embed(fact_text)
            embedding_str = embedding_to_vecf32(vec)
        except Exception as e:
            logger.warning("Embedding failed for fact, saving without: %s", e)

        fact = Fact(
            fact_text=fact_text,
            embedding=embedding_str,
            category=category,
            confidence=confidence,
            source_type=source_type,
            source_id=source_id,
            parent_id=parent_id,
            session_id=session_id,
            branch_name=branch_name,
            metadata_json=metadata,
        )
        self._session.add(fact)
        # MO FULLTEXT INDEX auto-indexes — no manual FTS insert needed
        await self._session.commit()
        await self._session.refresh(fact)
        return fact

    async def get_fact(self, fact_id: str) -> Fact:
        """Get a single fact by ID.

        Raises:
            FactNotFoundError: If fact doesn't exist.
        """
        result = await self._session.execute(select(Fact).where(Fact.id == fact_id))
        fact = result.scalar_one_or_none()
        if fact is None:
            raise FactNotFoundError(f"Fact {fact_id} not found")
        return fact

    async def update_fact(
        self,
        fact_id: str,
        fact_text: str | None = None,
        confidence: float | None = None,
        status: str | None = None,
        metadata: dict | None = None,
    ) -> Fact:
        """Update an existing fact.

        Args:
            fact_id: ID of the fact to update.
            fact_text: New text (re-embeds if changed).
            confidence: New confidence score.
            status: New status.
            metadata: New metadata (merged with existing).

        Returns:
            Updated Fact object.
        """
        fact = await self.get_fact(fact_id)
        values: dict = {}

        if fact_text is not None and fact_text != fact.fact_text:
            values["fact_text"] = fact_text
            try:
                vec = await self._embedder.embed(fact_text)
                values["embedding"] = embedding_to_vecf32(vec)
            except Exception as e:
                logger.warning("Embedding failed for fact update, keeping old: %s", e)
            # MO FULLTEXT INDEX auto-updates — no manual FTS ops needed

        if confidence is not None:
            values["confidence"] = confidence
        if status is not None:
            values["status"] = status
        if metadata is not None:
            existing = fact.metadata_json or {}
            existing.update(metadata)
            values["metadata_json"] = existing

        if values:
            values["updated_at"] = datetime.utcnow()
            await self._session.execute(
                update(Fact).where(Fact.id == fact_id).values(**values)
            )
            await self._session.commit()
            return await self.get_fact(fact_id)
        return fact

    async def list_facts(
        self,
        branch_name: str = "main",
        category: str | None = None,
        status: str = "active",
        limit: int = 50,
        offset: int = 0,
    ) -> list[Fact]:
        """List facts on a branch with optional filters."""
        stmt = (
            select(Fact)
            .where(Fact.branch_name == branch_name, Fact.status == status)
            .order_by(Fact.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if category:
            stmt = stmt.where(Fact.category == category)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def supersede_fact(self, old_id: str, new_text: str, **kwargs) -> Fact:
        """Create a new fact that supersedes an old one."""
        await self.update_fact(old_id, status="superseded")
        return await self.write_fact(fact_text=new_text, parent_id=old_id, **kwargs)
