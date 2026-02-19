"""REST API routes for conversation replay."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from branchedmind.core.exceptions import (
    ConversationNotFoundError,
    MessageNotFoundError,
    ReplayError,
)
from branchedmind.core.replay_engine import ReplayConfig, ReplayEngine
from branchedmind.core.semantic_diff import SemanticDiffEngine
from branchedmind.db.engine import get_session

router = APIRouter()


# --- Request / Response models ---


class ReplayRequest(BaseModel):
    from_message_id: str
    system_prompt: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    tool_filter: list[str] | None = None
    extra_context: str | None = None
    branch: str | None = None
    title: str | None = None


class ReplayResponse(BaseModel):
    replay_id: str
    original_conversation_id: str
    forked_conversation_id: str
    fork_point_message_id: str
    config: dict
    status: str
    messages_copied: int
    created_at: str | None


# --- Endpoints ---


@router.post(
    "/conversations/{conversation_id}/replay",
    response_model=ReplayResponse,
)
async def start_replay(
    conversation_id: str,
    body: ReplayRequest,
    session: AsyncSession = Depends(get_session),
):
    """Fork a conversation at a message and prepare for replay."""
    engine = ReplayEngine(session)
    config = ReplayConfig(
        system_prompt=body.system_prompt,
        model=body.model,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        tool_filter=body.tool_filter,
        extra_context=body.extra_context,
        branch_name=body.branch,
        title=body.title,
    )
    try:
        result = await engine.start_replay(
            conversation_id=conversation_id,
            from_message_id=body.from_message_id,
            config=config,
        )
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail="Conversation not found")
    except MessageNotFoundError:
        raise HTTPException(status_code=404, detail="Message not found")
    except ReplayError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ReplayResponse(
        replay_id=result.replay_id,
        original_conversation_id=result.original_conversation_id,
        forked_conversation_id=result.forked_conversation_id,
        fork_point_message_id=result.fork_point_message_id,
        config=result.config,
        status=result.status,
        messages_copied=result.messages_copied,
        created_at=result.created_at,
    )


@router.get("/replays/{replay_id}/context")
async def get_replay_context(
    replay_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get the message history for a replay, ready for LLM submission."""
    engine = ReplayEngine(session)
    try:
        return await engine.get_replay_context(replay_id)
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail="Replay not found")


@router.get("/replays/{replay_id}/diff")
async def diff_replay(
    replay_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Diff a replay against its original conversation."""
    engine = ReplayEngine(session)
    try:
        return await engine.diff_replay(replay_id)
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail="Replay not found")
    except ReplayError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/replays/{replay_id}/semantic-diff")
async def semantic_diff_replay(
    replay_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Three-layer semantic diff of replay vs original.

    Automatically resolves the original conversation from replay metadata.
    Returns action diff, reasoning diff, and outcome diff.
    """
    replay_engine = ReplayEngine(session)
    try:
        # Get the original conversation ID from replay metadata
        context = await replay_engine.get_replay_context(replay_id)
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail="Replay not found")

    original_id = context.get("original_conversation_id")
    if not original_id:
        raise HTTPException(
            status_code=400,
            detail="Cannot determine original conversation for this replay",
        )

    diff_engine = SemanticDiffEngine(session)
    try:
        return await diff_engine.semantic_diff(original_id, replay_id)
    except ConversationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/replays/{replay_id}/complete")
async def complete_replay(
    replay_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Mark a replay as completed."""
    engine = ReplayEngine(session)
    try:
        return await engine.complete_replay(replay_id)
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail="Replay not found")


@router.get("/replays")
async def list_replays(
    conversation_id: str | None = None,
    session_id: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """List replay conversations."""
    engine = ReplayEngine(session)
    replays = await engine.list_replays(
        conversation_id=conversation_id,
        session_id=session_id,
        limit=limit,
    )
    return {"replays": replays, "count": len(replays)}
