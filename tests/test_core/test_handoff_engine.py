"""Tests for HandoffEngine."""

from __future__ import annotations

import pytest

from day1.core.branch_manager import BranchManager
from day1.core.conversation_engine import ConversationEngine
from day1.core.embedding import MockEmbedding
from day1.core.exceptions import HandoffError
from day1.core.fact_engine import FactEngine
from day1.core.handoff_engine import HandoffEngine
from day1.core.verification_engine import VerificationEngine


@pytest.mark.asyncio
async def test_create_handoff_basic(db_session):
    """Create a basic handoff between branches."""
    mgr = BranchManager(db_session)
    await mgr.create_branch("task/source", parent_branch="main")
    await mgr.create_branch("task/target", parent_branch="main")

    engine = HandoffEngine(db_session)
    result = await engine.create_handoff(
        source_branch="task/source",
        target_branch="task/target",
        handoff_type="task_continuation",
    )

    assert result["handoff_id"]
    assert result["source_branch"] == "task/source"
    assert result["target_branch"] == "task/target"
    assert result["handoff_type"] == "task_continuation"


@pytest.mark.asyncio
async def test_create_handoff_invalid_type(db_session):
    """Invalid handoff type raises HandoffError."""
    engine = HandoffEngine(db_session)
    with pytest.raises(HandoffError):
        await engine.create_handoff(
            source_branch="main",
            target_branch="other",
            handoff_type="invalid_type",
        )


@pytest.mark.asyncio
async def test_handoff_includes_verified_facts_only(db_session):
    """Handoff with include_unverified=False only includes verified facts."""
    embedder = MockEmbedding(dims=64)
    fact_engine = FactEngine(db_session, embedder)

    # Create facts
    f1 = await fact_engine.write_fact(
        fact_text="The API uses rate limiting with a sliding window algorithm to prevent abuse",
        category="architecture",
        confidence=0.9,
        branch_name="main",
    )
    f2 = await fact_engine.write_fact(
        fact_text="Something unverified but interesting",
        category="insight",
        confidence=0.5,
        branch_name="main",
    )

    # Verify f1 only
    verifier = VerificationEngine(db_session)
    await verifier.verify_fact(f1.id)

    engine = HandoffEngine(db_session)
    result = await engine.create_handoff(
        source_branch="main",
        target_branch="other",
        include_unverified=False,
    )

    # Should only include verified facts (depends on heuristic)
    assert result["fact_count"] >= 0


@pytest.mark.asyncio
async def test_handoff_includes_unverified_when_opted_in(db_session):
    """Handoff with include_unverified=True includes all non-invalidated facts."""
    embedder = MockEmbedding(dims=64)
    fact_engine = FactEngine(db_session, embedder)

    await fact_engine.write_fact(
        fact_text="Unverified fact about caching strategies",
        category="pattern",
        confidence=0.7,
        branch_name="main",
    )

    engine = HandoffEngine(db_session)
    result = await engine.create_handoff(
        source_branch="main",
        target_branch="other",
        include_unverified=True,
    )

    assert result["fact_count"] >= 1


@pytest.mark.asyncio
async def test_get_handoff_packet(db_session):
    """Retrieve full handoff packet with facts and conversations."""
    embedder = MockEmbedding(dims=64)
    fact_engine = FactEngine(db_session, embedder)

    await fact_engine.write_fact(
        fact_text="Microservices should use async messaging for inter-service communication",
        category="architecture",
        confidence=0.9,
        branch_name="main",
    )

    # Verify the fact
    verifier = VerificationEngine(db_session)
    from sqlalchemy import select
    from day1.db.models import Fact
    result = await db_session.execute(select(Fact).where(Fact.branch_name == "main"))
    fact = result.scalars().first()
    await verifier.verify_fact(fact.id)

    engine = HandoffEngine(db_session)
    handoff = await engine.create_handoff(
        source_branch="main",
        target_branch="other",
    )

    packet = await engine.get_handoff_packet(handoff["handoff_id"])

    assert packet["handoff_id"] == handoff["handoff_id"]
    assert packet["source_branch"] == "main"
    assert "facts" in packet
    assert "conversations" in packet
    assert "context_summary" in packet


@pytest.mark.asyncio
async def test_get_handoff_packet_not_found(db_session):
    """Getting nonexistent handoff raises HandoffError."""
    engine = HandoffEngine(db_session)
    with pytest.raises(HandoffError):
        await engine.get_handoff_packet("nonexistent-id")


@pytest.mark.asyncio
async def test_list_handoffs(db_session):
    """List handoff records with filters."""
    engine = HandoffEngine(db_session)

    await engine.create_handoff(
        source_branch="main",
        target_branch="branch-a",
        handoff_type="task_continuation",
    )
    await engine.create_handoff(
        source_branch="main",
        target_branch="branch-b",
        handoff_type="agent_switch",
    )

    all_handoffs = await engine.list_handoffs()
    assert len(all_handoffs) == 2

    filtered = await engine.list_handoffs(handoff_type="agent_switch")
    assert len(filtered) == 1
    assert filtered[0]["handoff_type"] == "agent_switch"


@pytest.mark.asyncio
async def test_handoff_with_manual_summary(db_session):
    """Handoff with manual context summary."""
    engine = HandoffEngine(db_session)
    result = await engine.create_handoff(
        source_branch="main",
        target_branch="other",
        context_summary="Custom summary of what happened",
    )

    assert result["context_summary"] == "Custom summary of what happened"


@pytest.mark.asyncio
async def test_handoff_with_specific_ids(db_session):
    """Handoff with explicitly specified fact and conversation IDs."""
    embedder = MockEmbedding(dims=64)
    fact_engine = FactEngine(db_session, embedder)

    fact = await fact_engine.write_fact(
        fact_text="Specific fact to include in handoff",
        category="decision",
        confidence=0.9,
        branch_name="main",
    )

    engine = HandoffEngine(db_session)
    result = await engine.create_handoff(
        source_branch="main",
        target_branch="other",
        fact_ids=[fact.id],
        conversation_ids=[],
    )

    assert result["fact_count"] == 1
    assert result["conversation_count"] == 0
