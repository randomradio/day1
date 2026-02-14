"""Tests for REST API endpoints."""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_TEST_DB_URL = os.environ.get(
    "BM_TEST_DATABASE_URL",
    os.environ.get(
        "BM_DATABASE_URL",
        "mysql+aiomysql://root:111@127.0.0.1:6001/branchedmind",
    ),
)
os.environ["BM_DATABASE_URL"] = _TEST_DB_URL
os.environ["BM_EMBEDDING_PROVIDER"] = "mock"

from branchedmind.api.app import app
from branchedmind.core.branch_manager import BranchManager
from branchedmind.db.engine import get_session
from branchedmind.db.models import Base


@pytest_asyncio.fixture
async def client():
    """Create test client with fresh isolated database."""
    engine = create_async_engine(_TEST_DB_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        # Create FULLTEXT indexes (MO replaces FTS5)
        for stmt in [
            "CREATE FULLTEXT INDEX IF NOT EXISTS ft_facts ON facts(fact_text, category)",
            "CREATE FULLTEXT INDEX IF NOT EXISTS ft_obs ON observations(summary, tool_name)",
        ]:
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    # Yield same session for both override and main branch init
    async with session_factory() as session:
        # Override get_session to use this test's session
        def override_get_session():
            return session

        app.dependency_overrides[get_session] = override_get_session

        # Init main branch (using same session)
        mgr = BranchManager(session)
        await mgr.ensure_main_branch()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_create_and_get_fact(client):
    resp = await client.post("/api/v1/facts", json={
        "fact_text": "The API is built with FastAPI",
        "category": "architecture",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["fact_text"] == "The API is built with FastAPI"
    fact_id = data["id"]

    resp = await client.get(f"/api/v1/facts/{fact_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == fact_id


@pytest.mark.asyncio
async def test_search_facts(client):
    await client.post("/api/v1/facts", json={
        "fact_text": "SQLAlchemy is the ORM used in this project",
    })

    resp = await client.get("/api/v1/facts/search", params={
        "query": "SQLAlchemy ORM",
        "search_type": "keyword",
    })
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1


@pytest.mark.asyncio
async def test_branch_operations(client):
    resp = await client.post("/api/v1/branches", json={
        "branch_name": "test_branch",
        "description": "A test branch",
    })
    assert resp.status_code == 200
    assert resp.json()["branch_name"] == "test_branch"

    resp = await client.get("/api/v1/branches")
    assert resp.status_code == 200
    names = [b["branch_name"] for b in resp.json()["branches"]]
    assert "main" in names
    assert "test_branch" in names


@pytest.mark.asyncio
async def test_create_observation(client):
    resp = await client.post("/api/v1/observations", json={
        "session_id": "test-sess",
        "observation_type": "tool_use",
        "summary": "Ran pytest successfully",
        "tool_name": "Bash",
    })
    assert resp.status_code == 200
    assert "id" in resp.json()


@pytest.mark.asyncio
async def test_create_relation(client):
    resp = await client.post("/api/v1/relations", json={
        "source_entity": "FastAPI",
        "target_entity": "Pydantic",
        "relation_type": "depends_on",
    })
    assert resp.status_code == 200
    assert "id" in resp.json()


@pytest.mark.asyncio
async def test_snapshot_operations(client):
    resp = await client.post("/api/v1/snapshots", json={
        "label": "test-snapshot",
    })
    assert resp.status_code == 200
    assert resp.json()["label"] == "test-snapshot"

    resp = await client.get("/api/v1/snapshots")
    assert resp.status_code == 200
    assert len(resp.json()["snapshots"]) >= 1
