"""REST API routes for facts."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.embedding import get_embedding_provider
from day1.core.exceptions import FactNotFoundError
from day1.core.fact_engine import FactEngine
from day1.db.engine import get_session
from day1.db.models import Fact, Relation

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


@router.get("/facts/{fact_id}/related")
async def get_fact_related(
    fact_id: str,
    branch: str | None = None,
    limit: int = 25,
    session: AsyncSession = Depends(get_session),
):
    """Placeholder cross-reference endpoint for graph/SDK integration."""
    engine = FactEngine(session, get_embedding_provider())
    try:
        fact = await engine.get_fact(fact_id)
    except FactNotFoundError:
        raise HTTPException(status_code=404, detail="Fact not found")

    branch_name = branch or fact.branch_name
    text_lower = (fact.fact_text or "").lower()
    entities = []
    meta = fact.metadata_json or {}
    if isinstance(meta.get("entities"), list):
        entities = [
            str(e).strip()
            for e in meta["entities"]
            if str(e).strip()
        ]

    if entities:
        stmt = (
            select(Relation)
            .where(
                Relation.branch_name == branch_name,
                Relation.valid_to.is_(None),
                or_(
                    Relation.source_entity.in_(entities),
                    Relation.target_entity.in_(entities),
                ),
            )
            .order_by(Relation.created_at.desc())
            .limit(limit)
        )
        rel_rows = (await session.execute(stmt)).scalars().all()
    else:
        # Fallback placeholder heuristic: sample recent relations and keep those
        # whose endpoint labels appear in the fact text.
        stmt = (
            select(Relation)
            .where(
                Relation.branch_name == branch_name,
                Relation.valid_to.is_(None),
            )
            .order_by(Relation.created_at.desc())
            .limit(max(limit * 4, 50))
        )
        rel_rows = []
        for rel in (await session.execute(stmt)).scalars().all():
            if (
                rel.source_entity.lower() in text_lower
                or rel.target_entity.lower() in text_lower
            ):
                rel_rows.append(rel)
                if len(rel_rows) >= limit:
                    break

    edge_entities = {
        rel.source_entity
        for rel in rel_rows
    } | {
        rel.target_entity
        for rel in rel_rows
    }

    related_facts = []
    if edge_entities:
        stmt = (
            select(Fact)
            .where(
                Fact.branch_name == branch_name,
                Fact.status == "active",
                Fact.id != fact.id,
            )
            .order_by(Fact.created_at.desc())
            .limit(max(limit * 4, 50))
        )
        for candidate in (await session.execute(stmt)).scalars().all():
            candidate_text = (candidate.fact_text or "").lower()
            if any(entity.lower() in candidate_text for entity in edge_entities):
                related_facts.append(candidate)
                if len(related_facts) >= limit:
                    break

    return {
        "fact": FactResponse(
            id=fact.id,
            fact_text=fact.fact_text,
            category=fact.category,
            confidence=fact.confidence,
            status=fact.status,
            branch_name=fact.branch_name,
            created_at=fact.created_at.isoformat() if fact.created_at else None,
        ).model_dump(),
        "entities": sorted(edge_entities)[:limit],
        "relations": [
            {
                "id": r.id,
                "source_entity": r.source_entity,
                "target_entity": r.target_entity,
                "relation_type": r.relation_type,
                "confidence": r.confidence,
                "properties": r.properties,
            }
            for r in rel_rows
        ],
        "related_facts": [
            FactResponse(
                id=f.id,
                fact_text=f.fact_text,
                category=f.category,
                confidence=f.confidence,
                status=f.status,
                branch_name=f.branch_name,
                created_at=f.created_at.isoformat() if f.created_at else None,
            ).model_dump()
            for f in related_facts
        ],
        "count": len(rel_rows),
    }


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
    facts = await engine.list_facts(branch_name=branch, category=category, limit=limit)
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
