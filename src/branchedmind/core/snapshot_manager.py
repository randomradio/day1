"""Snapshot manager: point-in-time snapshots and time-travel queries (MatrixOne)."""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from branchedmind.config import settings
from branchedmind.core.branch_manager import _branch_table
from branchedmind.core.exceptions import SnapshotError
from branchedmind.db.models import Fact, Observation, Relation, Snapshot

# Extract database name from connection URL for SNAPSHOT commands
_db_name = settings.database_url.rsplit("/", 1)[-1].split("?")[0]


class SnapshotManager:
    """Manages point-in-time snapshots of memory state."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @asynccontextmanager
    async def _get_autocommit_conn(self) -> AsyncConnection:
        """Get an autocommit connection from the session's engine.

        Using the session's engine avoids event loop conflicts in tests
        where the global engine might be tied to a different event loop.
        """
        async with self._session.bind.connect() as raw_conn:
            conn = await raw_conn.execution_options(isolation_level="AUTOCOMMIT")
            yield conn

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
            select(Fact).where(Fact.branch_name == branch_name, Fact.status == "active")
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
        await self._session.refresh(snapshot)
        return snapshot

    async def create_snapshot_native(
        self,
        branch_name: str = "main",
        label: str | None = None,
    ) -> dict:
        """Create a MO native snapshot using CREATE SNAPSHOT FOR DATABASE.

        Args:
            branch_name: Branch name (used for labeling).
            label: Optional label.

        Returns:
            Dict with snapshot name and metadata.
        """
        safe_label = re.sub(r"[^a-zA-Z0-9_]", "_", label or branch_name)
        snap_name = f"sp_{safe_label}_{int(datetime.utcnow().timestamp())}"

        # CREATE SNAPSHOT requires autocommit (not inside a transaction)
        async with self._get_autocommit_conn() as ac:
            await ac.execute(
                text(f"CREATE SNAPSHOT {snap_name} FOR DATABASE `{_db_name}`")
            )

        # Also save to snapshots table for tracking
        snapshot = Snapshot(
            label=label or snap_name,
            branch_name=branch_name,
            snapshot_data={"mo_snapshot_name": snap_name, "type": "native"},
        )
        self._session.add(snapshot)
        await self._session.commit()

        return {
            "snapshot_name": snap_name,
            "id": snapshot.id,
            "branch_name": branch_name,
        }

    async def list_snapshots(self, branch_name: str | None = None) -> list[Snapshot]:
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
        """Query facts as they existed at a specific timestamp using MO time travel.

        Uses MatrixOne's {AS OF TIMESTAMP 'ts'} syntax for true point-in-time queries.

        Args:
            timestamp: ISO format timestamp.
            branch_name: Branch to query.
            category: Optional category filter.
            limit: Max results.

        Returns:
            Facts that existed at the given timestamp.
        """
        # Validate timestamp format to prevent injection
        if not re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}", timestamp):
            raise SnapshotError(f"Invalid timestamp format: {timestamp}")
        ts = timestamp[:19].replace("T", " ")

        table = _branch_table("facts", branch_name)

        where_parts: list[str] = []
        params: dict = {"limit": limit}
        if category:
            where_parts.append("category = :category")
            params["category"] = category

        where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        # MO native time travel: SELECT ... FROM table {AS OF TIMESTAMP 'ts'}
        result = await self._session.execute(
            text(
                f"SELECT id, fact_text, category, confidence, status, created_at "
                f"FROM {table} {{AS OF TIMESTAMP '{ts}'}} {where_sql} "
                f"ORDER BY created_at DESC LIMIT :limit"
            ),
            params,
        )
        rows = result.fetchall()
        columns = ["id", "fact_text", "category", "confidence", "status", "created_at"]

        return [
            {
                col: (val.isoformat() if isinstance(val, datetime) else val)
                for col, val in zip(columns, row)
            }
            for row in rows
        ]
