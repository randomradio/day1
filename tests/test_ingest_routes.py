"""Tests for ingest routes — hook events, MCP tool listing, invocation, timeline, count."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

# Ensure test env is set before importing app
import os
os.environ.setdefault("BM_EMBEDDING_PROVIDER", "mock")
os.environ.setdefault("BM_DATABASE_URL", "mysql+aiomysql://root:111@127.0.0.1:6001/day1")

from day1.api.app import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.asyncio
async def test_hook_user_prompt_submit():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/ingest/claude-hook",
            headers={"X-Day1-Hook-Event": "UserPromptSubmit"},
            json={"prompt": "How do I fix this bug?", "session_id": "test-session"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["event"] == "UserPromptSubmit"


@pytest.mark.asyncio
async def test_hook_session_start():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/ingest/claude-hook",
            headers={"X-Day1-Hook-Event": "SessionStart"},
            json={"session_id": "test-session"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["event"] == "SessionStart"


@pytest.mark.asyncio
async def test_hook_stop():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/ingest/claude-hook",
            headers={"X-Day1-Hook-Event": "Stop"},
            json={"last_assistant_message": "Done!", "session_id": "test-session"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_hook_post_tool_use():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/ingest/claude-hook",
            headers={"X-Day1-Hook-Event": "PostToolUse"},
            json={
                "tool_name": "Read",
                "tool_input": "file.py",
                "tool_response": "contents...",
                "session_id": "test-session",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_mcp_tool_listing():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/ingest/mcp-tools")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 11
    names = [t["name"] for t in data["tools"]]
    assert "memory_write" in names
    assert "memory_search" in names
    assert "memory_timeline" in names
    assert "memory_merge" in names
    assert "memory_count" in names


@pytest.mark.asyncio
async def test_mcp_tool_invocation():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/ingest/mcp",
            json={
                "tool": "memory_write",
                "arguments": {"text": "test via REST", "session_id": "rest-test"},
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tool"] == "memory_write"
    assert "result" in data


@pytest.mark.asyncio
async def test_mcp_tool_unknown():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/ingest/mcp",
            json={"tool": "nonexistent_tool", "arguments": {}},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_timeline_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/memories/timeline", params={"branch": "main", "limit": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert "timeline" in data
    assert "count" in data


@pytest.mark.asyncio
async def test_count_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/memories/count", params={"branch": "main"})
    assert resp.status_code == 200
    data = resp.json()
    assert "count" in data
    assert "branch" in data
