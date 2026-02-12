"""REST API routes for relations (knowledge graph)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from branchedmind.core.relation_engine import RelationEngine
from branchedmind.db.engine import get_session

router = APIRouter()


class RelationCreate(BaseModel):
    source_entity: str
    target_entity: str
    relation_type: str
    properties: dict | None = None
    confidence: float = 1.0
    session_id: str | None = None
    branch: str = "main"


@router.post("/relations")
async def create_relation(
    body: RelationCreate,
    session: AsyncSession = Depends(get_session),
):
    engine = RelationEngine(session)
    rel = await engine.write_relation(
        source_entity=body.source_entity,
        target_entity=body.target_entity,
        relation_type=body.relation_type,
        properties=body.properties,
        confidence=body.confidence,
        session_id=body.session_id,
        branch_name=body.branch,
    )
    return {"id": rel.id}


@router.get("/relations/graph")
async def graph_query(
    entity: str,
    relation_type: str | None = None,
    depth: int = 1,
    branch: str = "main",
    session: AsyncSession = Depends(get_session),
):
    engine = RelationEngine(session)
    results = await engine.graph_query(
        entity=entity,
        relation_type=relation_type,
        depth=depth,
        branch_name=branch,
    )
    return {"relations": results, "count": len(results)}


@router.get("/relations")
async def list_relations(
    branch: str = "main",
    source_entity: str | None = None,
    target_entity: str | None = None,
    relation_type: str | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
):
    engine = RelationEngine(session)
    relations = await engine.list_relations(
        branch_name=branch,
        source_entity=source_entity,
        target_entity=target_entity,
        relation_type=relation_type,
        limit=limit,
    )
    return {
        "relations": [
            {
                "id": r.id,
                "source_entity": r.source_entity,
                "target_entity": r.target_entity,
                "relation_type": r.relation_type,
                "properties": r.properties,
                "confidence": r.confidence,
            }
            for r in relations
        ]
    }
