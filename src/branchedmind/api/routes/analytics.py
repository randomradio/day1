"""REST API routes for analytics."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from branchedmind.core.analytics_engine import AnalyticsEngine
from branchedmind.db.engine import get_session

router = APIRouter()


@router.get("/analytics/overview")
async def analytics_overview(
    branch: str | None = None,
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
):
    """Top-level dashboard metrics."""
    engine = AnalyticsEngine(session)
    return await engine.overview(branch_name=branch, days=days)


@router.get("/analytics/sessions/{session_id}")
async def session_analytics(
    session_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Per-session breakdown."""
    engine = AnalyticsEngine(session)
    return await engine.session_analytics(session_id)


@router.get("/analytics/agents/{agent_id}")
async def agent_analytics(
    agent_id: str,
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
):
    """Per-agent performance metrics."""
    engine = AnalyticsEngine(session)
    return await engine.agent_analytics(agent_id=agent_id, days=days)


@router.get("/analytics/trends")
async def analytics_trends(
    branch: str | None = None,
    days: int = Query(30, ge=1, le=365),
    granularity: str = Query("day", pattern="^(day|hour)$"),
    session: AsyncSession = Depends(get_session),
):
    """Time-series metrics."""
    engine = AnalyticsEngine(session)
    return await engine.trends(
        branch_name=branch,
        days=days,
        granularity=granularity,
    )


@router.get("/analytics/conversations/{conversation_id}")
async def conversation_analytics(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Detailed analytics for a single conversation."""
    engine = AnalyticsEngine(session)
    return await engine.conversation_analytics(conversation_id)
