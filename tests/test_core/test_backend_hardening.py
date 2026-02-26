"""Backend hardening tests for S0: rollback safety and archive locking."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from day1.core.branch_manager import BranchManager
from day1.core.branch_topology_engine import BranchTopologyEngine
from day1.core.conversation_cherry_pick import ConversationCherryPick
from day1.core.conversation_engine import ConversationEngine
from day1.core.embedding import MockEmbedding
from day1.core.fact_engine import FactEngine
from day1.core.message_engine import MessageEngine
from day1.db.models import BranchRegistry, Conversation, Fact


class _NoopAutocommitConn:
    async def execute(self, *_args, **_kwargs):
        return None


@asynccontextmanager
async def _noop_autocommit():
    yield _NoopAutocommitConn()


async def _install_write_spies_and_fail_commit(db_session, monkeypatch):
    """Patch commit to fail and record rollback/close calls."""
    calls = {"rollback": 0, "close": 0}

    orig_commit = db_session.commit
    orig_rollback = db_session.rollback
    orig_close = db_session.close

    async def rollback_spy():
        calls["rollback"] += 1
        return await orig_rollback()

    async def close_spy():
        calls["close"] += 1
        return await orig_close()

    async def fail_commit():
        raise RuntimeError("forced commit failure")

    monkeypatch.setattr(db_session, "rollback", rollback_spy)
    monkeypatch.setattr(db_session, "close", close_spy)
    monkeypatch.setattr(db_session, "commit", fail_commit)
    return calls, orig_commit


async def _create_conversation_with_messages(
    db_session: AsyncSession,
    mock_embedder: MockEmbedding,
) -> str:
    conv_engine = ConversationEngine(db_session)
    msg_engine = MessageEngine(db_session, mock_embedder)
    conv = await conv_engine.create_conversation(
        session_id="hardening-session",
        title="Hardening source",
    )
    await msg_engine.write_message(
        conversation_id=conv.id,
        role="user",
        content="hello",
        session_id="hardening-session",
        embed=False,
    )
    await msg_engine.write_message(
        conversation_id=conv.id,
        role="assistant",
        content="world",
        session_id="hardening-session",
        embed=False,
    )
    return conv.id


@pytest.mark.asyncio
async def test_branch_manager_ensure_main_branch_rolls_back_on_commit_error(
    db_session,
    monkeypatch,
):
    await db_session.execute(
        delete(BranchRegistry).where(BranchRegistry.branch_name == "main")
    )
    await db_session.commit()

    mgr = BranchManager(db_session)
    calls, orig_commit = await _install_write_spies_and_fail_commit(
        db_session, monkeypatch
    )

    with pytest.raises(RuntimeError, match="forced commit failure"):
        await mgr.ensure_main_branch()

    monkeypatch.setattr(db_session, "commit", orig_commit)

    main_count = await db_session.scalar(
        select(func.count(BranchRegistry.branch_name)).where(
            BranchRegistry.branch_name == "main"
        )
    )
    assert main_count == 0
    assert calls["rollback"] >= 1
    assert calls["close"] >= 1


@pytest.mark.asyncio
async def test_branch_manager_create_branch_rolls_back_on_commit_error(
    db_session,
    monkeypatch,
):
    mgr = BranchManager(db_session)
    monkeypatch.setattr(mgr, "_get_autocommit_conn", _noop_autocommit)
    calls, orig_commit = await _install_write_spies_and_fail_commit(
        db_session, monkeypatch
    )

    with pytest.raises(RuntimeError, match="forced commit failure"):
        await mgr.create_branch("rollback-create")

    monkeypatch.setattr(db_session, "commit", orig_commit)

    created = await db_session.scalar(
        select(func.count(BranchRegistry.branch_name)).where(
            BranchRegistry.branch_name == "rollback-create"
        )
    )
    assert created == 0
    assert calls["rollback"] >= 1
    assert calls["close"] >= 1


@pytest.mark.asyncio
async def test_branch_manager_merge_branch_rolls_back_on_commit_error(
    db_session,
    monkeypatch,
):
    mgr = BranchManager(db_session)
    await mgr.create_branch("rollback-merge")
    monkeypatch.setattr(mgr, "_get_autocommit_conn", _noop_autocommit)
    calls, orig_commit = await _install_write_spies_and_fail_commit(
        db_session, monkeypatch
    )

    with pytest.raises(RuntimeError, match="forced commit failure"):
        await mgr.merge_branch_native("rollback-merge", "main")

    monkeypatch.setattr(db_session, "commit", orig_commit)

    status = await db_session.scalar(
        select(BranchRegistry.status).where(
            BranchRegistry.branch_name == "rollback-merge"
        )
    )
    assert status == "active"
    assert calls["rollback"] >= 1
    assert calls["close"] >= 1


@pytest.mark.asyncio
async def test_branch_manager_archive_branch_rolls_back_on_commit_error(
    db_session,
    monkeypatch,
):
    mgr = BranchManager(db_session)
    await mgr.create_branch("rollback-archive")
    monkeypatch.setattr(mgr, "_get_autocommit_conn", _noop_autocommit)
    calls, orig_commit = await _install_write_spies_and_fail_commit(
        db_session, monkeypatch
    )

    with pytest.raises(RuntimeError, match="forced commit failure"):
        await mgr.archive_branch("rollback-archive")

    monkeypatch.setattr(db_session, "commit", orig_commit)

    status = await db_session.scalar(
        select(BranchRegistry.status).where(
            BranchRegistry.branch_name == "rollback-archive"
        )
    )
    assert status == "active"
    assert calls["rollback"] >= 1
    assert calls["close"] >= 1


@pytest.mark.asyncio
async def test_branch_topology_enrich_rolls_back_on_commit_error(
    db_session,
    monkeypatch,
):
    engine = BranchTopologyEngine(db_session)
    calls, orig_commit = await _install_write_spies_and_fail_commit(
        db_session, monkeypatch
    )

    with pytest.raises(RuntimeError, match="forced commit failure"):
        await engine.enrich_branch_metadata(branch_name="main", owner="alice")

    monkeypatch.setattr(db_session, "commit", orig_commit)

    branch = await db_session.scalar(
        select(BranchRegistry).where(BranchRegistry.branch_name == "main")
    )
    assert (branch.metadata_json or {}).get("owner") is None
    assert calls["rollback"] >= 1
    assert calls["close"] >= 1


@pytest.mark.asyncio
async def test_branch_topology_apply_auto_archive_rolls_back_when_archive_step_fails(
    db_session,
    monkeypatch,
):
    mgr = BranchManager(db_session)
    await mgr.create_branch("rollback-auto-archive")
    await db_session.execute(
        update(BranchRegistry)
        .where(BranchRegistry.branch_name == "rollback-auto-archive")
        .values(status="merged")
    )
    await db_session.commit()

    engine = BranchTopologyEngine(db_session)
    calls = {"rollback": 0, "close": 0}
    orig_rollback = db_session.rollback
    orig_close = db_session.close

    async def rollback_spy():
        calls["rollback"] += 1
        return await orig_rollback()

    async def close_spy():
        calls["close"] += 1
        return await orig_close()

    async def fail_archive(_branch_name: str):
        raise RuntimeError("forced archive failure")

    monkeypatch.setattr(db_session, "rollback", rollback_spy)
    monkeypatch.setattr(db_session, "close", close_spy)
    monkeypatch.setattr(engine, "_archive_candidate_with_lock", fail_archive)

    result = await engine.apply_auto_archive()

    status = await db_session.scalar(
        select(BranchRegistry.status).where(
            BranchRegistry.branch_name == "rollback-auto-archive"
        )
    )
    assert status == "merged"
    assert result["archived"] == 0
    assert calls["rollback"] >= 1
    assert calls["close"] >= 1


@pytest.mark.asyncio
async def test_conversation_cherry_pick_conversation_rolls_back_on_commit_error(
    db_session,
    mock_embedder,
    monkeypatch,
):
    conv_id = await _create_conversation_with_messages(db_session, mock_embedder)
    picker = ConversationCherryPick(db_session)
    calls, orig_commit = await _install_write_spies_and_fail_commit(
        db_session, monkeypatch
    )

    with pytest.raises(RuntimeError, match="forced commit failure"):
        await picker.cherry_pick_conversation(conv_id, "main", include_messages=False)

    monkeypatch.setattr(db_session, "commit", orig_commit)

    copied_count = await db_session.scalar(
        select(func.count(Conversation.id)).where(
            Conversation.parent_conversation_id == conv_id
        )
    )
    assert copied_count == 0
    assert calls["rollback"] >= 1
    assert calls["close"] >= 1


@pytest.mark.asyncio
async def test_conversation_cherry_pick_range_rolls_back_on_commit_error(
    db_session,
    mock_embedder,
    monkeypatch,
):
    conv_id = await _create_conversation_with_messages(db_session, mock_embedder)
    picker = ConversationCherryPick(db_session)
    calls, orig_commit = await _install_write_spies_and_fail_commit(
        db_session, monkeypatch
    )

    with pytest.raises(RuntimeError, match="forced commit failure"):
        await picker.cherry_pick_message_range(
            conversation_id=conv_id,
            from_sequence=1,
            to_sequence=2,
            target_branch="main",
        )

    monkeypatch.setattr(db_session, "commit", orig_commit)

    copied_count = await db_session.scalar(
        select(func.count(Conversation.id)).where(
            Conversation.parent_conversation_id == conv_id
        )
    )
    assert copied_count == 0
    assert calls["rollback"] >= 1
    assert calls["close"] >= 1


@pytest.mark.asyncio
async def test_conversation_cherry_pick_curated_branch_rolls_back_on_commit_error(
    db_session,
    mock_embedder,
    monkeypatch,
):
    fact_engine = FactEngine(db_session, mock_embedder)
    fact = await fact_engine.write_fact(
        fact_text="rollback fact source",
        branch_name="main",
    )
    picker = ConversationCherryPick(db_session)

    async def noop_create_branch(self, **_kwargs):
        return None

    monkeypatch.setattr(BranchManager, "create_branch", noop_create_branch)
    calls, orig_commit = await _install_write_spies_and_fail_commit(
        db_session, monkeypatch
    )

    with pytest.raises(RuntimeError, match="forced commit failure"):
        await picker.cherry_pick_to_curated_branch(
            branch_name="curated-rollback",
            fact_ids=[fact.id],
        )

    monkeypatch.setattr(db_session, "commit", orig_commit)

    copied_facts = await db_session.scalar(
        select(func.count(Fact.id)).where(Fact.branch_name == "curated-rollback")
    )
    assert copied_facts == 0
    assert calls["rollback"] >= 1
    assert calls["close"] >= 1


@pytest.mark.asyncio
async def test_auto_archive_lock_prevents_duplicate_archive_under_concurrency(
    db_session,
    monkeypatch,
):
    mgr = BranchManager(db_session)
    await mgr.create_branch("task/lock-test")
    await db_session.execute(
        update(BranchRegistry)
        .where(BranchRegistry.branch_name == "task/lock-test")
        .values(status="merged")
    )
    await db_session.commit()

    orig_archive = BranchManager.archive_branch

    async def delayed_archive(self, branch_name: str):
        await asyncio.sleep(0.1)
        return await orig_archive(self, branch_name)

    monkeypatch.setattr(BranchManager, "archive_branch", delayed_archive)

    session_factory = async_sessionmaker(
        db_session.bind, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as s1, session_factory() as s2:
        e1 = BranchTopologyEngine(s1)
        e2 = BranchTopologyEngine(s2)
        r1, r2 = await asyncio.gather(
            e1.apply_auto_archive(archive_merged=True),
            e2.apply_auto_archive(archive_merged=True),
        )

    final_status = await db_session.scalar(
        select(BranchRegistry.status).where(
            BranchRegistry.branch_name == "task/lock-test"
        )
    )
    assert (r1["archived"] + r2["archived"]) == 1
    assert final_status == "archived"

