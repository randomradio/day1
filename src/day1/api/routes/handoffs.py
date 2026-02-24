"""REST API routes for task handoff operations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.exceptions import HandoffError
from day1.core.handoff_engine import HandoffEngine
from day1.db.engine import get_session

router = APIRouter()


class CreateHandoffRequest(BaseModel):
    source_branch: str
    target_branch: str
    handoff_type: str = "task_continuation"
    source_task_id: str | None = None
    target_task_id: str | None = None
    source_agent_id: str | None = None
    target_agent_id: str | None = None
    include_unverified: bool = False
    fact_ids: list[str] | None = None
    conversation_ids: list[str] | None = None
    context_summary: str | None = None


@router.post("/handoffs")
async def create_handoff(
    body: CreateHandoffRequest,
    session: AsyncSession = Depends(get_session),
):
    """Create a structured handoff between branches/agents."""
    engine = HandoffEngine(session)
    try:
        return await engine.create_handoff(
            source_branch=body.source_branch,
            target_branch=body.target_branch,
            handoff_type=body.handoff_type,
            source_task_id=body.source_task_id,
            target_task_id=body.target_task_id,
            source_agent_id=body.source_agent_id,
            target_agent_id=body.target_agent_id,
            include_unverified=body.include_unverified,
            fact_ids=body.fact_ids,
            conversation_ids=body.conversation_ids,
            context_summary=body.context_summary,
        )
    except HandoffError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/handoffs/{handoff_id}")
async def get_handoff_packet(
    handoff_id: str,
    include_messages: bool = True,
    message_limit: int = 50,
    session: AsyncSession = Depends(get_session),
):
    """Retrieve the full handoff packet."""
    engine = HandoffEngine(session)
    try:
        return await engine.get_handoff_packet(
            handoff_id=handoff_id,
            include_messages=include_messages,
            message_limit=message_limit,
        )
    except HandoffError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/handoffs")
async def list_handoffs(
    source_branch: str | None = None,
    target_branch: str | None = None,
    handoff_type: str | None = None,
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
):
    """List handoff records with optional filters."""
    engine = HandoffEngine(session)
    return {
        "handoffs": await engine.list_handoffs(
            source_branch=source_branch,
            target_branch=target_branch,
            handoff_type=handoff_type,
            limit=limit,
        )
    }
