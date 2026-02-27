"""MCP tool definitions and handlers — 8 tools, NL-first."""

from __future__ import annotations

from collections.abc import Callable

from mcp.types import Tool
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.memory_engine import MemoryEngine

TOOL_DEFINITIONS: list[Tool] = [
    Tool(
        name="memory_write",
        description=(
            "Store a memory. text = what happened (NL). "
            "context = why / how / outcome (NL, freeform). "
            "file_context = relevant file path."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "What happened (natural language)"},
                "context": {"type": "string", "description": "Why / how / outcome (natural language)"},
                "file_context": {"type": "string", "description": "Relevant file path (optional)"},
                "session_id": {"type": "string", "description": "Session or agent identifier"},
                "branch": {"type": "string", "description": "Target branch (default: active branch)"},
            },
            "required": ["text"],
        },
    ),
    Tool(
        name="memory_search",
        description="Search memories with natural language. Returns relevant memories from the active branch.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query"},
                "file_context": {"type": "string", "description": "Filter by file path"},
                "branch": {"type": "string", "description": "Branch to search"},
                "limit": {"type": "integer", "description": "Max results (default: 10)"},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="memory_branch_create",
        description="Create a new memory branch for isolated experimentation.",
        inputSchema={
            "type": "object",
            "properties": {
                "branch_name": {"type": "string", "description": "New branch name"},
                "parent": {"type": "string", "description": "Parent branch (default: main)"},
                "description": {"type": "string", "description": "Branch purpose"},
            },
            "required": ["branch_name"],
        },
    ),
    Tool(
        name="memory_branch_switch",
        description="Switch the active memory branch for this session.",
        inputSchema={
            "type": "object",
            "properties": {
                "branch_name": {"type": "string", "description": "Branch to switch to"},
            },
            "required": ["branch_name"],
        },
    ),
    Tool(
        name="memory_branch_list",
        description="List available memory branches.",
        inputSchema={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["active", "archived"], "description": "Filter by status"},
            },
        },
    ),
    Tool(
        name="memory_snapshot",
        description="Create a point-in-time snapshot of the current branch (before risky changes).",
        inputSchema={
            "type": "object",
            "properties": {
                "label": {"type": "string", "description": "Snapshot label"},
                "branch": {"type": "string", "description": "Branch to snapshot (default: active)"},
            },
        },
    ),
    Tool(
        name="memory_snapshot_list",
        description="List snapshots for a branch.",
        inputSchema={
            "type": "object",
            "properties": {
                "branch": {"type": "string", "description": "Filter by branch"},
            },
        },
    ),
    Tool(
        name="memory_restore",
        description="Restore memories to a snapshot point in time.",
        inputSchema={
            "type": "object",
            "properties": {
                "snapshot_id": {"type": "string", "description": "Snapshot ID to restore"},
            },
            "required": ["snapshot_id"],
        },
    ),
]


async def handle_tool_call(
    name: str,
    arguments: dict,
    session: AsyncSession,
    get_active_branch: Callable[[], str],
    set_active_branch: Callable[[str], None],
) -> dict:
    branch = arguments.get("branch") or get_active_branch()
    engine = MemoryEngine(session)

    if name == "memory_write":
        mem = await engine.write(
            text=arguments["text"],
            context=arguments.get("context"),
            file_context=arguments.get("file_context"),
            session_id=arguments.get("session_id"),
            branch_name=branch,
        )
        return {"id": mem.id, "created_at": mem.created_at}

    elif name == "memory_search":
        results = await engine.search(
            query=arguments["query"],
            file_context=arguments.get("file_context"),
            branch_name=branch,
            limit=arguments.get("limit", 10),
        )
        return {"results": results, "count": len(results)}

    elif name == "memory_branch_create":
        b = await engine.create_branch(
            branch_name=arguments["branch_name"],
            parent_branch=arguments.get("parent", "main"),
            description=arguments.get("description"),
        )
        return {"branch_name": b.branch_name, "parent_branch": b.parent_branch, "created_at": b.created_at}

    elif name == "memory_branch_switch":
        await engine.get_branch(arguments["branch_name"])  # verify exists
        set_active_branch(arguments["branch_name"])
        return {"active_branch": arguments["branch_name"]}

    elif name == "memory_branch_list":
        branches = await engine.list_branches(status=arguments.get("status"))
        return {
            "branches": [
                {
                    "branch_name": b.branch_name,
                    "parent_branch": b.parent_branch,
                    "status": b.status,
                    "description": b.description,
                    "created_at": b.created_at.isoformat() if b.created_at else None,
                }
                for b in branches
            ]
        }

    elif name == "memory_snapshot":
        snap = await engine.create_snapshot(branch_name=branch, label=arguments.get("label"))
        return {"snapshot_id": snap.id, "label": snap.label, "created_at": snap.created_at}

    elif name == "memory_snapshot_list":
        snaps = await engine.list_snapshots(branch_name=arguments.get("branch"))
        return {
            "snapshots": [
                {
                    "id": s.id,
                    "label": s.label,
                    "branch_name": s.branch_name,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                }
                for s in snaps
            ]
        }

    elif name == "memory_restore":
        return await engine.restore_snapshot(arguments["snapshot_id"])

    else:
        return {"error": f"Unknown tool: {name}"}
