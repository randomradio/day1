"""REST API routes for snapshots and time-travel."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from branchedmind.core.exceptions import SnapshotError
from branchedmind.core.snapshot_manager import SnapshotManager
from branchedmind.db.engine import get_session

router = APIRouter()


class SnapshotCreate(BaseModel):
    label: str | None = None
    branch: str = "main"


class TimeTravelQuery(BaseModel):
    timestamp: str
    branch: str = "main"
    category: str | None = None
    limit: int = 20


@router.post("/snapshots")
async def create_snapshot(
    body: SnapshotCreate,
    session: AsyncSession = Depends(get_session),
):
    mgr = SnapshotManager(session)
    snapshot = await mgr.create_snapshot(
        branch_name=body.branch,
        label=body.label,
    )
    return {
        "snapshot_id": snapshot.id,
        "label": snapshot.label,
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
    }


@router.get("/snapshots")
async def list_snapshots(
    branch: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    mgr = SnapshotManager(session)
    snapshots = await mgr.list_snapshots(branch_name=branch)
    return {
        "snapshots": [
            {
                "id": s.id,
                "label": s.label,
                "branch_name": s.branch_name,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in snapshots
        ]
    }


@router.get("/snapshots/{snapshot_id}")
async def get_snapshot(
    snapshot_id: str,
    session: AsyncSession = Depends(get_session),
):
    mgr = SnapshotManager(session)
    try:
        snapshot = await mgr.get_snapshot(snapshot_id)
    except SnapshotError:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return {
        "id": snapshot.id,
        "label": snapshot.label,
        "branch_name": snapshot.branch_name,
        "snapshot_data": snapshot.snapshot_data,
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
    }


@router.get("/time-travel")
async def time_travel(
    timestamp: str,
    branch: str = "main",
    category: str | None = None,
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
):
    mgr = SnapshotManager(session)
    results = await mgr.time_travel_query(
        timestamp=timestamp,
        branch_name=branch,
        category=category,
        limit=limit,
    )
    return {"timestamp": timestamp, "results": results}


@router.post("/time-travel")
async def time_travel_post(
    body: TimeTravelQuery,
    session: AsyncSession = Depends(get_session),
):
    mgr = SnapshotManager(session)
    results = await mgr.time_travel_query(
        timestamp=body.timestamp,
        branch_name=body.branch,
        category=body.category,
        limit=body.limit,
    )
    return {"timestamp": body.timestamp, "results": results}
