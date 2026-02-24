"""Tests for BranchTopologyEngine."""

from __future__ import annotations

import pytest
import pytest_asyncio
from datetime import datetime, timedelta

from sqlalchemy import update

from day1.core.branch_manager import BranchManager
from day1.core.branch_topology_engine import BranchTopologyEngine
from day1.core.exceptions import BranchNotFoundError
from day1.core.fact_engine import FactEngine
from day1.db.models import BranchRegistry


@pytest.mark.asyncio
async def test_get_topology_only_main(db_session):
    """Topology with only main branch returns single root node."""
    engine = BranchTopologyEngine(db_session)
    tree = await engine.get_topology()

    assert tree["branch_name"] == "main"
    assert tree["children"] == []
    assert tree["status"] == "active"


@pytest.mark.asyncio
async def test_get_topology_with_children(db_session):
    """Topology shows child branches."""
    mgr = BranchManager(db_session)
    await mgr.create_branch("task/feature-a", parent_branch="main")
    await mgr.create_branch("task/feature-b", parent_branch="main")

    engine = BranchTopologyEngine(db_session)
    tree = await engine.get_topology()

    assert tree["branch_name"] == "main"
    assert len(tree["children"]) == 2
    child_names = {c["branch_name"] for c in tree["children"]}
    assert child_names == {"task/feature-a", "task/feature-b"}


@pytest.mark.asyncio
async def test_get_topology_nested_hierarchy(db_session):
    """Topology builds nested tree from parent-child relationships."""
    mgr = BranchManager(db_session)
    await mgr.create_branch("task/project", parent_branch="main")
    await mgr.create_branch("task/project/agent-1", parent_branch="task/project")
    await mgr.create_branch("task/project/agent-2", parent_branch="task/project")

    engine = BranchTopologyEngine(db_session)
    tree = await engine.get_topology()

    assert len(tree["children"]) == 1
    project = tree["children"][0]
    assert project["branch_name"] == "task/project"
    assert len(project["children"]) == 2
    agent_names = {c["branch_name"] for c in project["children"]}
    assert agent_names == {"task/project/agent-1", "task/project/agent-2"}


@pytest.mark.asyncio
async def test_get_topology_excludes_archived(db_session):
    """Archived branches are excluded by default."""
    mgr = BranchManager(db_session)
    await mgr.create_branch("task/old", parent_branch="main")
    await mgr.archive_branch("task/old")

    engine = BranchTopologyEngine(db_session)
    tree = await engine.get_topology()
    assert len(tree["children"]) == 0

    # Include archived
    tree_all = await engine.get_topology(include_archived=True)
    assert len(tree_all["children"]) == 1
    assert tree_all["children"][0]["status"] == "archived"


@pytest.mark.asyncio
async def test_get_topology_nonexistent_root(db_session):
    """Requesting topology from nonexistent root raises error."""
    engine = BranchTopologyEngine(db_session)
    with pytest.raises(BranchNotFoundError):
        await engine.get_topology(root_branch="nonexistent")


@pytest.mark.asyncio
async def test_get_branch_stats(db_session, mock_embedder):
    """Branch stats returns counts of facts, conversations, observations."""
    engine = BranchTopologyEngine(db_session)

    # Write some facts to main
    fact_engine = FactEngine(db_session, mock_embedder)
    await fact_engine.write_fact(fact_text="Fact 1", branch_name="main")
    await fact_engine.write_fact(fact_text="Fact 2", branch_name="main")

    stats = await engine.get_branch_stats("main")

    assert stats["branch_name"] == "main"
    assert stats["fact_count"] == 2
    assert stats["conversation_count"] >= 0
    assert stats["observation_count"] >= 0
    assert stats["last_activity"] is not None


@pytest.mark.asyncio
async def test_get_branch_stats_nonexistent(db_session):
    """Stats for nonexistent branch raises error."""
    engine = BranchTopologyEngine(db_session)
    with pytest.raises(BranchNotFoundError):
        await engine.get_branch_stats("nonexistent")


@pytest.mark.asyncio
async def test_enrich_branch_metadata(db_session):
    """Enrich branch metadata with purpose, owner, TTL, tags."""
    engine = BranchTopologyEngine(db_session)

    branch = await engine.enrich_branch_metadata(
        branch_name="main",
        purpose="Primary knowledge store",
        owner="team-alpha",
        ttl_days=90,
        tags=["production", "core"],
    )

    meta = branch.metadata_json
    assert meta["purpose"] == "Primary knowledge store"
    assert meta["owner"] == "team-alpha"
    assert meta["ttl_days"] == 90
    assert meta["tags"] == ["production", "core"]
    assert "enriched_at" in meta


@pytest.mark.asyncio
async def test_enrich_branch_metadata_partial(db_session):
    """Partial enrichment preserves existing fields."""
    engine = BranchTopologyEngine(db_session)

    # First enrichment
    await engine.enrich_branch_metadata(
        branch_name="main",
        purpose="Original purpose",
        owner="team-alpha",
    )

    # Second enrichment (only tags)
    branch = await engine.enrich_branch_metadata(
        branch_name="main",
        tags=["updated"],
    )

    meta = branch.metadata_json
    assert meta["purpose"] == "Original purpose"
    assert meta["owner"] == "team-alpha"
    assert meta["tags"] == ["updated"]


@pytest.mark.asyncio
async def test_auto_archive_merged(db_session):
    """Auto-archive archives merged branches."""
    mgr = BranchManager(db_session)
    await mgr.create_branch("task/done", parent_branch="main")

    # Mark as merged
    await db_session.execute(
        update(BranchRegistry)
        .where(BranchRegistry.branch_name == "task/done")
        .values(status="merged")
    )
    await db_session.commit()

    engine = BranchTopologyEngine(db_session)
    result = await engine.apply_auto_archive(archive_merged=True)

    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["branch_name"] == "task/done"
    assert result["candidates"][0]["reason"] == "merged"
    assert result["archived"] == 1


@pytest.mark.asyncio
async def test_auto_archive_dry_run(db_session):
    """Dry run returns candidates without archiving."""
    mgr = BranchManager(db_session)
    await mgr.create_branch("task/done", parent_branch="main")

    await db_session.execute(
        update(BranchRegistry)
        .where(BranchRegistry.branch_name == "task/done")
        .values(status="merged")
    )
    await db_session.commit()

    engine = BranchTopologyEngine(db_session)
    result = await engine.apply_auto_archive(archive_merged=True, dry_run=True)

    assert len(result["candidates"]) == 1
    assert result["archived"] == 0

    # Branch should still be merged (not archived)
    branch = await mgr.get_branch("task/done")
    assert branch.status == "merged"


@pytest.mark.asyncio
async def test_check_ttl_expiry(db_session):
    """TTL expiry detection works for branches with expired TTL."""
    mgr = BranchManager(db_session)
    await mgr.create_branch("task/temp", parent_branch="main")

    # Set TTL to 0 days (already expired) and backdate forked_at
    await db_session.execute(
        update(BranchRegistry)
        .where(BranchRegistry.branch_name == "task/temp")
        .values(
            metadata={"ttl_days": 1},
            forked_at=datetime.utcnow() - timedelta(days=5),
        )
    )
    await db_session.commit()

    engine = BranchTopologyEngine(db_session)
    expired = await engine.check_ttl_expiry()

    assert len(expired) == 1
    assert expired[0]["branch_name"] == "task/temp"
    assert expired[0]["ttl_days"] == 1


@pytest.mark.asyncio
async def test_check_ttl_no_expired(db_session):
    """TTL check returns empty when no branches are expired."""
    mgr = BranchManager(db_session)
    await mgr.create_branch("task/fresh", parent_branch="main")

    # Set TTL to 30 days (not expired yet)
    await db_session.execute(
        update(BranchRegistry)
        .where(BranchRegistry.branch_name == "task/fresh")
        .values(metadata={"ttl_days": 30})
    )
    await db_session.commit()

    engine = BranchTopologyEngine(db_session)
    expired = await engine.check_ttl_expiry()
    assert len(expired) == 0


@pytest.mark.asyncio
async def test_validate_branch_name_conventions(db_session):
    """Branch name validation recognises conventions."""
    engine = BranchTopologyEngine(db_session)

    # Valid names
    r = await engine.validate_branch_name("task/my-feature")
    assert r["valid"] is True
    assert r["convention"] == "task"

    r = await engine.validate_branch_name("task/my-feature/agent-1")
    assert r["valid"] is True
    assert r["convention"] == "task/agent"

    r = await engine.validate_branch_name("template/bug-fix/v1")
    assert r["valid"] is True
    assert r["convention"] == "template"

    r = await engine.validate_branch_name("team/alpha/search")
    assert r["valid"] is True
    assert r["convention"] == "team"

    r = await engine.validate_branch_name("main")
    assert r["valid"] is True
    assert r["convention"] == "main"

    # Invalid name — gets suggestion
    r = await engine.validate_branch_name("my-random-branch")
    assert r["valid"] is False
    assert r["suggestion"] == "task/my-random-branch"
