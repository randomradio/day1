"""REST API routes for conversations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.conversation_cherry_pick import ConversationCherryPick
from day1.core.conversation_engine import ConversationEngine
from day1.core.exceptions import (
    ConversationNotFoundError,
    MessageNotFoundError,
)
from day1.core.semantic_diff import SemanticDiffEngine
from day1.db.engine import get_session

router = APIRouter()


# --- Request / Response models ---


class ConversationCreate(BaseModel):
    session_id: str | None = None
    agent_id: str | None = None
    task_id: str | None = None
    branch: str = "main"
    title: str | None = None
    model: str | None = None
    metadata: dict | None = None


class ConversationResponse(BaseModel):
    id: str
    session_id: str | None
    agent_id: str | None
    task_id: str | None
    branch_name: str
    title: str | None
    parent_conversation_id: str | None
    fork_point_message_id: str | None
    status: str
    message_count: int
    total_tokens: int
    model: str | None
    created_at: str | None
    updated_at: str | None

    model_config = {"from_attributes": True}


class ForkRequest(BaseModel):
    message_id: str
    branch: str | None = None
    title: str | None = None


class CherryPickRequest(BaseModel):
    target_branch: str
    from_sequence: int | None = None
    to_sequence: int | None = None
    title: str | None = None


def _conv_response(c) -> ConversationResponse:
    return ConversationResponse(
        id=c.id,
        session_id=c.session_id,
        agent_id=c.agent_id,
        task_id=c.task_id,
        branch_name=c.branch_name,
        title=c.title,
        parent_conversation_id=c.parent_conversation_id,
        fork_point_message_id=c.fork_point_message_id,
        status=c.status,
        message_count=c.message_count,
        total_tokens=c.total_tokens,
        model=c.model,
        created_at=c.created_at.isoformat() if c.created_at else None,
        updated_at=c.updated_at.isoformat() if c.updated_at else None,
    )


# --- Endpoints ---


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    body: ConversationCreate,
    session: AsyncSession = Depends(get_session),
):
    engine = ConversationEngine(session)
    conv = await engine.create_conversation(
        session_id=body.session_id,
        agent_id=body.agent_id,
        task_id=body.task_id,
        branch_name=body.branch,
        title=body.title,
        model=body.model,
        metadata=body.metadata,
    )
    return _conv_response(conv)


@router.get("/conversations")
async def list_conversations(
    session_id: str | None = None,
    agent_id: str | None = None,
    task_id: str | None = None,
    branch: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    engine = ConversationEngine(session)
    convs = await engine.list_conversations(
        session_id=session_id,
        agent_id=agent_id,
        task_id=task_id,
        branch_name=branch,
        status=status,
        limit=limit,
        offset=offset,
    )
    return {
        "conversations": [_conv_response(c).model_dump() for c in convs],
        "count": len(convs),
    }


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
):
    engine = ConversationEngine(session)
    try:
        conv = await engine.get_conversation(conversation_id)
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return _conv_response(conv)


@router.post(
    "/conversations/{conversation_id}/fork",
    response_model=ConversationResponse,
)
async def fork_conversation(
    conversation_id: str,
    body: ForkRequest,
    session: AsyncSession = Depends(get_session),
):
    engine = ConversationEngine(session)
    try:
        forked = await engine.fork_conversation(
            conversation_id=conversation_id,
            fork_at_message_id=body.message_id,
            branch_name=body.branch,
            title=body.title,
        )
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail="Conversation not found")
    except MessageNotFoundError:
        raise HTTPException(status_code=404, detail="Fork-point message not found")
    return _conv_response(forked)


@router.get("/conversations/{conv_a}/diff/{conv_b}")
async def diff_conversations(
    conv_a: str,
    conv_b: str,
    session: AsyncSession = Depends(get_session),
):
    engine = ConversationEngine(session)
    try:
        return await engine.diff_conversations(conv_a, conv_b)
    except ConversationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/conversations/{conv_a}/semantic-diff/{conv_b}")
async def semantic_diff_conversations(
    conv_a: str,
    conv_b: str,
    session: AsyncSession = Depends(get_session),
):
    """Three-layer semantic diff: actions, reasoning, outcomes."""
    engine = SemanticDiffEngine(session)
    try:
        return await engine.semantic_diff(conv_a, conv_b)
    except ConversationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/conversations/{conversation_id}/complete")
async def complete_conversation(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
):
    engine = ConversationEngine(session)
    try:
        conv = await engine.complete_conversation(conversation_id)
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return _conv_response(conv)


@router.post("/conversations/{conversation_id}/cherry-pick")
async def cherry_pick_conversation(
    conversation_id: str,
    body: CherryPickRequest,
    session: AsyncSession = Depends(get_session),
):
    """Cherry-pick a conversation or message range to another branch."""
    cherry = ConversationCherryPick(session)
    try:
        if body.from_sequence is not None and body.to_sequence is not None:
            result = await cherry.cherry_pick_message_range(
                conversation_id=conversation_id,
                from_sequence=body.from_sequence,
                to_sequence=body.to_sequence,
                target_branch=body.target_branch,
                title=body.title,
            )
        else:
            result = await cherry.cherry_pick_conversation(
                conversation_id=conversation_id,
                target_branch=body.target_branch,
            )
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return result
