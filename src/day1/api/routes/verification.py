"""REST API routes for fact verification."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.exceptions import FactNotFoundError, VerificationError
from day1.core.verification_engine import VerificationEngine
from day1.db.engine import get_session

router = APIRouter()


class VerifyFactRequest(BaseModel):
    dimensions: list[str] | None = None
    context: str | None = None


class BatchVerifyRequest(BaseModel):
    branch_name: str
    dimensions: list[str] | None = None
    limit: int = 50
    only_unverified: bool = True


class MergeGateRequest(BaseModel):
    source_branch: str
    require_verified: bool = True


@router.post("/facts/{fact_id}/verify")
async def verify_fact(
    fact_id: str,
    body: VerifyFactRequest,
    session: AsyncSession = Depends(get_session),
):
    """Verify a single fact using LLM-as-judge."""
    engine = VerificationEngine(session)
    try:
        result = await engine.verify_fact(
            fact_id=fact_id,
            dimensions=body.dimensions,
            context=body.context,
        )
    except FactNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except VerificationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.get("/facts/{fact_id}/verification")
async def get_verification_status(
    fact_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get the verification status of a fact."""
    engine = VerificationEngine(session)
    try:
        return await engine.get_verification_status(fact_id)
    except FactNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/verification/batch")
async def batch_verify(
    body: BatchVerifyRequest,
    session: AsyncSession = Depends(get_session),
):
    """Batch-verify all unverified facts on a branch."""
    engine = VerificationEngine(session)
    return await engine.batch_verify(
        branch_name=body.branch_name,
        dimensions=body.dimensions,
        limit=body.limit,
        only_unverified=body.only_unverified,
    )


@router.get("/verification/verified")
async def get_verified_facts(
    branch_name: str = "main",
    category: str | None = None,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
):
    """Get all verified facts on a branch."""
    engine = VerificationEngine(session)
    return {
        "facts": await engine.get_verified_facts(
            branch_name=branch_name,
            category=category,
            limit=limit,
        )
    }


@router.post("/verification/merge-gate")
async def check_merge_gate(
    body: MergeGateRequest,
    session: AsyncSession = Depends(get_session),
):
    """Check if a branch passes the verification merge gate."""
    engine = VerificationEngine(session)
    return await engine.check_merge_gate(
        source_branch=body.source_branch,
        require_verified=body.require_verified,
    )


@router.get("/verification/summary/{branch_name:path}")
async def branch_verification_summary(
    branch_name: str,
    session: AsyncSession = Depends(get_session),
):
    """Get verification summary for all facts on a branch."""
    engine = VerificationEngine(session)
    return await engine.get_branch_verification_summary(branch_name)
