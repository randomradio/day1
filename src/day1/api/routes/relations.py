"""REST API routes for relations (knowledge graph)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.relation_engine import RelationEngine
from day1.db.engine import get_session
from day1.db.models import Relation

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
    entity: str | None = None,
    relation_type: str | None = None,
    depth: int = 1,
    branch: str = "main",
    limit: int = 200,
    session: AsyncSession = Depends(get_session),
):
    """Graph query.

    - With `entity`: BFS traversal around an entity (existing behavior).
    - Without `entity`: graph snapshot placeholder for dashboard/SDK integration.
    """
    engine = RelationEngine(session)
    if entity:
        results = await engine.graph_query(
            entity=entity,
            relation_type=relation_type,
            depth=depth,
            branch_name=branch,
        )
    else:
        stmt = (
            select(Relation)
            .where(
                Relation.branch_name == branch,
                Relation.valid_to.is_(None),
            )
            .order_by(Relation.created_at.desc())
            .limit(limit)
        )
        if relation_type:
            stmt = stmt.where(Relation.relation_type == relation_type)
        rel_rows = (await session.execute(stmt)).scalars().all()
        results = [
            {
                "source": r.source_entity,
                "target": r.target_entity,
                "relation": r.relation_type,
                "properties": r.properties,
                "confidence": r.confidence,
                "id": r.id,
            }
            for r in rel_rows
        ]

    node_seen: set[str] = set()
    nodes: list[dict[str, str]] = []
    for rel in results:
        for entity_name in (rel["source"], rel["target"]):
            if entity_name in node_seen:
                continue
            node_seen.add(entity_name)
            nodes.append({"id": entity_name, "label": entity_name})

    edges = [
        {
            "id": rel["id"],
            "source": rel["source"],
            "target": rel["target"],
            "label": rel["relation"],
            "confidence": rel.get("confidence"),
        }
        for rel in results
    ]

    return {
        "mode": "entity" if entity else "snapshot",
        "entity": entity,
        "relations": results,
        "nodes": nodes,
        "edges": edges,
        "count": len(results),
    }


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
