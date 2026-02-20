"""SessionEnd hook: generate final session summary and consolidate.

Invoked when a Claude Code session ends.
Creates a comprehensive summary, triggers consolidation if in a task context,
and marks the session as completed.
"""

from __future__ import annotations

import os

from day1.core.consolidation_engine import ConsolidationEngine
from day1.core.embedding import get_embedding_provider
from day1.core.exceptions import ConsolidationError, DatabaseError
from day1.core.observation_engine import ObservationEngine
from day1.core.session_manager import SessionManager
from day1.hooks.base import (
    get_db_session,
    get_session_id,
    run_hook,
)


async def handler(input_data: dict) -> dict:
    """Generate final summary, consolidate, and close session."""
    session = await get_db_session()
    if session is None:
        return {}

    embedder = get_embedding_provider()
    obs_engine = ObservationEngine(session, embedder)
    session_mgr = SessionManager(session)

    sid = get_session_id()
    task_id = os.environ.get("BM_TASK_ID")
    agent_id = os.environ.get("BM_AGENT_ID")

    # Gather all observations from this session for summary
    observations = await obs_engine.list_observations(session_id=sid, limit=100)

    # Generate summary from observations
    summary = _generate_session_summary(observations)

    # Write final summary observation
    if summary:
        await obs_engine.write_observation(
            session_id=sid,
            observation_type="insight",
            summary=f"Session summary: {summary}",
            task_id=task_id,
            agent_id=agent_id,
        )

    # Trigger session-level consolidation if in a task context
    if task_id:
        try:
            consolidator = ConsolidationEngine(session)
            sess_record = await session_mgr.get_session(sid)
            branch = sess_record.branch_name if sess_record else "main"
            await consolidator.consolidate_session(
                session_id=sid,
                branch_name=branch,
                task_id=task_id,
                agent_id=agent_id,
            )
        except (ConsolidationError, DatabaseError):
            pass  # Graceful degradation

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


if __name__ == "__main__":
    run_hook(handler)
