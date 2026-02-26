"""REST API routes for branch operations (MatrixOne native)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.branch_manager import BranchManager
from day1.core.conversation_cherry_pick import ConversationCherryPick
from day1.core.exceptions import (
    BranchExistsError,
    BranchNotFoundError,
)
from day1.core.merge_engine import MergeEngine
from day1.db.engine import get_session

router = APIRouter()


class BranchCreate(BaseModel):
    branch_name: str
    parent_branch: str = "main"
    description: str | None = None


class MergeRequest(BaseModel):
    strategy: str = "auto"
    target_branch: str = "main"
    items: list[str] | None = None
    conflict: str = "skip"


class CuratedBranchRequest(BaseModel):
    branch_name: str
    parent_branch: str = "main"
    conversation_ids: list[str] | None = None
    fact_ids: list[str] | None = None
    description: str | None = None


@router.post("/branches")
async def create_branch(
    body: BranchCreate,
    session: AsyncSession = Depends(get_session),
):
    mgr = BranchManager(session)
    try:
        branch = await mgr.create_branch(
            branch_name=body.branch_name,
            parent_branch=body.parent_branch,
            description=body.description,
        )
    except BranchExistsError:
        raise HTTPException(status_code=409, detail="Branch already exists")
    except BranchNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "branch_name": branch.branch_name,
        "parent_branch": branch.parent_branch,
        "created_at": branch.forked_at.isoformat() if branch.forked_at else None,
    }


@router.get("/branches")
async def list_branches(
    status: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    mgr = BranchManager(session)
    branches = await mgr.list_branches(status=status)
    return {
        "branches": [
            {
                "branch_name": b.branch_name,
                "parent_branch": b.parent_branch,
                "status": b.status,
                "description": b.description,
                "forked_at": b.forked_at.isoformat() if b.forked_at else None,
            }
            for b in branches
        ]
    }


@router.get("/branches/{branch_name:path}/diff")
async def branch_diff(
    branch_name: str,
    target_branch: str = "main",
    category: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Application-layer diff (fact text similarity)."""
    engine = MergeEngine(session)
    try:
        diff = await engine.diff(
            source_branch=branch_name,
            target_branch=target_branch,
            category=category,
        )
    except BranchNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return diff.to_dict()


@router.get("/branches/{branch_name:path}/diff/native")
async def branch_diff_native(
    branch_name: str,
    target_branch: str = "main",
    session: AsyncSession = Depends(get_session),
):
    """MO DATA BRANCH DIFF — row-level INSERT/UPDATE/DELETE diff."""
    mgr = BranchManager(session)
    try:
        diffs = await mgr.diff_branch(branch_name, target_branch)
    except BranchNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"diffs": diffs, "count": len(diffs)}


@router.get("/branches/{branch_name:path}/diff/native/count")
async def branch_diff_native_count(
    branch_name: str,
    target_branch: str = "main",
    session: AsyncSession = Depends(get_session),
):
    """MO DATA BRANCH DIFF OUTPUT COUNT — per-table change counts."""
    mgr = BranchManager(session)
    try:
        counts = await mgr.diff_branch_count(branch_name, target_branch)
    except BranchNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"counts": counts}


@router.post("/branches/{branch_name:path}/merge")
async def merge_branch(
    branch_name: str,
    body: MergeRequest,
    session: AsyncSession = Depends(get_session),
):
    """Merge a branch using the specified strategy.

    Strategies:
        auto — application-layer merge, skip conflicts
        cherry_pick — merge specific items by ID
        squash — merge all items
        native — MO DATA BRANCH MERGE with conflict=skip|accept
    """
    engine = MergeEngine(session)
    try:
        result = await engine.merge(
            source_branch=branch_name,
            target_branch=body.target_branch,
            strategy=body.strategy,
            items=body.items,
            conflict=body.conflict,
        )
    except BranchNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result


@router.delete("/branches/{branch_name:path}")
async def archive_branch(
    branch_name: str,
    session: AsyncSession = Depends(get_session),
):
    """Archive a branch (drop branch tables, mark as archived)."""
    mgr = BranchManager(session)
    try:
        await mgr.archive_branch(branch_name)
    except BranchNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except BranchExistsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "archived", "branch_name": branch_name}


@router.post("/branches/curated", status_code=201)
async def create_curated_branch(
    body: CuratedBranchRequest,
    session: AsyncSession = Depends(get_session),
):
    """Create a curated branch from selected conversations and facts."""
    cherry = ConversationCherryPick(session)
    try:
        result = await cherry.cherry_pick_to_curated_branch(
            branch_name=body.branch_name,
            parent_branch=body.parent_branch,
            conversation_ids=body.conversation_ids,
            fact_ids=body.fact_ids,
            description=body.description,
        )
    except BranchExistsError:
        raise HTTPException(status_code=409, detail="Branch already exists")
    except BranchNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result
