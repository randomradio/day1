"""PreToolUse hook: capture tool call intent before execution.

Invoked before each tool call in Claude Code.
Stores the tool call intent as a message in conversation history,
allowing full replay of what the agent intended to do.
"""

from __future__ import annotations

import asyncio
import os

from branchedmind.core.conversation_engine import ConversationEngine
from branchedmind.core.embedding import get_embedding_provider
from branchedmind.core.message_engine import MessageEngine
from branchedmind.hooks.base import (
    get_db_session,
    get_session_id,
    read_hook_input,
    write_hook_output,
)


async def handler(input_data: dict) -> dict:
    """Capture tool call intent as a message."""
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    if not tool_name:
        return {}

    session = await get_db_session()
    if session is None:
        return {}

    sid = get_session_id()
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
    input_str = str(tool_input)[:2000]
    await msg_engine.write_message(
        conversation_id=conv.id,
        role="tool_call",
        content=f"Calling {tool_name}",
        tool_calls=[{"name": tool_name, "input": input_str}],
        session_id=sid,
        agent_id=agent_id,
        branch_name=conv.branch_name,
        embed=False,  # Tool calls don't need embeddings
    )

    await session.close()
    return {}  # Allow tool to proceed normally


def main() -> None:
    input_data = read_hook_input()
    result = asyncio.run(handler(input_data))
    write_hook_output(result)


if __name__ == "__main__":
    main()
