"""Tests for KnowledgeBundleEngine."""

from __future__ import annotations

import pytest

from day1.core.branch_manager import BranchManager
from day1.core.embedding import MockEmbedding
from day1.core.exceptions import KnowledgeBundleError
from day1.core.fact_engine import FactEngine
from day1.core.knowledge_bundle_engine import KnowledgeBundleEngine
from day1.core.verification_engine import VerificationEngine
from day1.db.models import Conversation, Fact, Message, Relation


@pytest.mark.asyncio
async def test_create_bundle_basic(db_session):
    """Create a knowledge bundle from a branch."""
    embedder = MockEmbedding(dims=64)
    fact_engine = FactEngine(db_session, embedder)

    await fact_engine.write_fact(
        fact_text="PostgreSQL JSONB is more efficient than JSON for querying",
        category="architecture",
        confidence=0.9,
        branch_name="main",
    )

    # Verify the fact so it gets included
    verifier = VerificationEngine(db_session)
    from sqlalchemy import select
    result = await db_session.execute(select(Fact).where(Fact.branch_name == "main"))
    fact = result.scalars().first()
    await verifier.verify_fact(fact.id)

    engine = KnowledgeBundleEngine(db_session)
    bundle = await engine.create_bundle(
        name="test-bundle",
        source_branch="main",
        description="Test knowledge bundle",
        tags=["test", "architecture"],
    )

    assert bundle["name"] == "test-bundle"
    assert bundle["description"] == "Test knowledge bundle"
    assert bundle["tags"] == ["test", "architecture"]
    assert bundle["source_branch"] == "main"


@pytest.mark.asyncio
async def test_create_bundle_only_verified(db_session):
    """Bundle with only_verified=True excludes unverified facts."""
    embedder = MockEmbedding(dims=64)
    fact_engine = FactEngine(db_session, embedder)

    await fact_engine.write_fact(
        fact_text="Unverified fact about Redis",
        category="architecture",
        confidence=0.9,
        branch_name="main",
    )

    engine = KnowledgeBundleEngine(db_session)
    bundle = await engine.create_bundle(
        name="verified-only",
        source_branch="main",
        only_verified=True,
    )

    # No verified facts, so bundle should have 0 facts
    assert bundle["fact_count"] == 0


@pytest.mark.asyncio
async def test_create_bundle_with_all_facts(db_session):
    """Bundle with only_verified=False includes all active facts."""
    embedder = MockEmbedding(dims=64)
    fact_engine = FactEngine(db_session, embedder)

    await fact_engine.write_fact(
        fact_text="Fact about microservices architecture",
        category="architecture",
        confidence=0.9,
        branch_name="main",
    )
    await fact_engine.write_fact(
        fact_text="Fact about database indexing strategies",
        category="pattern",
        confidence=0.8,
        branch_name="main",
    )

    engine = KnowledgeBundleEngine(db_session)
    bundle = await engine.create_bundle(
        name="all-facts",
        source_branch="main",
        only_verified=False,
    )

    assert bundle["fact_count"] == 2


@pytest.mark.asyncio
async def test_import_bundle_facts(db_session):
    """Import bundle creates facts on target branch."""
    embedder = MockEmbedding(dims=64)
    fact_engine = FactEngine(db_session, embedder)

    await fact_engine.write_fact(
        fact_text="GraphQL enables flexible API queries with a single endpoint",
        category="architecture",
        confidence=0.9,
        branch_name="main",
    )

    engine = KnowledgeBundleEngine(db_session)
    bundle = await engine.create_bundle(
        name="importable",
        source_branch="main",
        only_verified=False,
    )

    # Create target branch
    mgr = BranchManager(db_session)
    await mgr.create_branch("target", parent_branch="main")

    # Import
    result = await engine.import_bundle(
        bundle_id=bundle["id"],
        target_branch="target",
    )

    assert result["facts_imported"] == 1
    assert result["target_branch"] == "target"
    assert result["bundle_name"] == "importable"


@pytest.mark.asyncio
async def test_import_bundle_conversations(db_session):
    """Import bundle creates conversations and messages."""
    # Create a conversation with messages
    conv = Conversation(
        branch_name="main",
        title="Test conversation",
        status="active",
        message_count=2,
    )
    db_session.add(conv)
    await db_session.flush()

    msg1 = Message(
        conversation_id=conv.id,
        role="user",
        content="Hello",
        sequence_num=1,
        branch_name="main",
    )
    msg2 = Message(
        conversation_id=conv.id,
        role="assistant",
        content="Hi there!",
        sequence_num=2,
        branch_name="main",
    )
    db_session.add_all([msg1, msg2])
    await db_session.commit()

    engine = KnowledgeBundleEngine(db_session)
    bundle = await engine.create_bundle(
        name="conv-bundle",
        source_branch="main",
        only_verified=False,
    )

    assert bundle["conversation_count"] == 1

    # Import
    result = await engine.import_bundle(
        bundle_id=bundle["id"],
        target_branch="main",
    )

    assert result["conversations_imported"] == 1
    assert result["messages_imported"] == 2


@pytest.mark.asyncio
async def test_import_bundle_relations(db_session):
    """Import bundle creates relations on target branch."""
    rel = Relation(
        source_entity="AuthService",
        target_entity="JWTProvider",
        relation_type="depends_on",
        branch_name="main",
    )
    db_session.add(rel)
    await db_session.commit()

    engine = KnowledgeBundleEngine(db_session)
    bundle = await engine.create_bundle(
        name="rel-bundle",
        source_branch="main",
        only_verified=False,
    )

    assert bundle["relation_count"] == 1

    result = await engine.import_bundle(
        bundle_id=bundle["id"],
        target_branch="main",
    )

    assert result["relations_imported"] == 1


@pytest.mark.asyncio
async def test_import_bundle_not_found(db_session):
    """Import nonexistent bundle raises KnowledgeBundleError."""
    engine = KnowledgeBundleEngine(db_session)
    with pytest.raises(KnowledgeBundleError):
        await engine.import_bundle(
            bundle_id="nonexistent",
            target_branch="main",
        )


@pytest.mark.asyncio
async def test_get_bundle(db_session):
    """Get bundle details."""
    engine = KnowledgeBundleEngine(db_session)
    bundle = await engine.create_bundle(
        name="detail-bundle",
        source_branch="main",
        description="A test bundle",
        tags=["test"],
        only_verified=False,
    )

    details = await engine.get_bundle(bundle["id"])

    assert details["name"] == "detail-bundle"
    assert details["description"] == "A test bundle"
    assert details["tags"] == ["test"]
    assert details["status"] == "active"


@pytest.mark.asyncio
async def test_get_bundle_not_found(db_session):
    """Get nonexistent bundle raises KnowledgeBundleError."""
    engine = KnowledgeBundleEngine(db_session)
    with pytest.raises(KnowledgeBundleError):
        await engine.get_bundle("nonexistent")


@pytest.mark.asyncio
async def test_export_bundle(db_session):
    """Export bundle includes full bundle_data."""
    embedder = MockEmbedding(dims=64)
    fact_engine = FactEngine(db_session, embedder)

    await fact_engine.write_fact(
        fact_text="Event sourcing stores state changes as immutable events",
        category="architecture",
        confidence=0.9,
        branch_name="main",
    )

    engine = KnowledgeBundleEngine(db_session)
    bundle = await engine.create_bundle(
        name="export-bundle",
        source_branch="main",
        only_verified=False,
    )

    exported = await engine.export_bundle(bundle["id"])

    assert "bundle_data" in exported
    assert len(exported["bundle_data"]["facts"]) == 1
    assert exported["bundle_data"]["facts"][0]["fact_text"] == (
        "Event sourcing stores state changes as immutable events"
    )


@pytest.mark.asyncio
async def test_list_bundles(db_session):
    """List bundles with filters."""
    engine = KnowledgeBundleEngine(db_session)

    await engine.create_bundle(
        name="bundle-a",
        source_branch="main",
        tags=["auth"],
        only_verified=False,
    )
    await engine.create_bundle(
        name="bundle-b",
        source_branch="main",
        tags=["database"],
        only_verified=False,
    )

    bundles = await engine.list_bundles()
    assert len(bundles) == 2

    # Filter by tags
    filtered = await engine.list_bundles(tags=["auth"])
    assert len(filtered) == 1
    assert filtered[0]["name"] == "bundle-a"


@pytest.mark.asyncio
async def test_import_bundle_selective(db_session):
    """Import bundle with selective import options."""
    embedder = MockEmbedding(dims=64)
    fact_engine = FactEngine(db_session, embedder)

    await fact_engine.write_fact(
        fact_text="WebSockets enable real-time bidirectional communication",
        category="pattern",
        confidence=0.9,
        branch_name="main",
    )

    engine = KnowledgeBundleEngine(db_session)
    bundle = await engine.create_bundle(
        name="selective-bundle",
        source_branch="main",
        only_verified=False,
    )

    # Import only facts, not conversations or relations
    result = await engine.import_bundle(
        bundle_id=bundle["id"],
        target_branch="main",
        import_facts=True,
        import_conversations=False,
        import_relations=False,
    )

    assert result["facts_imported"] == 1
    assert result["conversations_imported"] == 0
    assert result["relations_imported"] == 0
