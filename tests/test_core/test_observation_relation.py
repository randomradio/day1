"""Tests for ObservationEngine and RelationEngine."""

from __future__ import annotations

import pytest

from branchedmind.core.embedding import MockEmbedding
from branchedmind.core.observation_engine import ObservationEngine
from branchedmind.core.relation_engine import RelationEngine


@pytest.mark.asyncio
async def test_write_and_list_observations(db_session, mock_embedder):
    engine = ObservationEngine(db_session, mock_embedder)

    obs = await engine.write_observation(
        session_id="test-session-1",
        observation_type="tool_use",
        summary="Ran pytest and found 3 failing tests",
        tool_name="Bash",
    )

    assert obs.id is not None
    assert obs.observation_type == "tool_use"

    observations = await engine.list_observations(session_id="test-session-1")
    assert len(observations) == 1


@pytest.mark.asyncio
async def test_observation_timeline(db_session, mock_embedder):
    engine = ObservationEngine(db_session, mock_embedder)

    await engine.write_observation(
        session_id="s1",
        observation_type="tool_use",
        summary="First action",
    )
    await engine.write_observation(
        session_id="s1",
        observation_type="discovery",
        summary="Found something",
    )

    timeline = await engine.timeline(session_id="s1")
    assert len(timeline) == 2


@pytest.mark.asyncio
async def test_write_and_query_relation(db_session):
    engine = RelationEngine(db_session)

    rel = await engine.write_relation(
        source_entity="AuthService",
        target_entity="UserModel",
        relation_type="depends_on",
        properties={"coupling": "tight"},
    )

    assert rel.id is not None

    # Graph query
    results = await engine.graph_query(
        entity="AuthService",
        depth=1,
    )

    assert len(results) == 1
    assert results[0]["target"] == "UserModel"
    assert results[0]["relation"] == "depends_on"


@pytest.mark.asyncio
async def test_graph_query_depth(db_session):
    engine = RelationEngine(db_session)

    await engine.write_relation(
        source_entity="A", target_entity="B", relation_type="uses"
    )
    await engine.write_relation(
        source_entity="B", target_entity="C", relation_type="uses"
    )

    # Depth 1: only A->B
    results_d1 = await engine.graph_query(entity="A", depth=1)
    assert len(results_d1) == 1

    # Depth 2: A->B and B->C
    results_d2 = await engine.graph_query(entity="A", depth=2)
    assert len(results_d2) == 2
