"""Tests for ConversationCherryPick transactional safety."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from day1.core.branch_manager import BranchManager
from day1.core.conversation_cherry_pick import ConversationCherryPick
from day1.core.conversation_engine import ConversationEngine
from day1.core.message_engine import MessageEngine
from day1.db.models import Conversation


async def _seed_conversation(
    db_session,
    mock_embedder,
    session_id: str = "cherry-session",
    branch_name: str = "main",
) -> str:
    conv_engine = ConversationEngine(db_session)
    msg_engine = MessageEngine(db_session, mock_embedder)

    conv = await conv_engine.create_conversation(
        session_id=session_id,
        title="Cherry Source",
        branch_name=branch_name,
    )
    messages = [
        {"role": "user", "content": "Start cherry pick"},
        {"role": "assistant", "content": "Working on it"},
        {"role": "user", "content": "Great!"},
        {"role": "assistant", "content": "Done"},
    ]
    for msg in messages:
        await msg_engine.write_message(
            conversation_id=conv.id,
            role=msg["role"],
            content=msg["content"],
            session_id=session_id,
            branch_name=branch_name,
            embed=False,
        )
    return conv.id


@pytest.mark.asyncio
async def test_cherry_pick_conversation_rolls_back_on_failure(
    db_session,
    mock_embedder,
    monkeypatch,
):
    """Failed message copy should roll back new conversation creation."""
    source_conv = await _seed_conversation(db_session, mock_embedder)
    mgr = BranchManager(db_session)
    await mgr.create_branch("task/curated", tables=[])

    cherry = ConversationCherryPick(db_session)

    async def failing_copy_messages(self, *args, **kwargs):
        raise RuntimeError("copy failed")

    monkeypatch.setattr(
        ConversationCherryPick,
        "_copy_messages",
        failing_copy_messages,
    )

    with pytest.raises(RuntimeError):
        await cherry.cherry_pick_conversation(
            conversation_id=source_conv,
            target_branch="task/curated",
        )

    # No conversations should exist on target branch after rollback
    count = await db_session.scalar(
        select(func.count(Conversation.id)).where(
            Conversation.branch_name == "task/curated"
        )
    )
    assert count == 0
