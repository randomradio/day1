"""Tests for BranchManager and MergeEngine."""

from __future__ import annotations

import pytest

from day1.core.branch_manager import BranchManager
from day1.core.embedding import MockEmbedding
from day1.core.exceptions import BranchExistsError, BranchNotFoundError
from day1.core.fact_engine import FactEngine
from day1.core.merge_engine import MergeEngine
from day1.core.relation_engine import RelationEngine


@pytest.mark.asyncio
async def test_create_and_list_branch(db_session):
    mgr = BranchManager(db_session)

    branch = await mgr.create_branch(
        branch_name="experiment-auth",
        description="Testing new auth approach",
    )

    assert branch.branch_name == "experiment-auth"
    assert branch.parent_branch == "main"
    assert branch.status == "active"

    branches = await mgr.list_branches()
    names = [b.branch_name for b in branches]
    assert "main" in names
    assert "experiment-auth" in names


@pytest.mark.asyncio
async def test_create_duplicate_branch_fails(db_session):
    mgr = BranchManager(db_session)
    await mgr.create_branch(branch_name="test-branch")

    with pytest.raises(BranchExistsError):
        await mgr.create_branch(branch_name="test-branch")


@pytest.mark.asyncio
async def test_create_branch_copies_facts(db_session, mock_embedder):
    mgr = BranchManager(db_session)
    fact_engine = FactEngine(db_session, mock_embedder)

    # Write fact on main
    await fact_engine.write_fact(
        fact_text="This fact exists on main",
        branch_name="main",
    )

    # Create branch (DATA BRANCH creates zero-copy reference)
    await mgr.create_branch(branch_name="feature-x")

    # Write a fact on the new branch
    await fact_engine.write_fact(
        fact_text="This fact is on feature-x",
        branch_name="feature-x",
    )

    # Verify facts are isolated per branch
    main_facts = await fact_engine.list_facts(branch_name="main")
    feature_facts = await fact_engine.list_facts(branch_name="feature-x")

    assert len(main_facts) == 1
    assert main_facts[0].fact_text == "This fact exists on main"
    assert len(feature_facts) == 1
    assert feature_facts[0].fact_text == "This fact is on feature-x"


@pytest.mark.asyncio
async def test_branch_isolation(db_session, mock_embedder):
    mgr = BranchManager(db_session)
    fact_engine = FactEngine(db_session, mock_embedder)

    await mgr.create_branch(branch_name="isolated")

    # Write fact only on isolated branch
    await fact_engine.write_fact(
        fact_text="Only on isolated branch",
        branch_name="isolated",
    )

    # Main should not have it
    main_facts = await fact_engine.list_facts(branch_name="main")
    isolated_facts = await fact_engine.list_facts(branch_name="isolated")

    assert not any(f.fact_text == "Only on isolated branch" for f in main_facts)
    assert any(f.fact_text == "Only on isolated branch" for f in isolated_facts)


@pytest.mark.asyncio
async def test_diff_branches(db_session, mock_embedder):
    mgr = BranchManager(db_session)
    fact_engine = FactEngine(db_session, mock_embedder)
    merge_engine = MergeEngine(db_session)

    await mgr.create_branch(branch_name="feature")

    # Add new fact only on feature branch
    await fact_engine.write_fact(
        fact_text="New discovery on feature branch",
        branch_name="feature",
    )

    diff = await merge_engine.diff("feature", "main")
    assert len(diff.new_facts) >= 1


@pytest.mark.asyncio
async def test_auto_merge(db_session, mock_embedder):
    mgr = BranchManager(db_session)
    fact_engine = FactEngine(db_session, mock_embedder)
    merge_engine = MergeEngine(db_session)

    await mgr.create_branch(branch_name="to-merge")

    await fact_engine.write_fact(
        fact_text="Unique fact on branch to merge",
        branch_name="to-merge",
    )

    result = await merge_engine.merge(
        source_branch="to-merge",
        target_branch="main",
        strategy="auto",
    )

    assert result["merged_count"] >= 1
    assert result["merge_id"] is not None


@pytest.mark.asyncio
async def test_cherry_pick_merge(db_session, mock_embedder):
    mgr = BranchManager(db_session)
    fact_engine = FactEngine(db_session, mock_embedder)
    merge_engine = MergeEngine(db_session)

    await mgr.create_branch(branch_name="cherry")

    fact1 = await fact_engine.write_fact(
        fact_text="Want this fact",
        branch_name="cherry",
    )
    fact2 = await fact_engine.write_fact(
        fact_text="Don't want this fact",
        branch_name="cherry",
    )

    result = await merge_engine.merge(
        source_branch="cherry",
        target_branch="main",
        strategy="cherry_pick",
        items=[fact1.id],
    )

    assert result["merged_count"] == 1

    # Verify only fact1 was merged to main
    main_facts = await fact_engine.list_facts(branch_name="main")
    texts = [f.fact_text for f in main_facts]
    assert "Want this fact" in texts
    assert "Don't want this fact" not in texts
