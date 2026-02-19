"""REST API routes for sessions and context handoff."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.session_manager import SessionManager
from day1.db.engine import get_session

router = APIRouter()


@router.get("/sessions")
async def list_sessions(
    branch: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """List recent sessions."""
    mgr = SessionManager(session)
    sessions = await mgr.get_recent_sessions(branch_name=branch, limit=limit)
    return {
        "sessions": [
            {
                "session_id": s.session_id,
                "status": s.status,
                "branch_name": s.branch_name,
                "project_path": s.project_path,
                "task_id": s.task_id,
                "agent_id": s.agent_id,
                "summary": s.summary,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "ended_at": s.ended_at.isoformat() if s.ended_at else None,
            }
            for s in sessions
        ]
    }


@router.get("/sessions/{session_id}")
async def get_session_info(
    session_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get session metadata."""
    mgr = SessionManager(session)
    sess = await mgr.get_session(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": sess.session_id,
        "status": sess.status,
        "branch_name": sess.branch_name,
        "project_path": sess.project_path,
        "task_id": sess.task_id,
        "agent_id": sess.agent_id,
        "summary": sess.summary,
        "started_at": sess.started_at.isoformat() if sess.started_at else None,
        "ended_at": sess.ended_at.isoformat() if sess.ended_at else None,
    }


@router.get("/sessions/{session_id}/context")
async def get_session_context(
    session_id: str,
    message_limit: int = Query(50, ge=1, le=200),
    fact_limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """Get full context package from a session for agent handoff.

    Returns everything a new agent needs to continue where a
    previous session left off: session metadata, conversations
    with messages, facts produced, and observation summary.
    """
    mgr = SessionManager(session)
    context = await mgr.get_session_context(
        session_id=session_id,
        message_limit=message_limit,
        fact_limit=fact_limit,
    )
    if "error" in context:
        raise HTTPException(status_code=404, detail=context["error"])
    return context
