"""Tests for FactEngine."""

from __future__ import annotations

import pytest

from day1.core.embedding import MockEmbedding
from day1.core.exceptions import FactNotFoundError
from day1.core.fact_engine import FactEngine


@pytest.mark.asyncio
async def test_write_and_get_fact(db_session, mock_embedder):
    engine = FactEngine(db_session, mock_embedder)

    fact = await engine.write_fact(
        fact_text="The project uses FastAPI for the REST API",
        category="architecture",
        confidence=0.95,
    )

    assert fact.id is not None
    assert fact.fact_text == "The project uses FastAPI for the REST API"
    assert fact.category == "architecture"
    assert fact.confidence == 0.95
    assert fact.status == "active"
    assert fact.branch_name == "main"

    # Retrieve it
    retrieved = await engine.get_fact(fact.id)
    assert retrieved.fact_text == fact.fact_text


@pytest.mark.asyncio
async def test_get_nonexistent_fact(db_session, mock_embedder):
    engine = FactEngine(db_session, mock_embedder)
    with pytest.raises(FactNotFoundError):
        await engine.get_fact("nonexistent-id")


@pytest.mark.asyncio
async def test_update_fact(db_session, mock_embedder):
    engine = FactEngine(db_session, mock_embedder)

    fact = await engine.write_fact(
        fact_text="Initial fact text",
        category="general",
    )

    updated = await engine.update_fact(
        fact.id,
        fact_text="Updated fact text",
        confidence=0.8,
    )

    assert updated.fact_text == "Updated fact text"
    assert updated.confidence == 0.8


@pytest.mark.asyncio
async def test_list_facts_by_branch(db_session, mock_embedder):
    engine = FactEngine(db_session, mock_embedder)

    await engine.write_fact(fact_text="Fact on main", branch_name="main")
    await engine.write_fact(fact_text="Fact on dev", branch_name="dev")

    main_facts = await engine.list_facts(branch_name="main")
    assert len(main_facts) == 1
    assert main_facts[0].fact_text == "Fact on main"


@pytest.mark.asyncio
async def test_list_facts_by_category(db_session, mock_embedder):
    engine = FactEngine(db_session, mock_embedder)

    await engine.write_fact(fact_text="Bug related", category="bug_fix")
    await engine.write_fact(fact_text="Arch related", category="architecture")

    bugs = await engine.list_facts(category="bug_fix")
    assert len(bugs) == 1
    assert bugs[0].category == "bug_fix"


@pytest.mark.asyncio
async def test_supersede_fact(db_session, mock_embedder):
    engine = FactEngine(db_session, mock_embedder)

    old = await engine.write_fact(fact_text="Old version of truth")
    new = await engine.supersede_fact(old.id, "New version of truth")

    assert new.parent_id == old.id
    old_refreshed = await engine.get_fact(old.id)
    assert old_refreshed.status == "superseded"
