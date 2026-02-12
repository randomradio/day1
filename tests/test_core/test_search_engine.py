"""Tests for SearchEngine."""

from __future__ import annotations

import pytest

from branchedmind.core.embedding import MockEmbedding
from branchedmind.core.fact_engine import FactEngine
from branchedmind.core.search_engine import SearchEngine


@pytest.mark.asyncio
async def test_keyword_search(db_session, mock_embedder):
    fact_engine = FactEngine(db_session, mock_embedder)
    search_engine = SearchEngine(db_session, mock_embedder)

    await fact_engine.write_fact(
        fact_text="FastAPI is used for the REST API server",
        category="architecture",
    )
    await fact_engine.write_fact(
        fact_text="The authentication bug was fixed in session 42",
        category="bug_fix",
    )

    results = await search_engine.search(
        query="FastAPI REST",
        search_type="keyword",
    )

    assert len(results) >= 1
    assert any("FastAPI" in r["fact_text"] for r in results)


@pytest.mark.asyncio
async def test_vector_search(db_session, mock_embedder):
    fact_engine = FactEngine(db_session, mock_embedder)
    search_engine = SearchEngine(db_session, mock_embedder)

    await fact_engine.write_fact(
        fact_text="The project uses SQLAlchemy for database operations",
    )
    await fact_engine.write_fact(
        fact_text="Redis is used for caching layer",
    )

    results = await search_engine.search(
        query="database ORM",
        search_type="vector",
    )

    assert len(results) >= 1


@pytest.mark.asyncio
async def test_hybrid_search(db_session, mock_embedder):
    fact_engine = FactEngine(db_session, mock_embedder)
    search_engine = SearchEngine(db_session, mock_embedder)

    await fact_engine.write_fact(
        fact_text="SQLAlchemy async is the ORM of choice",
        category="architecture",
    )

    results = await search_engine.search(
        query="SQLAlchemy ORM",
        search_type="hybrid",
    )

    assert len(results) >= 1


@pytest.mark.asyncio
async def test_empty_query_returns_recent(db_session, mock_embedder):
    fact_engine = FactEngine(db_session, mock_embedder)
    search_engine = SearchEngine(db_session, mock_embedder)

    await fact_engine.write_fact(fact_text="First fact")
    await fact_engine.write_fact(fact_text="Second fact")

    results = await search_engine.search(
        query="",
        search_type="keyword",
    )

    assert len(results) == 2


@pytest.mark.asyncio
async def test_search_with_category_filter(db_session, mock_embedder):
    fact_engine = FactEngine(db_session, mock_embedder)
    search_engine = SearchEngine(db_session, mock_embedder)

    await fact_engine.write_fact(
        fact_text="Bug found in auth module",
        category="bug_fix",
    )
    await fact_engine.write_fact(
        fact_text="Architecture uses microservices",
        category="architecture",
    )

    results = await search_engine.search(
        query="",
        search_type="keyword",
        category="bug_fix",
    )

    assert len(results) == 1
    assert results[0]["category"] == "bug_fix"
