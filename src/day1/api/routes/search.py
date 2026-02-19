"""REST API routes for search."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.embedding import get_embedding_provider
from day1.core.search_engine import SearchEngine
from day1.db.engine import get_session

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    search_type: str = "hybrid"
    category: str | None = None
    branch: str = "main"
    limit: int = 10
    time_range: dict | None = None


@router.get("/facts/search")
async def search_facts(
    query: str,
    search_type: str = "hybrid",
    category: str | None = None,
    branch: str = "main",
    limit: int = 10,
    session: AsyncSession = Depends(get_session),
):
    engine = SearchEngine(session, get_embedding_provider())
    results = await engine.search(
        query=query,
        search_type=search_type,
        branch_name=branch,
        category=category,
        limit=limit,
    )
    return {"results": results, "count": len(results)}


@router.post("/facts/search")
async def search_facts_post(
    body: SearchRequest,
    session: AsyncSession = Depends(get_session),
):
    engine = SearchEngine(session, get_embedding_provider())
    results = await engine.search(
        query=body.query,
        search_type=body.search_type,
        branch_name=body.branch,
        category=body.category,
        limit=body.limit,
        time_range=body.time_range,
    )
    return {"results": results, "count": len(results)}


@router.get("/observations/search")
async def search_observations(
    query: str,
    branch: str = "main",
    session_id: str | None = None,
    limit: int = 10,
    session: AsyncSession = Depends(get_session),
):
    engine = SearchEngine(session, get_embedding_provider())
    results = await engine.search_observations(
        query=query,
        branch_name=branch,
        session_id=session_id,
        limit=limit,
    )
    return {"results": results, "count": len(results)}
