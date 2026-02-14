"""SessionStart hook: inject relevant historical memory into context.

Invoked when a Claude Code session begins.
Returns additional context to be injected into the system prompt.
"""

from __future__ import annotations

import asyncio
import os

from branchedmind.core.branch_manager import BranchManager
from branchedmind.core.embedding import get_embedding_provider
from branchedmind.core.exceptions import DatabaseError, TaskNotFoundError
from branchedmind.core.fact_engine import FactEngine
from branchedmind.core.session_manager import SessionManager
from branchedmind.core.task_engine import TaskEngine
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

    # Check for task/agent context from environment
    task_id = os.environ.get("BM_TASK_ID")
    agent_id = os.environ.get("BM_AGENT_ID")

    # Register this session
    sid = get_session_id()
    existing = await session_mgr.get_session(sid)
    if existing is None:
        await session_mgr.create_session(
            session_id=sid,
            branch_name="main",
            project_path=get_project_path(),
            task_id=task_id,
            agent_id=agent_id,
        )

    context_parts: list[str] = []

    # Task-aware context injection
    if task_id:
        try:
            task_engine = TaskEngine(session)
            task_context = await task_engine.get_task_context(task_id)

            context_parts.append("## Task Context")
            task_info = task_context["task"]
            context_parts.append(f"**Task**: {task_info['name']}")
            if task_info.get("description"):
                context_parts.append(f"**Description**: {task_info['description']}")
            if task_info.get("task_type"):
                context_parts.append(f"**Type**: {task_info['task_type']}")

            # Objectives with status
            if task_info.get("objectives"):
                context_parts.append("\n### Objectives")
                status_icons = {
                    "done": "[DONE]",
                    "active": "[ACTIVE]",
                    "todo": "[TODO]",
                    "blocked": "[BLOCKED]",
                }
                for obj in task_info["objectives"]:
                    icon = status_icons.get(obj.get("status", "todo"), "")
                    agent_note = (
                        f" (by {obj['agent_id']})"
                        if obj.get("agent_id") and obj["status"] == "done"
                        else ""
                    )
                    context_parts.append(f"- {icon} {obj['description']}{agent_note}")

            # Previous agent work
            if task_context.get("agent_summaries"):
                context_parts.append("\n### Previous Agent Work")
                for s in task_context["agent_summaries"]:
                    context_parts.append(
                        f"- **{s['agent_id']}** ({s.get('role', 'agent')}): "
                        f"{s['summary'][:300]}"
                    )

            # Key facts from task
            if task_context.get("key_facts"):
                context_parts.append("\n### Key Task Facts")
                for f in task_context["key_facts"][:10]:
                    cat = f"[{f['category']}]" if f.get("category") else ""
                    context_parts.append(f"- {f['fact_text']} {cat}")

            # Progress
            progress = task_context.get("progress", {})
            if progress.get("total", 0) > 0:
                context_parts.append(
                    f"\n**Progress**: {progress.get('done', 0)}/{progress['total']} "
                    f"done, {progress.get('active', 0)} active, "
                    f"{progress.get('todo', 0)} remaining"
                )

        except (TaskNotFoundError, DatabaseError):
            pass  # Graceful degradation if task not found

    else:
        # Standard context (no task): recent facts + sessions
        facts = await fact_engine.list_facts(branch_name="main", limit=15)
        if facts:
            context_parts.append("## Project Memory (Key Facts)")
            for f in facts:
                cat = f"[{f.category}]" if f.category else ""
                context_parts.append(f"- {f.fact_text} {cat}")

        recent_sessions = await session_mgr.get_recent_sessions(limit=3)
        completed = [s for s in recent_sessions if s.summary]
        if completed:
            context_parts.append("\n## Recent Session Summaries")
            for s in completed:
                ts = s.started_at.isoformat() if s.started_at else "unknown"
                summary = (s.summary or "No summary")[:200]
                context_parts.append(f"- {ts}: {summary}")

    # Active branches (always shown)
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
