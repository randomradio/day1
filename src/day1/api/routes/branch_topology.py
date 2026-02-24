"""REST API routes for branch topology management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.branch_topology_engine import BranchTopologyEngine
from day1.core.exceptions import BranchNotFoundError
from day1.db.engine import get_session

router = APIRouter()


class EnrichRequest(BaseModel):
    purpose: str | None = None
    owner: str | None = None
    ttl_days: int | None = None
    tags: list[str] | None = None


class AutoArchiveRequest(BaseModel):
    inactive_days: int = 30
    archive_merged: bool = True
    dry_run: bool = False


class ValidateNameRequest(BaseModel):
    branch_name: str


@router.get("/branches/topology")
async def get_topology(
    root_branch: str = "main",
    max_depth: int = 10,
    include_archived: bool = False,
    session: AsyncSession = Depends(get_session),
):
    """Get hierarchical branch topology tree."""
    engine = BranchTopologyEngine(session)
    try:
        tree = await engine.get_topology(
            root_branch=root_branch,
            max_depth=max_depth,
            include_archived=include_archived,
        )
    except BranchNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return tree


@router.get("/branches/{branch_name}/stats")
async def get_branch_stats(
    branch_name: str,
    session: AsyncSession = Depends(get_session),
):
    """Get per-branch content stats."""
    engine = BranchTopologyEngine(session)
    try:
        stats = await engine.get_branch_stats(branch_name)
    except BranchNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return stats


@router.post("/branches/{branch_name}/enrich")
async def enrich_branch(
    branch_name: str,
    body: EnrichRequest,
    session: AsyncSession = Depends(get_session),
):
    """Enrich branch metadata with purpose, owner, TTL, tags."""
    engine = BranchTopologyEngine(session)
    try:
        branch = await engine.enrich_branch_metadata(
            branch_name=branch_name,
            purpose=body.purpose,
            owner=body.owner,
            ttl_days=body.ttl_days,
            tags=body.tags,
        )
    except BranchNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "branch_name": branch.branch_name,
        "metadata": branch.metadata_json,
    }


@router.post("/branches/auto-archive")
async def auto_archive(
    body: AutoArchiveRequest,
    session: AsyncSession = Depends(get_session),
):
    """Apply auto-archive policies (inactive branches, merged branches)."""
    engine = BranchTopologyEngine(session)
    result = await engine.apply_auto_archive(
        inactive_days=body.inactive_days,
        archive_merged=body.archive_merged,
        dry_run=body.dry_run,
    )
    return result


@router.get("/branches/expired")
async def get_expired_branches(
    session: AsyncSession = Depends(get_session),
):
    """List branches that have exceeded their TTL."""
    engine = BranchTopologyEngine(session)
    expired = await engine.check_ttl_expiry()
    return {"expired": expired, "count": len(expired)}


@router.post("/branches/validate-name")
async def validate_branch_name(
    body: ValidateNameRequest,
    session: AsyncSession = Depends(get_session),
):
    """Validate a branch name against naming conventions."""
    engine = BranchTopologyEngine(session)
    result = await engine.validate_branch_name(body.branch_name)
    return result
