"""REST API routes for messages."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.embedding import get_embedding_provider
from day1.core.exceptions import MessageNotFoundError
from day1.core.message_engine import MessageEngine
from day1.db.engine import get_session

router = APIRouter()


# --- Request / Response models ---


class MessageCreate(BaseModel):
    conversation_id: str
    role: str
    content: str | None = None
    thinking: str | None = None
    tool_calls: list[dict] | None = None
    token_count: int = 0
    model: str | None = None
    parent_message_id: str | None = None
    session_id: str | None = None
    agent_id: str | None = None
    branch: str = "main"
    metadata: dict | None = None


class MessageBatchCreate(BaseModel):
    """Bulk ingest endpoint — post multiple messages at once."""

    messages: list[MessageCreate]


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    session_id: str | None
    agent_id: str | None
    role: str
    content: str | None
    thinking: str | None
    tool_calls: list[dict] | None
    token_count: int
    model: str | None
    sequence_num: int
    branch_name: str
    created_at: str | None

    model_config = {"from_attributes": True}


def _msg_response(m) -> MessageResponse:
    return MessageResponse(
        id=m.id,
        conversation_id=m.conversation_id,
        session_id=m.session_id,
        agent_id=m.agent_id,
        role=m.role,
        content=m.content,
        thinking=m.thinking,
        tool_calls=m.tool_calls_json,
        token_count=m.token_count,
        model=m.model,
        sequence_num=m.sequence_num,
        branch_name=m.branch_name,
        created_at=m.created_at.isoformat() if m.created_at else None,
    )


# --- Endpoints ---


@router.post("/conversations/{conversation_id}/messages", response_model=MessageResponse)
async def add_message(
    conversation_id: str,
    body: MessageCreate,
    session: AsyncSession = Depends(get_session),
):
    """Add a single message to a conversation."""
    engine = MessageEngine(session, get_embedding_provider())
    msg = await engine.write_message(
        conversation_id=conversation_id,
        role=body.role,
        content=body.content,
        thinking=body.thinking,
        tool_calls=body.tool_calls,
        token_count=body.token_count,
        model=body.model,
        parent_message_id=body.parent_message_id,
        session_id=body.session_id,
        agent_id=body.agent_id,
        branch_name=body.branch,
        metadata=body.metadata,
    )
    return _msg_response(msg)


@router.post("/conversations/{conversation_id}/messages/batch")
async def add_messages_batch(
    conversation_id: str,
    body: MessageBatchCreate,
    session: AsyncSession = Depends(get_session),
):
    """Bulk add messages to a conversation."""
    engine = MessageEngine(session, get_embedding_provider())
    results = []
    for m in body.messages:
        msg = await engine.write_message(
            conversation_id=conversation_id,
            role=m.role,
            content=m.content,
            thinking=m.thinking,
            tool_calls=m.tool_calls,
            token_count=m.token_count,
            model=m.model,
            parent_message_id=m.parent_message_id,
            session_id=m.session_id,
            agent_id=m.agent_id,
            branch_name=m.branch,
            metadata=m.metadata,
        )
        results.append(_msg_response(msg).model_dump())
    return {"messages": results, "count": len(results)}


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: str,
    role: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    """List messages in a conversation (ordered by sequence)."""
    engine = MessageEngine(session, get_embedding_provider())
    msgs = await engine.list_messages(
        conversation_id=conversation_id,
        limit=limit,
        offset=offset,
        role=role,
    )
    return {
        "messages": [_msg_response(m).model_dump() for m in msgs],
        "count": len(msgs),
    }


@router.get("/messages/search")
async def search_messages(
    query: str,
    branch: str = "main",
    conversation_id: str | None = None,
    session_id: str | None = None,
    role: str | None = None,
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """Semantic + keyword search across messages."""
    engine = MessageEngine(session, get_embedding_provider())
    results = await engine.search_messages(
        query=query,
        branch_name=branch,
        conversation_id=conversation_id,
        session_id=session_id,
        role=role,
        limit=limit,
    )
    return {"results": results, "count": len(results)}


@router.get("/messages/{message_id}", response_model=MessageResponse)
async def get_message(
    message_id: str,
    session: AsyncSession = Depends(get_session),
):
    engine = MessageEngine(session, get_embedding_provider())
    try:
        msg = await engine.get_message(message_id)
    except MessageNotFoundError:
        raise HTTPException(status_code=404, detail="Message not found")
    return _msg_response(msg)
