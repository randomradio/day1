"""PostToolUse hook: capture tool call observations asynchronously.

Invoked after each tool call in Claude Code.
Compresses the observation and stores it in memory,
including task and agent context when available.
"""

from __future__ import annotations

import asyncio
import os

from branchedmind.core.embedding import get_embedding_provider
from branchedmind.core.observation_engine import ObservationEngine
from branchedmind.hooks.base import (
    get_db_session,
    get_session_id,
    read_hook_input,
    write_hook_output,
)


async def handler(input_data: dict) -> dict:
    """Capture and store tool call observation."""
    session = await get_db_session()
    if session is None:
        return {"async": True}

    embedder = get_embedding_provider()
    obs_engine = ObservationEngine(session, embedder)

    tool_name = input_data.get("tool_name", "unknown")
    tool_input = input_data.get("tool_input", "")
    tool_response = input_data.get("tool_response", "")

    # Read task/agent context from environment
    task_id = os.environ.get("BM_TASK_ID")
    agent_id = os.environ.get("BM_AGENT_ID")

    # Compress observation: extract key information
    summary = _compress_observation(tool_name, tool_input, tool_response)

    await obs_engine.write_observation(
        session_id=get_session_id(),
        observation_type="tool_use",
        tool_name=tool_name,
        summary=summary,
        raw_input=str(tool_input)[:2000],
        raw_output=str(tool_response)[:2000],
        task_id=task_id,
        agent_id=agent_id,
    )

    await session.close()
    return {"async": True, "asyncTimeout": 10000}


def _compress_observation(
    tool_name: str, tool_input: str | dict, tool_response: str | dict
) -> str:
    """Compress a tool observation into a concise summary.

    For MVP, uses simple heuristic compression.
    Production version would use LLM for intelligent compression.
    """
    input_str = str(tool_input)[:500] if tool_input else ""
    output_str = str(tool_response)[:500] if tool_response else ""

    if tool_name == "Bash":
        return f"Executed command: {input_str[:200]}. Result: {output_str[:200]}"
    elif tool_name == "Read":
        return f"Read file: {input_str[:200]}"
    elif tool_name in ("Edit", "Write"):
        return f"Modified file: {input_str[:200]}"
    elif tool_name == "Grep":
        return f"Searched for: {input_str[:200]}. Found: {output_str[:200]}"
    else:
        return f"Used {tool_name}: {input_str[:150]}. Result: {output_str[:150]}"


def main() -> None:
    input_data = read_hook_input()
    result = asyncio.run(handler(input_data))
    write_hook_output(result)


if __name__ == "__main__":
    main()
