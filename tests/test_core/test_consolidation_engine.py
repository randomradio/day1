"""Tests for ConsolidationEngine: session/agent/task consolidation."""

from __future__ import annotations

import pytest

from branchedmind.core.branch_manager import BranchManager
from branchedmind.core.consolidation_engine import (
    ConsolidationEngine,
    _jaccard_similarity,
    _infer_category,
    _tokenize,
)
from branchedmind.core.embedding import MockEmbedding
from branchedmind.core.exceptions import ConsolidationError
from branchedmind.core.fact_engine import FactEngine
from branchedmind.core.observation_engine import ObservationEngine
from branchedmind.core.task_engine import TaskEngine


@pytest.mark.asyncio
async def test_session_consolidation(db_session, mock_embedder):
    """Observations should be converted into facts during session consolidation."""
    obs_engine = ObservationEngine(db_session, mock_embedder)
    consolidator = ConsolidationEngine(db_session)

    # Write observations that should become facts
    await obs_engine.write_observation(
        session_id="sess-1",
        observation_type="insight",
        summary="The authentication system uses JWT tokens with RS256 signing",
    )
    await obs_engine.write_observation(
        session_id="sess-1",
        observation_type="decision",
        summary="Decided to use Redis for session caching",
    )
    await obs_engine.write_observation(
        session_id="sess-1",
        observation_type="tool_use",
        summary="Read file auth.py",
        tool_name="Read",
    )

    result = await consolidator.consolidate_session(
        session_id="sess-1",
        branch_name="main",
    )

    # Only insight and decision types should be processed
    assert result["observations_processed"] == 2
    assert result["facts_created"] == 2
    assert result["facts_updated"] == 0
    assert result["facts_deduplicated"] == 0


@pytest.mark.asyncio
async def test_session_consolidation_dedup(db_session, mock_embedder):
    """Similar observations should boost existing facts instead of creating duplicates."""
    obs_engine = ObservationEngine(db_session, mock_embedder)
    fact_engine = FactEngine(db_session, mock_embedder)
    consolidator = ConsolidationEngine(db_session)

    # Pre-existing fact
    await fact_engine.write_fact(
        fact_text="The project uses JWT tokens for authentication with RS256 signing",
        category="architecture",
        confidence=0.7,
    )

    # Very similar observation
    await obs_engine.write_observation(
        session_id="sess-2",
        observation_type="insight",
        summary="The project uses JWT tokens for authentication with RS256 signing algorithm",
    )

    result = await consolidator.consolidate_session(
        session_id="sess-2",
        branch_name="main",
    )

    # Should update existing fact (high Jaccard similarity) rather than creating new
    assert result["observations_processed"] == 1
    assert result["facts_updated"] + result["facts_deduplicated"] >= 1


@pytest.mark.asyncio
async def test_session_consolidation_no_observations(db_session):
    """Empty sessions should return zero counts."""
    consolidator = ConsolidationEngine(db_session)

    result = await consolidator.consolidate_session(
        session_id="empty-sess",
        branch_name="main",
    )

    assert result["observations_processed"] == 0
    assert result["facts_created"] == 0


@pytest.mark.asyncio
async def test_session_consolidation_with_task(db_session, mock_embedder):
    """Consolidation with task/agent context should tag created facts."""
    obs_engine = ObservationEngine(db_session, mock_embedder)
    consolidator = ConsolidationEngine(db_session)

    await obs_engine.write_observation(
        session_id="task-sess",
        observation_type="discovery",
        summary="Found a SQL injection vulnerability in the login endpoint",
    )

    result = await consolidator.consolidate_session(
        session_id="task-sess",
        branch_name="main",
        task_id="task-123",
        agent_id="security-scanner",
    )

    assert result["facts_created"] == 1


@pytest.mark.asyncio
async def test_agent_consolidation(db_session, mock_embedder):
    """Agent consolidation should deduplicate facts across sessions."""
    task_engine = TaskEngine(db_session)
    fact_engine = FactEngine(db_session, mock_embedder)
    consolidator = ConsolidationEngine(db_session)

    task = await task_engine.create_task(name="Agent Consolidation Test")
    join_result = await task_engine.join_task(
        task_id=task.id, agent_id="dedup-agent"
    )
    agent_branch = join_result["agent_branch"]

    # Write duplicate facts on agent branch (Jaccard similarity must be > 0.85)
    await fact_engine.write_fact(
        fact_text="The API uses cursor based pagination for listing resources efficiently",
        branch_name=agent_branch,
    )
    await fact_engine.write_fact(
        fact_text="The API uses cursor based pagination for listing resources",
        branch_name=agent_branch,
    )

    result = await consolidator.consolidate_agent(
        task_id=task.id, agent_id="dedup-agent"
    )

    assert result["facts_deduplicated"] >= 1
    assert "summary" in result


@pytest.mark.asyncio
async def test_agent_consolidation_nonexistent(db_session):
    """Consolidating a nonexistent agent should raise ConsolidationError."""
    consolidator = ConsolidationEngine(db_session)

    with pytest.raises(ConsolidationError):
        await consolidator.consolidate_agent(
            task_id="no-task", agent_id="no-agent"
        )


@pytest.mark.asyncio
async def test_task_consolidation_classifies(db_session, mock_embedder):
    """Task consolidation should classify facts as durable vs ephemeral."""
    task_engine = TaskEngine(db_session)
    fact_engine = FactEngine(db_session, mock_embedder)
    consolidator = ConsolidationEngine(db_session)

    task = await task_engine.create_task(name="Classify Test")

    # Durable fact (high confidence + durable category)
    await fact_engine.write_fact(
        fact_text="Fixed race condition in connection pool",
        category="bug_fix",
        confidence=0.9,
        branch_name=task.branch_name,
    )

    # Ephemeral fact (low confidence)
    await fact_engine.write_fact(
        fact_text="Tried using library X but it didn't work",
        category="insight",
        confidence=0.5,
        branch_name=task.branch_name,
    )

    # Ephemeral fact (non-durable category despite high confidence)
    await fact_engine.write_fact(
        fact_text="Interesting code pattern observed",
        category="discovery",
        confidence=0.9,
        branch_name=task.branch_name,
    )

    result = await consolidator.consolidate_task(task_id=task.id)

    assert len(result["durable_fact_ids"]) == 1  # Only bug_fix with high confidence
    assert result["ephemeral_count"] == 2


@pytest.mark.asyncio
async def test_deduplicate_facts(db_session, mock_embedder):
    """Direct dedup test with clearly duplicate facts."""
    fact_engine = FactEngine(db_session, mock_embedder)
    consolidator = ConsolidationEngine(db_session)

    branch_mgr = BranchManager(db_session)
    await branch_mgr.create_branch("dedup-test", "main")

    await fact_engine.write_fact(
        fact_text="The database schema uses normalized tables for user data",
        branch_name="dedup-test",
        confidence=0.6,
    )
    await fact_engine.write_fact(
        fact_text="The database schema uses normalized tables for user data storage",
        branch_name="dedup-test",
        confidence=0.8,
    )
    await fact_engine.write_fact(
        fact_text="Completely different fact about API design",
        branch_name="dedup-test",
        confidence=0.7,
    )

    count = await consolidator._deduplicate_facts("dedup-test")

    # The two similar facts should be deduped, keeping the higher-confidence one
    assert count == 1


# --- Unit tests for helper functions ---


def test_jaccard_similarity_identical():
    assert _jaccard_similarity("hello world", "hello world") == 1.0


def test_jaccard_similarity_different():
    sim = _jaccard_similarity(
        "the cat sat on the mat",
        "completely unrelated sentence about python"
    )
    assert sim < 0.2


def test_jaccard_similarity_partial_overlap():
    sim = _jaccard_similarity(
        "the project uses JWT tokens for authentication",
        "the project uses JWT tokens for auth and authorization"
    )
    assert 0.3 < sim < 0.9


def test_jaccard_similarity_empty():
    assert _jaccard_similarity("", "something") == 0.0
    assert _jaccard_similarity("something", "") == 0.0


def test_tokenize():
    tokens = _tokenize("Hello, World! This is a test.")
    assert "hello" in tokens
    assert "world" in tokens
    assert "test" in tokens
    # Single-char tokens are excluded
    assert "a" not in tokens


def test_infer_category_decision():
    assert _infer_category("decision", "anything") == "decision"


def test_infer_category_discovery():
    assert _infer_category("discovery", "anything") == "discovery"


def test_infer_category_bug():
    assert _infer_category("insight", "Fixed the authentication bug") == "bug_fix"


def test_infer_category_architecture():
    assert _infer_category("insight", "The architecture uses microservices") == "architecture"


def test_infer_category_security():
    assert _infer_category("insight", "Found a security vulnerability") == "security"


def test_infer_category_default():
    assert _infer_category("insight", "Some general observation") == "insight"
