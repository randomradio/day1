"""REST API routes for branch operations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from branchedmind.core.branch_manager import BranchManager
from branchedmind.core.exceptions import (
    BranchExistsError,
    BranchNotFoundError,
)
from branchedmind.core.merge_engine import MergeEngine
from branchedmind.db.engine import get_session

router = APIRouter()


class BranchCreate(BaseModel):
    branch_name: str
    parent_branch: str = "main"
    description: str | None = None


class MergeRequest(BaseModel):
    strategy: str = "auto"
    target_branch: str = "main"
    items: list[str] | None = None


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


@router.get("/branches/{branch_name}/diff")
async def branch_diff(
    branch_name: str,
    target_branch: str = "main",
    category: str | None = None,
    session: AsyncSession = Depends(get_session),
):
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


@router.post("/branches/{branch_name}/merge")
async def merge_branch(
    branch_name: str,
    body: MergeRequest,
    session: AsyncSession = Depends(get_session),
):
    engine = MergeEngine(session)
    try:
        result = await engine.merge(
            source_branch=branch_name,
            target_branch=body.target_branch,
            strategy=body.strategy,
            items=body.items,
        )
    except BranchNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result
