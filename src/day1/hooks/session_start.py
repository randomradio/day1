"""SessionStart hook: inject relevant historical memory into context.

Invoked when a Claude Code session begins.
Returns additional context to be injected into the system prompt.
"""

from __future__ import annotations

import os

from day1.core.branch_manager import BranchManager
from day1.core.conversation_engine import ConversationEngine
from day1.core.embedding import get_embedding_provider
from day1.core.exceptions import DatabaseError, TaskNotFoundError
from day1.core.fact_engine import FactEngine
from day1.core.session_manager import SessionManager
from day1.core.task_engine import TaskEngine
from day1.hooks.base import (
    get_db_session,
    get_project_path,
    get_session_id,
    run_hook,
)


async def handler() -> dict:
    """Inject relevant historical memory at session start."""
    async with get_db_session() as session:
        if session is None:
            return {}

        embedder = get_embedding_provider()
        fact_engine = FactEngine(session, embedder)
        session_mgr = SessionManager(session)
        branch_mgr = BranchManager(session)

    # Check for task/agent context from environment
    task_id = os.environ.get("BM_TASK_ID")
    agent_id = os.environ.get("BM_AGENT_ID")
    active_branch = os.environ.get("BM_BRANCH") or "main"

    # Register this session (link to parent if BM_PARENT_SESSION is set)
    sid = get_session_id()
    parent_session = os.environ.get("BM_PARENT_SESSION")

    existing = await session_mgr.get_session(sid)
    if existing is None:
        await session_mgr.create_session(
            session_id=sid,
            branch_name=active_branch,
            project_path=get_project_path(),
            parent_session=parent_session,
            task_id=task_id,
            agent_id=agent_id,
        )

    # Create a conversation for this session (Layer 1: History)
    conv_engine = ConversationEngine(session)
    existing_conv = await conv_engine.get_conversation_by_session(sid)
    if existing_conv is None:
        await conv_engine.create_conversation(
            session_id=sid,
            agent_id=agent_id,
            task_id=task_id,
            branch_name=active_branch,
        )

    context_parts: list[str] = []

    # Parent session context handoff
    if parent_session:
        try:
            parent_ctx = await session_mgr.get_session_context(
                parent_session, message_limit=30, fact_limit=15
            )
            if "error" not in parent_ctx:
                context_parts.append("## Continuing from Previous Session")
                ps = parent_ctx["session"]
                if ps.get("summary"):
                    context_parts.append(f"**Summary**: {ps['summary'][:500]}")

                # Include recent conversation messages
                for conv in parent_ctx.get("conversations", [])[:2]:
                    title = conv.get("title") or "Untitled"
                    context_parts.append(
                        f"\n### Conversation: {title} "
                        f"({conv.get('message_count', 0)} messages)"
                    )
                    for msg in conv.get("messages", [])[-15:]:
                        role = msg["role"].upper()
                        content = (msg.get("content") or "")[:300]
                        if content:
                            context_parts.append(f"- **{role}**: {content}")

                # Include facts from parent session
                parent_facts = parent_ctx.get("facts", [])
                if parent_facts:
                    context_parts.append("\n### Key Facts from Previous Session")
                    for pf in parent_facts[:10]:
                        cat = f"[{pf.get('category', '')}]" if pf.get("category") else ""
                        context_parts.append(f"- {pf['fact_text'][:200]} {cat}")

                # Observation summary
                obs_sum = parent_ctx.get("observations_summary", {})
                if obs_sum.get("total"):
                    tools = ", ".join(obs_sum.get("tools_used", [])[:10])
                    context_parts.append(
                        f"\n**Previous session**: {obs_sum['total']} observations, "
                        f"tools used: {tools}"
                    )
        except (DatabaseError,):
            pass  # Graceful degradation

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
        facts = await fact_engine.list_facts(branch_name=active_branch, limit=15)
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

    # Recent conversations on the active branch
    recent_convs = await conv_engine.list_conversations(
        branch_name=active_branch, limit=3
    )
    if recent_convs:
        context_parts.append(f"\n## Recent Conversations on '{active_branch}'")
        for c in recent_convs:
            title = c.title or "Untitled"
            context_parts.append(f"- {title} ({c.message_count} messages)")

    # Active branches (always shown)
    branches = await branch_mgr.list_branches(status="active")
    non_main = [b for b in branches if b.branch_name != "main"]
    if non_main:
        context_parts.append("\n## Active Memory Branches")
        for b in non_main:
            desc = b.description or "No description"
            context_parts.append(f"- {b.branch_name}: {desc}")

    if not context_parts:
        return {}

    return {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "\n".join(context_parts),
        }
    }


if __name__ == "__main__":
    run_hook(handler, takes_input=False)
