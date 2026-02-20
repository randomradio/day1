"""Stop hook (assistant capture): capture assistant response messages.

Invoked when Claude finishes a response turn.
Stores the assistant's final message in the conversation history layer.
"""

from __future__ import annotations

import os

from day1.core.conversation_engine import ConversationEngine
from day1.core.embedding import get_embedding_provider
from day1.core.message_engine import MessageEngine
from day1.hooks.base import (
    get_db_session,
    get_session_id,
    run_hook,
)


async def handler(input_data: dict) -> dict:
    """Capture assistant response as a message in conversation history."""
    # Prevent infinite loops: if Stop hook already active, bail out
    if input_data.get("stop_hook_active"):
        return {}

    message = input_data.get("last_assistant_message", "")
    if not message:
        return {}

    session = await get_db_session()
    if session is None:
        return {}

    sid = get_session_id()
    agent_id = os.environ.get("BM_AGENT_ID")

    # Find active conversation for this session
    conv_engine = ConversationEngine(session)
    conv = await conv_engine.get_conversation_by_session(sid)
    if conv is None:
        # No conversation yet — create one
        conv = await conv_engine.create_conversation(
            session_id=sid,
            agent_id=agent_id,
            task_id=os.environ.get("BM_TASK_ID"),
        )

    embedder = get_embedding_provider()
    msg_engine = MessageEngine(session, embedder)

    await msg_engine.write_message(
        conversation_id=conv.id,
        role="assistant",
        content=message,
        session_id=sid,
        agent_id=agent_id,
        branch_name=conv.branch_name,
    )

    await session.close()
    return {}


if __name__ == "__main__":
    run_hook(handler)
