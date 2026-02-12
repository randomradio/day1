"""SessionEnd hook: generate final session summary.

Invoked when a Claude Code session ends.
Creates a comprehensive summary and marks the session as completed.
"""

from __future__ import annotations

import asyncio

from branchedmind.core.embedding import get_embedding_provider
from branchedmind.core.observation_engine import ObservationEngine
from branchedmind.core.session_manager import SessionManager
from branchedmind.hooks.base import (
    get_db_session,
    get_session_id,
    read_hook_input,
    write_hook_output,
)


async def handler(input_data: dict) -> dict:
    """Generate final summary and close session."""
    session = await get_db_session()
    if session is None:
        return {}

    embedder = get_embedding_provider()
    obs_engine = ObservationEngine(session, embedder)
    session_mgr = SessionManager(session)

    sid = get_session_id()

    # Gather all observations from this session for summary
    observations = await obs_engine.list_observations(
        session_id=sid, limit=100
    )

    # Generate summary from observations
    summary = _generate_session_summary(observations)

    # Write final summary observation
    if summary:
        await obs_engine.write_observation(
            session_id=sid,
            observation_type="insight",
            summary=f"Session summary: {summary}",
        )

    # Mark session as completed
    await session_mgr.end_session(session_id=sid, summary=summary)

    await session.close()
    return {}


def _generate_session_summary(observations: list) -> str:
    """Generate a session summary from observations.

    For MVP: concatenate key observations.
    Production would use LLM for intelligent summarization.
    """
    if not observations:
        return "No significant observations recorded."

    # Group by type
    tool_uses = [o for o in observations if o.observation_type == "tool_use"]
    insights = [o for o in observations if o.observation_type == "insight"]
    errors = [o for o in observations if o.observation_type == "error"]

    parts = []
    if tool_uses:
        parts.append(f"Performed {len(tool_uses)} tool operations")
    if insights:
        parts.append(f"Generated {len(insights)} insights")
    if errors:
        parts.append(f"Encountered {len(errors)} errors")

    # Add most recent insight as context
    if insights:
        parts.append(f"Last insight: {insights[0].summary[:200]}")

    return ". ".join(parts) + "." if parts else "Session completed."


def main() -> None:
    input_data = read_hook_input()
    result = asyncio.run(handler(input_data))
    write_hook_output(result)


if __name__ == "__main__":
    main()
