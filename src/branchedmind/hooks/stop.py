"""Stop hook: generate interim summary after each agent response.

Invoked when Claude Code finishes a response turn.
Generates a brief summary of what was accomplished.
"""

from __future__ import annotations

import asyncio

from branchedmind.core.embedding import get_embedding_provider
from branchedmind.core.observation_engine import ObservationEngine
from branchedmind.hooks.base import (
    get_db_session,
    get_session_id,
    read_hook_input,
    write_hook_output,
)


async def handler(input_data: dict) -> dict:
    """Generate interim summary of the current response."""
    session = await get_db_session()
    if session is None:
        return {}

    embedder = get_embedding_provider()
    obs_engine = ObservationEngine(session, embedder)

    # Extract summary from the response
    response = input_data.get("response", "")
    if not response:
        await session.close()
        return {}

    # For MVP: create a simple summary observation
    summary = _summarize_response(response)
    if summary:
        await obs_engine.write_observation(
            session_id=get_session_id(),
            observation_type="insight",
            summary=summary,
        )

    await session.close()
    return {}


def _summarize_response(response: str) -> str:
    """Create a brief summary of a response.

    For MVP: take first meaningful paragraph.
    Production would use LLM for intelligent summarization.
    """
    lines = [line.strip() for line in response.split("\n") if line.strip()]
    # Skip very short lines (headers, bullets, etc.)
    content_lines = [line for line in lines if len(line) > 30]
    if content_lines:
        return content_lines[0][:500]
    return ""


def main() -> None:
    input_data = read_hook_input()
    result = asyncio.run(handler(input_data))
    write_hook_output(result)


if __name__ == "__main__":
    main()
