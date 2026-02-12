"""Tests for REST API endpoints."""

from __future__ import annotations

import os
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

os.environ["BM_DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["BM_EMBEDDING_PROVIDER"] = "mock"

from branchedmind.api.app import app
from branchedmind.core.branch_manager import BranchManager
from branchedmind.db.engine import get_session
from branchedmind.db.models import Base


@pytest_asyncio.fixture
async def client():
    """Create test client with fresh isolated database."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts "
                "USING fts5(id, fact_text, category)"
            )
        )
        await conn.execute(
            text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS observations_fts "
                "USING fts5(id, summary, tool_name)"
            )
        )

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    # Init main branch
    async with session_factory() as session:
        mgr = BranchManager(session)
        await mgr.ensure_main_branch()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
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
        "branch_name": "test-branch",
        "description": "A test branch",
    })
    assert resp.status_code == 200
    assert resp.json()["branch_name"] == "test-branch"

    resp = await client.get("/api/v1/branches")
    assert resp.status_code == 200
    names = [b["branch_name"] for b in resp.json()["branches"]]
    assert "main" in names
    assert "test-branch" in names


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
