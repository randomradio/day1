"""REST API routes for template branch management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.exceptions import (
    BranchNotFoundError,
    TemplateError,
    TemplateNotFoundError,
)
from day1.core.template_engine import TemplateEngine
from day1.db.engine import get_session

router = APIRouter()


class TemplateCreateRequest(BaseModel):
    name: str
    source_branch: str
    description: str | None = None
    applicable_task_types: list[str] | None = None
    tags: list[str] | None = None
    created_by: str | None = None


class TemplateInstantiateRequest(BaseModel):
    target_branch_name: str
    task_id: str | None = None


class TemplateUpdateRequest(BaseModel):
    source_branch: str
    reason: str | None = None


def _template_to_dict(t) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "version": t.version,
        "branch_name": t.branch_name,
        "source_branch": t.source_branch,
        "applicable_task_types": t.applicable_task_types,
        "tags": t.tags,
        "fact_count": t.fact_count,
        "conversation_count": t.conversation_count,
        "status": t.status,
        "created_by": t.created_by,
        "metadata": t.metadata_json,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


@router.post("/templates", status_code=201)
async def create_template(
    body: TemplateCreateRequest,
    session: AsyncSession = Depends(get_session),
):
    """Create a template from an existing branch."""
    engine = TemplateEngine(session)
    try:
        template = await engine.create_template(
            name=body.name,
            source_branch=body.source_branch,
            description=body.description,
            applicable_task_types=body.applicable_task_types,
            tags=body.tags,
            created_by=body.created_by,
        )
    except BranchNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TemplateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _template_to_dict(template)


@router.get("/templates")
async def list_templates(
    task_type: str | None = None,
    status: str = "active",
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
):
    """List templates with optional filters."""
    engine = TemplateEngine(session)
    templates = await engine.list_templates(
        task_type=task_type,
        status=status,
        limit=limit,
    )
    return {"templates": [_template_to_dict(t) for t in templates]}


@router.get("/templates/find")
async def find_template(
    task_type: str,
    task_description: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Find the best template for a given task type."""
    engine = TemplateEngine(session)
    template = await engine.find_applicable_template(
        task_type=task_type,
        task_description=task_description,
    )
    if template is None:
        return {"template": None}
    return {"template": _template_to_dict(template)}


@router.get("/templates/{name}")
async def get_template(
    name: str,
    session: AsyncSession = Depends(get_session),
):
    """Get template details by name."""
    engine = TemplateEngine(session)
    try:
        template = await engine.get_template(name)
    except TemplateNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _template_to_dict(template)


@router.post("/templates/{name}/instantiate")
async def instantiate_template(
    name: str,
    body: TemplateInstantiateRequest,
    session: AsyncSession = Depends(get_session),
):
    """Fork a template into a working branch."""
    engine = TemplateEngine(session)
    try:
        result = await engine.instantiate_template(
            template_name=name,
            target_branch_name=body.target_branch_name,
            task_id=body.task_id,
        )
    except TemplateNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TemplateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.post("/templates/{name}/update")
async def update_template(
    name: str,
    body: TemplateUpdateRequest,
    session: AsyncSession = Depends(get_session),
):
    """Evolve a template by creating a new version from a source branch."""
    engine = TemplateEngine(session)
    try:
        template = await engine.update_template(
            template_name=name,
            source_branch=body.source_branch,
            reason=body.reason,
        )
    except TemplateNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (BranchNotFoundError, TemplateError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _template_to_dict(template)


@router.post("/templates/{name}/deprecate")
async def deprecate_template(
    name: str,
    session: AsyncSession = Depends(get_session),
):
    """Deprecate a template."""
    engine = TemplateEngine(session)
    try:
        template = await engine.deprecate_template(name)
    except TemplateNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _template_to_dict(template)
