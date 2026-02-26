"""REST API routes for analytics."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.analytics_engine import AnalyticsEngine
from day1.db.engine import get_session

router = APIRouter()

_BRANCH_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_/-]+$")


def _resolve_branch_name(
    branch: str | None,
    branch_name: str | None,
) -> str | None:
    """Accept `branch` and legacy `branch_name` query params with validation."""
    value = branch_name if branch_name is not None else branch
    if branch and branch_name and branch != branch_name:
        raise HTTPException(
            status_code=400,
            detail="Use either 'branch' or 'branch_name' (same value), not both.",
        )
    if value is not None and not _BRANCH_NAME_PATTERN.fullmatch(value):
        raise HTTPException(
            status_code=400,
            detail="Invalid branch name format.",
        )
    return value


@router.get("/analytics/overview")
async def analytics_overview(
    branch: str | None = None,
    branch_name: str | None = Query(None, alias="branch_name"),
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
):
    """Top-level dashboard metrics."""
    engine = AnalyticsEngine(session)
    return await engine.overview(
        branch_name=_resolve_branch_name(branch, branch_name),
        days=days,
    )


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
    branch_name: str | None = Query(None, alias="branch_name"),
    days: int = Query(30, ge=1, le=365),
    granularity: str = Query("day", pattern="^(day|hour)$"),
    session: AsyncSession = Depends(get_session),
):
    """Time-series metrics."""
    engine = AnalyticsEngine(session)
    return await engine.trends(
        branch_name=_resolve_branch_name(branch, branch_name),
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
