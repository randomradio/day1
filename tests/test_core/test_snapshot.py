"""Tests for SnapshotManager."""

from __future__ import annotations

import pytest

from day1.core.embedding import MockEmbedding
from day1.core.fact_engine import FactEngine
from day1.core.snapshot_manager import SnapshotManager


@pytest.mark.asyncio
async def test_create_and_list_snapshot(db_session, mock_embedder):
    fact_engine = FactEngine(db_session, mock_embedder)
    snap_mgr = SnapshotManager(db_session)

    await fact_engine.write_fact(fact_text="Fact before snapshot")

    snapshot = await snap_mgr.create_snapshot(
        branch_name="main",
        label="before-refactor",
    )

    assert snapshot.id is not None
    assert snapshot.label == "before-refactor"
    assert snapshot.snapshot_data is not None
    assert len(snapshot.snapshot_data["facts"]) == 1

    # List snapshots
    snapshots = await snap_mgr.list_snapshots()
    assert len(snapshots) == 1


@pytest.mark.asyncio
async def test_time_travel_query(db_session, mock_embedder):
    fact_engine = FactEngine(db_session, mock_embedder)
    snap_mgr = SnapshotManager(db_session)

    await fact_engine.write_fact(fact_text="Old fact")

    # Query at a future timestamp should include the fact
    results = await snap_mgr.time_travel_query(
        timestamp="2099-01-01T00:00:00",
        branch_name="main",
    )

    assert len(results) >= 1


@pytest.mark.asyncio
async def test_time_travel_query_filters_by_branch(db_session, mock_embedder):
    fact_engine = FactEngine(db_session, mock_embedder)
    snap_mgr = SnapshotManager(db_session)

    branch_a = "task_tt_branch_a"
    branch_b = "task_tt_branch_b"

    fact_a = await fact_engine.write_fact(
        fact_text="Branch A time-travel fact",
        branch_name=branch_a,
    )
    await fact_engine.write_fact(
        fact_text="Branch B time-travel fact",
        branch_name=branch_b,
    )

    results = await snap_mgr.time_travel_query(
        timestamp="2099-01-01T00:00:00",
        branch_name=branch_a,
    )

    assert any(item["id"] == fact_a.id for item in results)
    assert all("Branch B" not in item["fact_text"] for item in results)
