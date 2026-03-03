"""Tests for MemoryEngine — write, search, branch, snapshot, timeline, merge, count."""

from __future__ import annotations

import pytest
import pytest_asyncio

from day1.core.embedding import MockEmbedding
from day1.core.memory_engine import MemoryEngine


@pytest_asyncio.fixture
async def engine(db_session):
    return MemoryEngine(db_session, embedder=MockEmbedding(dims=64))


# ── Write ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_write_basic(engine):
    mem = await engine.write(text="Test memory", session_id="s1")
    assert mem.id is not None
    assert mem.text == "Test memory"
    assert mem.branch_name == "main"
    assert mem.session_id == "s1"


@pytest.mark.asyncio
async def test_write_enrichment(engine):
    mem = await engine.write(
        text="Architecture decision: use SQLAlchemy",
        category="decision",
        confidence=0.95,
        source_type="user_input",
    )
    assert mem.category == "decision"
    assert mem.confidence == 0.95
    assert mem.source_type == "user_input"
    assert mem.status == "active"


@pytest.mark.asyncio
async def test_write_file_context(engine):
    mem = await engine.write(
        text="Fixed import in app.py",
        file_context="src/day1/api/app.py",
        context="Mount the ingest router",
    )
    assert mem.file_context == "src/day1/api/app.py"
    assert mem.context == "Mount the ingest router"


# ── Search ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_returns_results(engine):
    await engine.write(text="Python is great for scripting", session_id="s1")
    await engine.write(text="FastAPI uses async Python", session_id="s1")

    results = await engine.search(query="Python")
    assert len(results) >= 1
    assert any("Python" in r["text"] for r in results)


@pytest.mark.asyncio
async def test_search_empty_query(engine):
    await engine.write(text="Recent memory", session_id="s1")
    results = await engine.search(query="")
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_search_branch_isolation(engine):
    await engine.write(text="Main branch memory", branch_name="main")
    await engine.create_branch("feature", parent_branch="main")
    await engine.write(text="Feature branch memory", branch_name="feature")

    main_results = await engine.search(query="memory", branch_name="main")
    feature_results = await engine.search(query="memory", branch_name="feature")

    main_texts = [r["text"] for r in main_results]
    feature_texts = [r["text"] for r in feature_results]

    assert "Main branch memory" in main_texts
    assert "Feature branch memory" not in main_texts
    assert "Feature branch memory" in feature_texts


@pytest.mark.asyncio
async def test_search_enrichment_in_results(engine):
    await engine.write(
        text="Decision to use curl hooks",
        category="decision",
        confidence=0.9,
        source_type="user_input",
    )
    results = await engine.search(query="curl hooks")
    assert len(results) >= 1
    r = results[0]
    assert r["category"] == "decision"
    assert r["confidence"] == 0.9
    assert r["source_type"] == "user_input"
    assert r["status"] == "active"


# ── Branch ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_branch_create(engine):
    branch = await engine.create_branch("experiment", description="Test branch")
    assert branch.branch_name == "experiment"
    assert branch.parent_branch == "main"
    assert branch.description == "Test branch"


@pytest.mark.asyncio
async def test_branch_list(engine):
    branches = await engine.list_branches()
    names = [b.branch_name for b in branches]
    assert "main" in names


@pytest.mark.asyncio
async def test_branch_get(engine):
    branch = await engine.get_branch("main")
    assert branch.branch_name == "main"


@pytest.mark.asyncio
async def test_branch_not_found(engine):
    with pytest.raises(ValueError, match="Branch not found"):
        await engine.get_branch("nonexistent")


# ── Snapshot ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_snapshot_create(engine):
    snap = await engine.create_snapshot("main", label="before-refactor")
    assert snap.id is not None
    assert snap.label == "before-refactor"
    assert snap.branch_name == "main"


@pytest.mark.asyncio
async def test_snapshot_list(engine):
    await engine.create_snapshot("main", label="s1")
    await engine.create_snapshot("main", label="s2")
    snaps = await engine.list_snapshots("main")
    assert len(snaps) >= 2


@pytest.mark.asyncio
async def test_snapshot_restore(engine):
    await engine.write(text="Before snapshot", session_id="s1")
    snap = await engine.create_snapshot("main", label="checkpoint")
    await engine.write(text="After snapshot", session_id="s1")

    restored = await engine.restore_snapshot(snap.id)
    texts = [m["text"] for m in restored["memories"]]
    assert "Before snapshot" in texts
    assert "After snapshot" not in texts


# ── Search Filtering ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_filter_by_category(engine):
    await engine.write(text="Bug fix for login", category="bug_fix")
    await engine.write(text="Decision to use FastAPI", category="decision")
    results = await engine.search(query="fix login FastAPI", category="bug_fix")
    for r in results:
        assert r["category"] == "bug_fix"


@pytest.mark.asyncio
async def test_search_filter_by_source_type(engine):
    await engine.write(text="User asked about auth", source_type="user_input")
    await engine.write(text="Tool read file", source_type="tool_observation")
    results = await engine.search(query="auth file", source_type="user_input")
    for r in results:
        assert r["source_type"] == "user_input"


@pytest.mark.asyncio
async def test_search_filter_by_status(engine):
    await engine.write(text="Active memory", status="active")
    await engine.write(text="Archived memory", status="archived")
    results = await engine.search(query="memory", status="active")
    for r in results:
        assert r["status"] == "active"


# ── Timeline ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_timeline_returns_chronological(engine):
    await engine.write(text="First memory", session_id="s1")
    await engine.write(text="Second memory", session_id="s1")
    entries = await engine.timeline(branch_name="main")
    assert len(entries) >= 2
    # Newest first
    assert entries[0]["text"] == "Second memory"
    assert entries[1]["text"] == "First memory"


@pytest.mark.asyncio
async def test_timeline_filter_by_category(engine):
    await engine.write(text="A decision", category="decision")
    await engine.write(text="A pattern", category="pattern")
    entries = await engine.timeline(branch_name="main", category="decision")
    assert len(entries) == 1
    assert entries[0]["category"] == "decision"


@pytest.mark.asyncio
async def test_timeline_filter_by_session(engine):
    await engine.write(text="Session A memory", session_id="session-a")
    await engine.write(text="Session B memory", session_id="session-b")
    entries = await engine.timeline(branch_name="main", session_id="session-a")
    assert len(entries) == 1
    assert entries[0]["session_id"] == "session-a"


# ── Count ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_count(engine):
    assert await engine.count("main") == 0
    await engine.write(text="Memory 1")
    await engine.write(text="Memory 2")
    assert await engine.count("main") == 2


@pytest.mark.asyncio
async def test_count_branch_isolation(engine):
    await engine.write(text="Main memory")
    await engine.create_branch("other")
    await engine.write(text="Other memory", branch_name="other")
    assert await engine.count("main") == 1
    assert await engine.count("other") == 1


# ── Merge ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_merge_branch(engine):
    await engine.create_branch("feature")
    await engine.write(text="Feature work", branch_name="feature", category="decision")
    result = await engine.merge_branch("feature", "main")
    assert result["merged"] == 1
    assert result["skipped_duplicates"] == 0
    # Verify it's on main now
    main_results = await engine.search(query="Feature work", branch_name="main")
    assert any("Feature work" in r["text"] for r in main_results)


@pytest.mark.asyncio
async def test_merge_branch_skips_duplicates(engine):
    await engine.write(text="Shared memory")
    await engine.create_branch("dup-test")
    await engine.write(text="Shared memory", branch_name="dup-test")
    await engine.write(text="New memory", branch_name="dup-test")
    result = await engine.merge_branch("dup-test", "main")
    assert result["merged"] == 1
    assert result["skipped_duplicates"] == 1


@pytest.mark.asyncio
async def test_merge_branch_not_found(engine):
    with pytest.raises(ValueError, match="Branch not found"):
        await engine.merge_branch("nonexistent", "main")
