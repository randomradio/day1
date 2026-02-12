"""Relation engine: entity relationship graph operations."""

from __future__ import annotations

from collections import deque

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from branchedmind.db.models import Relation


class RelationEngine:
    """Manages entity relationships (knowledge graph edges)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def write_relation(
        self,
        source_entity: str,
        target_entity: str,
        relation_type: str,
        properties: dict | None = None,
        confidence: float = 1.0,
        session_id: str | None = None,
        branch_name: str = "main",
    ) -> Relation:
        """Write an entity relationship.

        Args:
            source_entity: Source entity name.
            target_entity: Target entity name.
            relation_type: Type of relation (depends_on, causes, fixes, etc.).
            properties: Relation metadata.
            confidence: Confidence score.
            session_id: Associated session.
            branch_name: Target branch.

        Returns:
            Created Relation object.
        """
        rel = Relation(
            source_entity=source_entity,
            target_entity=target_entity,
            relation_type=relation_type,
            properties=properties,
            confidence=confidence,
            session_id=session_id,
            branch_name=branch_name,
        )
        self._session.add(rel)
        await self._session.commit()
        return rel

    async def graph_query(
        self,
        entity: str,
        relation_type: str | None = None,
        depth: int = 1,
        branch_name: str = "main",
    ) -> list[dict]:
        """Query entity relationship graph with BFS traversal.

        Args:
            entity: Starting entity name.
            relation_type: Optional filter by relation type.
            depth: BFS traversal depth (default 1).
            branch_name: Branch to query.

        Returns:
            List of relation dicts with source, target, relation, properties.
        """
        visited: set[str] = set()
        seen_rel_ids: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(entity, 0)])
        results: list[dict] = []

        while queue:
            current, current_depth = queue.popleft()
            if current in visited or current_depth >= depth:
                continue
            visited.add(current)

            stmt = (
                select(Relation)
                .where(
                    Relation.branch_name == branch_name,
                    Relation.valid_to.is_(None),
                    or_(
                        Relation.source_entity == current,
                        Relation.target_entity == current,
                    ),
                )
            )
            if relation_type:
                stmt = stmt.where(Relation.relation_type == relation_type)

            result = await self._session.execute(stmt)
            relations = result.scalars().all()

            for rel in relations:
                if rel.id in seen_rel_ids:
                    continue
                seen_rel_ids.add(rel.id)
                results.append({
                    "source": rel.source_entity,
                    "target": rel.target_entity,
                    "relation": rel.relation_type,
                    "properties": rel.properties,
                    "confidence": rel.confidence,
                    "id": rel.id,
                })
                # Enqueue neighbors
                neighbor = (
                    rel.target_entity
                    if rel.source_entity == current
                    else rel.source_entity
                )
                if neighbor not in visited:
                    queue.append((neighbor, current_depth + 1))

        return results

    async def list_relations(
        self,
        branch_name: str = "main",
        source_entity: str | None = None,
        target_entity: str | None = None,
        relation_type: str | None = None,
        limit: int = 50,
    ) -> list[Relation]:
        """List relations with optional filters."""
        stmt = (
            select(Relation)
            .where(
                Relation.branch_name == branch_name,
                Relation.valid_to.is_(None),
            )
            .order_by(Relation.created_at.desc())
            .limit(limit)
        )
        if source_entity:
            stmt = stmt.where(Relation.source_entity == source_entity)
        if target_entity:
            stmt = stmt.where(Relation.target_entity == target_entity)
        if relation_type:
            stmt = stmt.where(Relation.relation_type == relation_type)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
