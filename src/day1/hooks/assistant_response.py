"""Stop hook (assistant capture): capture assistant response messages.

Invoked when Claude finishes a response turn.
Stores the assistant's final message in the conversation history layer.

Core principle: Message capture is critical, external services (embedding) are optional.
"""

from __future__ import annotations

import os

from day1.core.conversation_engine import ConversationEngine
from day1.core.embedding import get_embedding_provider
from day1.core.message_engine import MessageEngine
from day1.hooks.base import (
    _debug_log,
    get_db_session,
    get_session_id,
    run_hook,
)


async def handler(input_data: dict) -> dict:
    """Capture assistant response as a message in conversation history."""
    message = input_data.get("last_assistant_message", "")
    if not message:
        return {}

    sid = get_session_id()
    _debug_log(f"[assistant_response] session_id={sid}, content_len={len(message)}")

    async with get_db_session() as session:
        if session is None:
            _debug_log("[assistant_response] ERROR: No DB session!")
            return {}

        agent_id = os.environ.get("BM_AGENT_ID")

        # Find active conversation for this session
        conv_engine = ConversationEngine(session)
        conv = await conv_engine.get_conversation_by_session(sid)
        if conv is None:
            conv = await conv_engine.create_conversation(
                session_id=sid,
                agent_id=agent_id,
                task_id=os.environ.get("BM_TASK_ID"),
            )
            _debug_log(f"[assistant_response] Created conversation {conv.id}")

        embedder = get_embedding_provider()
        msg_engine = MessageEngine(session, embedder)

        try:
            msg = await msg_engine.write_message(
                conversation_id=conv.id,
                role="assistant",
                content=message,
                session_id=sid,
                agent_id=agent_id,
                branch_name=conv.branch_name,
                embed=False,  # Disable embedding to avoid external service dependency
            )
            _debug_log(f"[assistant_response] Wrote message {msg.id}")
        except Exception as e:
            _debug_log(f"[assistant_response] ERROR: {e}")
            # Still try to write without any external dependencies
            try:
                msg = await msg_engine.write_message(
                    conversation_id=conv.id,
                    role="assistant",
                    content=message,
                    session_id=sid,
                    agent_id=agent_id,
                    branch_name=conv.branch_name,
                    embed=False,
                )
                _debug_log(f"[assistant_response] Wrote message (fallback) {msg.id}")
            except Exception as e2:
                _debug_log(f"[assistant_response] Fallback also failed: {e2}")

    return {}


if __name__ == "__main__":
    run_hook(handler)
