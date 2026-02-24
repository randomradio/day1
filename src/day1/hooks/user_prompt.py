"""UserPromptSubmit hook: capture user messages.

Invoked before Claude processes each user message.
Stores the user message in the conversation history layer.

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
    """Capture user message to conversation history."""
    prompt = input_data.get("prompt", "")
    if not prompt:
        return {}

    sid = get_session_id()
    _debug_log(f"[user_prompt] session_id={sid}, prompt='{prompt[:50]}...'")

    async with get_db_session() as session:
        if session is None:
            _debug_log("[user_prompt] ERROR: No DB session!")
            return {}

        agent_id = os.environ.get("BM_AGENT_ID")

        # Ensure there's an active conversation for this session
        conv_engine = ConversationEngine(session)
        conv = await conv_engine.get_conversation_by_session(sid)
        if conv is None:
            conv = await conv_engine.create_conversation(
                session_id=sid,
                agent_id=agent_id,
                task_id=os.environ.get("BM_TASK_ID"),
                title=prompt[:100],
            )
            _debug_log(f"[user_prompt] Created conversation {conv.id}")

        # Store the user message (no embedding - core capture only)
        embedder = get_embedding_provider()
        msg_engine = MessageEngine(session, embedder)

        try:
            msg = await msg_engine.write_message(
                conversation_id=conv.id,
                role="user",
                content=prompt,
                session_id=sid,
                agent_id=agent_id,
                branch_name=conv.branch_name,
                embed=False,  # No embedding - external service dependency
            )
            _debug_log(f"[user_prompt] Wrote message {msg.id}")
        except Exception as e:
            _debug_log(f"[user_prompt] ERROR: {e}")
            # Try once more with minimal dependencies
            try:
                msg = await msg_engine.write_message(
                    conversation_id=conv.id,
                    role="user",
                    content=prompt,
                    session_id=sid,
                    agent_id=agent_id,
                    branch_name=conv.branch_name,
                    embed=False,
                )
                _debug_log(f"[user_prompt] Wrote message (fallback) {msg.id}")
            except Exception as e2:
                _debug_log(f"[user_prompt] Fallback failed: {e2}")

    return {}  # No context injection - that's SessionStart's job


if __name__ == "__main__":
    run_hook(handler)
