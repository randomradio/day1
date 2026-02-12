"""REST API routes for facts."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from branchedmind.core.embedding import get_embedding_provider
from branchedmind.core.exceptions import FactNotFoundError
from branchedmind.core.fact_engine import FactEngine
from branchedmind.db.engine import get_session

router = APIRouter()


class FactCreate(BaseModel):
    fact_text: str
    category: str | None = None
    confidence: float = 1.0
    source_type: str | None = None
    session_id: str | None = None
    branch: str = "main"
    metadata: dict | None = None


class FactUpdate(BaseModel):
    fact_text: str | None = None
    confidence: float | None = None
    status: str | None = None
    metadata: dict | None = None


class FactResponse(BaseModel):
    id: str
    fact_text: str
    category: str | None
    confidence: float
    status: str
    branch_name: str
    created_at: str | None

    model_config = {"from_attributes": True}


@router.post("/facts", response_model=FactResponse)
async def create_fact(
    body: FactCreate,
    session: AsyncSession = Depends(get_session),
):
    engine = FactEngine(session, get_embedding_provider())
    fact = await engine.write_fact(
        fact_text=body.fact_text,
        category=body.category,
        confidence=body.confidence,
        source_type=body.source_type,
        session_id=body.session_id,
        branch_name=body.branch,
        metadata=body.metadata,
    )
    return FactResponse(
        id=fact.id,
        fact_text=fact.fact_text,
        category=fact.category,
        confidence=fact.confidence,
        status=fact.status,
        branch_name=fact.branch_name,
        created_at=fact.created_at.isoformat() if fact.created_at else None,
    )


@router.get("/facts/{fact_id}", response_model=FactResponse)
async def get_fact(
    fact_id: str,
    session: AsyncSession = Depends(get_session),
):
    engine = FactEngine(session, get_embedding_provider())
    try:
        fact = await engine.get_fact(fact_id)
    except FactNotFoundError:
        raise HTTPException(status_code=404, detail="Fact not found")
    return FactResponse(
        id=fact.id,
        fact_text=fact.fact_text,
        category=fact.category,
        confidence=fact.confidence,
        status=fact.status,
        branch_name=fact.branch_name,
        created_at=fact.created_at.isoformat() if fact.created_at else None,
    )


@router.patch("/facts/{fact_id}", response_model=FactResponse)
async def update_fact(
    fact_id: str,
    body: FactUpdate,
    session: AsyncSession = Depends(get_session),
):
    engine = FactEngine(session, get_embedding_provider())
    try:
        fact = await engine.update_fact(
            fact_id=fact_id,
            fact_text=body.fact_text,
            confidence=body.confidence,
            status=body.status,
            metadata=body.metadata,
        )
    except FactNotFoundError:
        raise HTTPException(status_code=404, detail="Fact not found")
    return FactResponse(
        id=fact.id,
        fact_text=fact.fact_text,
        category=fact.category,
        confidence=fact.confidence,
        status=fact.status,
        branch_name=fact.branch_name,
        created_at=fact.created_at.isoformat() if fact.created_at else None,
    )


@router.get("/facts")
async def list_facts(
    branch: str = "main",
    category: str | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
):
    engine = FactEngine(session, get_embedding_provider())
    facts = await engine.list_facts(
        branch_name=branch, category=category, limit=limit
    )
    return {
        "facts": [
            FactResponse(
                id=f.id,
                fact_text=f.fact_text,
                category=f.category,
                confidence=f.confidence,
                status=f.status,
                branch_name=f.branch_name,
                created_at=f.created_at.isoformat() if f.created_at else None,
            ).model_dump()
            for f in facts
        ]
    }
