"""Snapshot manager: point-in-time snapshots and time-travel queries."""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from branchedmind.core.exceptions import SnapshotError
from branchedmind.db.models import Fact, Observation, Relation, Snapshot


class SnapshotManager:
    """Manages point-in-time snapshots of memory state."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_snapshot(
        self,
        branch_name: str = "main",
        label: str | None = None,
    ) -> Snapshot:
        """Create a snapshot of current branch state.

        Args:
            branch_name: Branch to snapshot.
            label: Optional human-readable label.

        Returns:
            Created Snapshot object.
        """
        # Capture current state
        facts = await self._session.execute(
            select(Fact).where(
                Fact.branch_name == branch_name, Fact.status == "active"
            )
        )
        relations = await self._session.execute(
            select(Relation).where(
                Relation.branch_name == branch_name, Relation.valid_to.is_(None)
            )
        )
        observations = await self._session.execute(
            select(Observation).where(Observation.branch_name == branch_name)
        )

        snapshot_data = {
            "facts": [
                {
                    "id": f.id,
                    "fact_text": f.fact_text,
                    "category": f.category,
                    "confidence": f.confidence,
                    "created_at": f.created_at.isoformat() if f.created_at else None,
                }
                for f in facts.scalars().all()
            ],
            "relations": [
                {
                    "id": r.id,
                    "source": r.source_entity,
                    "target": r.target_entity,
                    "relation": r.relation_type,
                }
                for r in relations.scalars().all()
            ],
            "observation_count": len(list(observations.scalars().all())),
        }

        snapshot = Snapshot(
            label=label,
            branch_name=branch_name,
            snapshot_data=snapshot_data,
        )
        self._session.add(snapshot)
        await self._session.commit()
        return snapshot

    async def list_snapshots(
        self, branch_name: str | None = None
    ) -> list[Snapshot]:
        """List all snapshots, optionally filtered by branch."""
        stmt = select(Snapshot).order_by(Snapshot.created_at.desc())
        if branch_name:
            stmt = stmt.where(Snapshot.branch_name == branch_name)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_snapshot(self, snapshot_id: str) -> Snapshot:
        """Get a specific snapshot."""
        result = await self._session.execute(
            select(Snapshot).where(Snapshot.id == snapshot_id)
        )
        snapshot = result.scalar_one_or_none()
        if snapshot is None:
            raise SnapshotError(f"Snapshot '{snapshot_id}' not found")
        return snapshot

    async def time_travel_query(
        self,
        timestamp: str,
        branch_name: str = "main",
        category: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Query facts as they existed at a specific timestamp.

        Args:
            timestamp: ISO format timestamp.
            branch_name: Branch to query.
            category: Optional category filter.
            limit: Max results.

        Returns:
            Facts that were active at the given timestamp.
        """
        stmt = (
            select(Fact)
            .where(
                Fact.branch_name == branch_name,
                Fact.created_at <= timestamp,
            )
            .order_by(Fact.created_at.desc())
            .limit(limit)
        )
        if category:
            stmt = stmt.where(Fact.category == category)

        # Exclude facts that were superseded before the timestamp
        result = await self._session.execute(stmt)
        facts = result.scalars().all()

        return [
            {
                "id": f.id,
                "fact_text": f.fact_text,
                "category": f.category,
                "confidence": f.confidence,
                "status": f.status,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in facts
        ]
