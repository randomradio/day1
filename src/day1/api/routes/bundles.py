"""REST API routes for knowledge bundle operations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.exceptions import KnowledgeBundleError
from day1.core.knowledge_bundle_engine import KnowledgeBundleEngine
from day1.db.engine import get_session

router = APIRouter()


class CreateBundleRequest(BaseModel):
    name: str
    source_branch: str
    description: str | None = None
    source_task_id: str | None = None
    tags: list[str] | None = None
    created_by: str | None = None
    only_verified: bool = True
    fact_ids: list[str] | None = None
    conversation_ids: list[str] | None = None


class ImportBundleRequest(BaseModel):
    target_branch: str
    import_facts: bool = True
    import_conversations: bool = True
    import_relations: bool = True


@router.post("/bundles")
async def create_bundle(
    body: CreateBundleRequest,
    session: AsyncSession = Depends(get_session),
):
    """Create a knowledge bundle from a branch."""
    engine = KnowledgeBundleEngine(session)
    try:
        return await engine.create_bundle(
            name=body.name,
            source_branch=body.source_branch,
            description=body.description,
            source_task_id=body.source_task_id,
            tags=body.tags,
            created_by=body.created_by,
            only_verified=body.only_verified,
            fact_ids=body.fact_ids,
            conversation_ids=body.conversation_ids,
        )
    except KnowledgeBundleError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/bundles")
async def list_bundles(
    status: str = "active",
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
):
    """List knowledge bundles."""
    engine = KnowledgeBundleEngine(session)
    return {
        "bundles": await engine.list_bundles(status=status, limit=limit)
    }


@router.get("/bundles/{bundle_id}")
async def get_bundle(
    bundle_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get bundle details (without full data)."""
    engine = KnowledgeBundleEngine(session)
    try:
        return await engine.get_bundle(bundle_id)
    except KnowledgeBundleError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/bundles/{bundle_id}/export")
async def export_bundle(
    bundle_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Export the full bundle data for transfer."""
    engine = KnowledgeBundleEngine(session)
    try:
        return await engine.export_bundle(bundle_id)
    except KnowledgeBundleError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/bundles/{bundle_id}/import")
async def import_bundle(
    bundle_id: str,
    body: ImportBundleRequest,
    session: AsyncSession = Depends(get_session),
):
    """Import a knowledge bundle into a target branch."""
    engine = KnowledgeBundleEngine(session)
    try:
        return await engine.import_bundle(
            bundle_id=bundle_id,
            target_branch=body.target_branch,
            import_facts=body.import_facts,
            import_conversations=body.import_conversations,
            import_relations=body.import_relations,
        )
    except KnowledgeBundleError as e:
        raise HTTPException(status_code=404, detail=str(e))
