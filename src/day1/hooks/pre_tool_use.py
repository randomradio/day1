"""PreToolUse hook: capture tool call intent before execution.

Invoked before each tool call in Claude Code.
Stores the tool call intent as a message in conversation history,
allowing full replay of what the agent intended to do.
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
    """Capture tool call intent as a message."""
    tool_name = input_data.get("tool_name", "")
    if not tool_name:
        return {}

    sid = get_session_id()
    _debug_log(f"[pre_tool_use] session_id={sid}, tool={tool_name}")

    async with get_db_session() as session:
        if session is None:
            _debug_log("[pre_tool_use] ERROR: No DB session!")
            return {}

        agent_id = os.environ.get("BM_AGENT_ID")

        # Find active conversation
        conv_engine = ConversationEngine(session)
        conv = await conv_engine.get_conversation_by_session(sid)
        if conv is None:
            conv = await conv_engine.create_conversation(
                session_id=sid,
                agent_id=agent_id,
                task_id=os.environ.get("BM_TASK_ID"),
            )

        embedder = get_embedding_provider()
        msg_engine = MessageEngine(session, embedder)

        # Store as tool_call message with structured data
        tool_input = input_data.get("tool_input", {})
        input_str = str(tool_input)[:2000]
        await msg_engine.write_message(
            conversation_id=conv.id,
            role="tool_call",
            content=f"Calling {tool_name}",
            tool_calls=[{"name": tool_name, "input": input_str}],
            session_id=sid,
            agent_id=agent_id,
            branch_name=conv.branch_name,
            embed=False,
        )

    return {}  # Allow tool to proceed normally


if __name__ == "__main__":
    run_hook(handler)
