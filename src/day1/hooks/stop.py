"""Stop hook: generate interim summary after each agent response.

Invoked when Claude Code finishes a response turn.
Generates a brief summary of what was accomplished.
"""

from __future__ import annotations

from day1.core.embedding import get_embedding_provider
from day1.core.observation_engine import ObservationEngine
from day1.hooks.base import (
    get_db_session,
    get_session_id,
    run_hook,
)


async def handler(input_data: dict) -> dict:
    """Generate interim summary of the current response."""
    async with get_db_session() as session:
        if session is None:
            return {}

        embedder = get_embedding_provider()
        obs_engine = ObservationEngine(session, embedder)

        # Extract summary from the response
        response = input_data.get("response", "")
        if not response:
            return {}

        # For MVP: create a simple summary observation
        summary = _summarize_response(response)
        if summary:
            await obs_engine.write_observation(
                session_id=get_session_id(),
                observation_type="insight",
                summary=summary,
            )

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


if __name__ == "__main__":
    run_hook(handler)
