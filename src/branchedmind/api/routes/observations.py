"""REST API routes for observations."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from branchedmind.core.embedding import get_embedding_provider
from branchedmind.core.observation_engine import ObservationEngine
from branchedmind.db.engine import get_session

router = APIRouter()


class ObservationCreate(BaseModel):
    session_id: str
    observation_type: str
    summary: str
    tool_name: str | None = None
    raw_input: str | None = None
    raw_output: str | None = None
    branch: str = "main"
    metadata: dict | None = None


@router.post("/observations")
async def create_observation(
    body: ObservationCreate,
    session: AsyncSession = Depends(get_session),
):
    engine = ObservationEngine(session, get_embedding_provider())
    obs = await engine.write_observation(
        session_id=body.session_id,
        observation_type=body.observation_type,
        summary=body.summary,
        tool_name=body.tool_name,
        raw_input=body.raw_input,
        raw_output=body.raw_output,
        branch_name=body.branch,
        metadata=body.metadata,
    )
    return {
        "id": obs.id,
        "created_at": obs.created_at.isoformat() if obs.created_at else None,
    }


@router.get("/observations")
async def list_observations(
    branch: str = "main",
    session_id: str | None = None,
    observation_type: str | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
):
    engine = ObservationEngine(session, get_embedding_provider())
    observations = await engine.list_observations(
        branch_name=branch,
        session_id=session_id,
        observation_type=observation_type,
        limit=limit,
    )
    return {
        "observations": [
            {
                "id": o.id,
                "session_id": o.session_id,
                "observation_type": o.observation_type,
                "tool_name": o.tool_name,
                "summary": o.summary,
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in observations
        ]
    }


@router.get("/observations/timeline")
async def observation_timeline(
    branch: str = "main",
    session_id: str | None = None,
    after: str | None = None,
    before: str | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
):
    engine = ObservationEngine(session, get_embedding_provider())
    observations = await engine.timeline(
        branch_name=branch,
        session_id=session_id,
        after=after,
        before=before,
        limit=limit,
    )
    return {
        "timeline": [
            {
                "id": o.id,
                "type": "observation",
                "observation_type": o.observation_type,
                "tool_name": o.tool_name,
                "summary": o.summary,
                "timestamp": o.created_at.isoformat() if o.created_at else None,
            }
            for o in observations
        ]
    }
