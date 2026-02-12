"""SessionStart hook: inject relevant historical memory into context.

Invoked when a Claude Code session begins.
Returns additional context to be injected into the system prompt.
"""

from __future__ import annotations

import asyncio

from branchedmind.core.branch_manager import BranchManager
from branchedmind.core.embedding import get_embedding_provider
from branchedmind.core.fact_engine import FactEngine
from branchedmind.core.session_manager import SessionManager
from branchedmind.hooks.base import (
    get_db_session,
    get_project_path,
    get_session_id,
    read_hook_input,
    write_hook_output,
)


async def handler() -> dict:
    """Inject relevant historical memory at session start."""
    session = await get_db_session()
    if session is None:
        return {}

    embedder = get_embedding_provider()
    fact_engine = FactEngine(session, embedder)
    session_mgr = SessionManager(session)
    branch_mgr = BranchManager(session)

    # Register this session
    sid = get_session_id()
    existing = await session_mgr.get_session(sid)
    if existing is None:
        await session_mgr.create_session(
            session_id=sid,
            branch_name="main",
            project_path=get_project_path(),
        )

    context_parts: list[str] = []

    # 1. Recent key facts (top 15 by recency)
    facts = await fact_engine.list_facts(branch_name="main", limit=15)
    if facts:
        context_parts.append("## Project Memory (Key Facts)")
        for f in facts:
            cat = f"[{f.category}]" if f.category else ""
            context_parts.append(f"- {f.fact_text} {cat}")

    # 2. Recent session summaries
    recent_sessions = await session_mgr.get_recent_sessions(limit=3)
    completed = [s for s in recent_sessions if s.summary]
    if completed:
        context_parts.append("\n## Recent Session Summaries")
        for s in completed:
            ts = s.started_at.isoformat() if s.started_at else "unknown"
            summary = (s.summary or "No summary")[:200]
            context_parts.append(f"- {ts}: {summary}")

    # 3. Active branches
    branches = await branch_mgr.list_branches(status="active")
    non_main = [b for b in branches if b.branch_name != "main"]
    if non_main:
        context_parts.append("\n## Active Memory Branches")
        for b in non_main:
            desc = b.description or "No description"
            context_parts.append(f"- {b.branch_name}: {desc}")

    await session.close()

    if not context_parts:
        return {}

    return {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "\n".join(context_parts),
        }
    }


def main() -> None:
    _input = read_hook_input()
    result = asyncio.run(handler())
    write_hook_output(result)


if __name__ == "__main__":
    main()
