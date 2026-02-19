"""UserPromptSubmit hook: capture user messages and inject memory context.

Invoked before Claude processes each user message.
Stores the user message in the conversation history layer,
then optionally injects relevant memory as additional context.
"""

from __future__ import annotations

import asyncio
import os

from branchedmind.core.conversation_engine import ConversationEngine
from branchedmind.core.embedding import get_embedding_provider
from branchedmind.core.message_engine import MessageEngine
from branchedmind.core.search_engine import SearchEngine
from branchedmind.hooks.base import (
    get_db_session,
    get_session_id,
    read_hook_input,
    write_hook_output,
)


async def handler(input_data: dict) -> dict:
    """Capture user message and inject relevant memory context."""
    prompt = input_data.get("prompt", "")
    if not prompt:
        return {}

    session = await get_db_session()
    if session is None:
        return {}

    sid = get_session_id()
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

    # Store the user message
    embedder = get_embedding_provider()
    msg_engine = MessageEngine(session, embedder)
    await msg_engine.write_message(
        conversation_id=conv.id,
        role="user",
        content=prompt,
        session_id=sid,
        agent_id=agent_id,
        branch_name=conv.branch_name,
    )

    # Search memory for relevant context to inject
    search_engine = SearchEngine(session, embedder)
    results = await search_engine.search(
        query=prompt,
        branch_name=conv.branch_name,
        limit=5,
    )

    await session.close()

    if results:
        context_lines = ["## Relevant Memory"]
        for r in results:
            cat = f"[{r['category']}]" if r.get("category") else ""
            context_lines.append(f"- {r['fact_text'][:200]} {cat}")

        return {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": "\n".join(context_lines),
            }
        }

    return {}


def main() -> None:
    input_data = read_hook_input()
    result = asyncio.run(handler(input_data))
    write_hook_output(result)


if __name__ == "__main__":
    main()
