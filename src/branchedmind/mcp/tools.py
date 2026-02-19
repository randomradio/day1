"""MCP tool definitions and handlers for all memory_* tools."""

from __future__ import annotations

from collections.abc import Callable

from mcp.types import Tool
from sqlalchemy.ext.asyncio import AsyncSession

from branchedmind.core.branch_manager import BranchManager
from branchedmind.core.consolidation_engine import ConsolidationEngine
from branchedmind.core.conversation_engine import ConversationEngine
from branchedmind.core.embedding import get_embedding_provider
from branchedmind.core.fact_engine import FactEngine
from branchedmind.core.merge_engine import MergeEngine
from branchedmind.core.message_engine import MessageEngine
from branchedmind.core.observation_engine import ObservationEngine
from branchedmind.core.relation_engine import RelationEngine
from branchedmind.core.search_engine import SearchEngine
from branchedmind.core.snapshot_manager import SnapshotManager
from branchedmind.core.task_engine import TaskEngine

# ---- Tool Definitions ----

TOOL_DEFINITIONS: list[Tool] = [
    # === Memory Write ===
    Tool(
        name="memory_write_fact",
        description=(
            "Store a structured fact in memory." " Facts are the core knowledge units."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "fact_text": {
                    "type": "string",
                    "description": "Natural language description of the fact",
                },
                "category": {
                    "type": "string",
                    "description": (
                        "Category: bug_fix, architecture,"
                        " preference, pattern, decision, etc."
                    ),
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence score 0.0-1.0 (default 1.0)",
                },
                "branch": {
                    "type": "string",
                    "description": "Target branch (default: current active branch)",
                },
            },
            "required": ["fact_text"],
        },
    ),
    Tool(
        name="memory_write_observation",
        description=(
            "Store a tool call observation record."
            " Captures what happened during tool use."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "observation_type": {
                    "type": "string",
                    "description": (
                        "Type: tool_use, discovery," " decision, error, insight"
                    ),
                },
                "summary": {
                    "type": "string",
                    "description": "Compressed observation summary",
                },
                "tool_name": {
                    "type": "string",
                    "description": "Tool that was used (Bash, Edit, Read, etc.)",
                },
                "raw_input": {"type": "string", "description": "Truncated raw input"},
                "raw_output": {
                    "type": "string",
                    "description": "Truncated raw output",
                },
                "session_id": {
                    "type": "string",
                    "description": "Session ID (auto-detected if not provided)",
                },
                "branch": {"type": "string", "description": "Target branch"},
            },
            "required": ["observation_type", "summary"],
        },
    ),
    Tool(
        name="memory_write_relation",
        description="Store an entity relationship in the knowledge graph.",
        inputSchema={
            "type": "object",
            "properties": {
                "source_entity": {
                    "type": "string",
                    "description": "Source entity name",
                },
                "target_entity": {
                    "type": "string",
                    "description": "Target entity name",
                },
                "relation_type": {
                    "type": "string",
                    "description": (
                        "Relation type: depends_on," " causes, fixes, implements, etc."
                    ),
                },
                "properties": {
                    "type": "object",
                    "description": "Additional relation metadata",
                },
                "branch": {"type": "string", "description": "Target branch"},
            },
            "required": ["source_entity", "target_entity", "relation_type"],
        },
    ),
    # === Search ===
    Tool(
        name="memory_search",
        description=(
            "Search memory using hybrid BM25 + vector search."
            " Returns facts matching your query."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query",
                },
                "search_type": {
                    "type": "string",
                    "enum": ["hybrid", "vector", "keyword"],
                    "description": "Search mode (default: hybrid)",
                },
                "category": {"type": "string", "description": "Filter by category"},
                "branch": {"type": "string", "description": "Branch to search"},
                "limit": {
                    "type": "integer",
                    "description": "Max results (default: 10)",
                },
                "time_range": {
                    "type": "object",
                    "properties": {
                        "after": {
                            "type": "string",
                            "description": "ISO timestamp lower bound",
                        },
                        "before": {
                            "type": "string",
                            "description": "ISO timestamp upper bound",
                        },
                    },
                    "description": "Time range filter",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="memory_graph_query",
        description=(
            "Query the entity relationship graph." " Find all connections to an entity."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "entity": {
                    "type": "string",
                    "description": "Entity name to query",
                },
                "relation_type": {
                    "type": "string",
                    "description": "Filter by relation type",
                },
                "depth": {
                    "type": "integer",
                    "description": "Traversal depth (default: 1)",
                },
                "branch": {"type": "string", "description": "Branch to query"},
            },
            "required": ["entity"],
        },
    ),
    Tool(
        name="memory_timeline",
        description="Get chronological memory timeline of facts and observations.",
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Filter by session",
                },
                "branch": {"type": "string", "description": "Branch name"},
                "after": {"type": "string", "description": "ISO timestamp start"},
                "before": {"type": "string", "description": "ISO timestamp end"},
                "limit": {
                    "type": "integer",
                    "description": "Max results (default: 50)",
                },
            },
        },
    ),
    # === Branch Operations ===
    Tool(
        name="memory_branch_create",
        description=(
            "Create a new memory branch (fork from parent)."
            " Isolated workspace for experiments or agents."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "branch_name": {
                    "type": "string",
                    "description": "New branch name",
                },
                "parent_branch": {
                    "type": "string",
                    "description": "Parent branch to fork from (default: main)",
                },
                "description": {
                    "type": "string",
                    "description": "Branch description/purpose",
                },
            },
            "required": ["branch_name"],
        },
    ),
    Tool(
        name="memory_branch_list",
        description="List all memory branches with their status.",
        inputSchema={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["active", "merged", "archived"],
                    "description": "Filter by status",
                },
            },
        },
    ),
    Tool(
        name="memory_branch_switch",
        description=(
            "Switch the active branch. All subsequent"
            " operations will use this branch."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "branch_name": {
                    "type": "string",
                    "description": "Branch to switch to",
                },
            },
            "required": ["branch_name"],
        },
    ),
    Tool(
        name="memory_branch_diff",
        description=(
            "Compare two branches." " Shows new facts, relations, and conflicts."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "source_branch": {
                    "type": "string",
                    "description": "Branch with new changes",
                },
                "target_branch": {
                    "type": "string",
                    "description": "Branch to compare against",
                },
                "category": {"type": "string", "description": "Filter by category"},
            },
            "required": ["source_branch", "target_branch"],
        },
    ),
    Tool(
        name="memory_branch_merge",
        description=(
            "Merge one branch into another."
            " Supports auto, cherry_pick, and squash strategies."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "source_branch": {
                    "type": "string",
                    "description": "Branch to merge from",
                },
                "target_branch": {
                    "type": "string",
                    "description": "Branch to merge into (default: main)",
                },
                "strategy": {
                    "type": "string",
                    "enum": ["auto", "cherry_pick", "squash"],
                    "description": "Merge strategy",
                },
                "items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "For cherry_pick: specific" " fact/observation IDs to merge"
                    ),
                },
            },
            "required": ["source_branch", "strategy"],
        },
    ),
    # === Snapshot & Time Travel ===
    Tool(
        name="memory_snapshot",
        description="Create a point-in-time snapshot of current memory state.",
        inputSchema={
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "description": "Snapshot label (e.g. 'before-refactor')",
                },
                "branch": {"type": "string", "description": "Branch to snapshot"},
            },
        },
    ),
    Tool(
        name="memory_snapshot_list",
        description="List all snapshots, optionally filtered by branch.",
        inputSchema={
            "type": "object",
            "properties": {
                "branch": {"type": "string", "description": "Filter by branch"},
            },
        },
    ),
    Tool(
        name="memory_time_travel",
        description=(
            "Query memory as it was at a specific point"
            " in time. Read-only, doesn't modify data."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "timestamp": {
                    "type": "string",
                    "description": "ISO format timestamp to travel to",
                },
                "query": {
                    "type": "string",
                    "description": "Search query to run at that time point",
                },
                "branch": {"type": "string", "description": "Branch to query"},
            },
            "required": ["timestamp", "query"],
        },
    ),
    # === Task Management ===
    Tool(
        name="memory_task_create",
        description=(
            "Create a long-running task. Creates a task"
            " branch and optionally defines objectives."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Task name (e.g. 'fix-oauth2-bug')",
                },
                "description": {
                    "type": "string",
                    "description": "What this task aims to accomplish",
                },
                "task_type": {
                    "type": "string",
                    "description": (
                        "Type: bug_fix, pr_review, feature,"
                        " research, refactor, incident"
                    ),
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Cross-cutting labels for discovery"
                        " (e.g. ['auth', 'security'])"
                    ),
                },
                "objectives": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"description": {"type": "string"}},
                    },
                    "description": "Ordered list of objectives/subtasks",
                },
                "parent_branch": {
                    "type": "string",
                    "description": "Branch to fork from (default: main)",
                },
            },
            "required": ["name"],
        },
    ),
    Tool(
        name="memory_task_join",
        description=(
            "Join an agent to a task. Creates an isolated"
            " agent branch and returns full task context."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID to join"},
                "agent_id": {
                    "type": "string",
                    "description": "Unique agent identifier (global, cross-task)",
                },
                "role": {
                    "type": "string",
                    "description": "Agent role: implementer, reviewer, tester",
                },
                "objectives": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Objective IDs this agent will work on",
                },
            },
            "required": ["task_id", "agent_id"],
        },
    ),
    Tool(
        name="memory_task_status",
        description=(
            "Get comprehensive task status: objectives,"
            " agents, progress, and recent activity."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
            },
            "required": ["task_id"],
        },
    ),
    Tool(
        name="memory_task_update",
        description=(
            "Update a task's objectives or status."
            " Mark objectives as done/blocked/active."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "objective_id": {
                    "type": "integer",
                    "description": "Objective to update",
                },
                "objective_status": {
                    "type": "string",
                    "enum": ["done", "active", "todo", "blocked"],
                },
                "agent_id": {
                    "type": "string",
                    "description": "Agent making the update",
                },
                "notes": {
                    "type": "string",
                    "description": "Notes about completion or blockers",
                },
                "task_status": {
                    "type": "string",
                    "enum": ["active", "completed", "paused", "failed"],
                },
            },
            "required": ["task_id"],
        },
    ),
    # === Consolidation ===
    Tool(
        name="memory_consolidate",
        description=(
            "Consolidate memory: distill observations into"
            " facts, deduplicate, and merge to parent scope."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["session", "agent", "task"],
                    "description": "What level to consolidate",
                },
                "task_id": {
                    "type": "string",
                    "description": "Required for agent/task scope",
                },
                "agent_id": {
                    "type": "string",
                    "description": "Required for agent scope",
                },
                "session_id": {
                    "type": "string",
                    "description": "Required for session scope",
                },
                "branch": {"type": "string", "description": "Branch for session scope"},
            },
            "required": ["scope"],
        },
    ),
    # === Replay & Cross-Branch Search ===
    Tool(
        name="memory_search_task",
        description=(
            "Search across a task's memory including all"
            " agent branches. Returns results with"
            " source attribution."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task ID to search within",
                },
                "query": {"type": "string", "description": "Search query"},
                "agent_id": {
                    "type": "string",
                    "description": "Filter to a specific agent's memories",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default: 10)",
                },
            },
            "required": ["task_id", "query"],
        },
    ),
    Tool(
        name="memory_agent_timeline",
        description="Get the complete timeline for a specific agent across all tasks.",
        inputSchema={
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent ID to replay"},
                "task_type": {"type": "string", "description": "Filter by task type"},
                "limit": {"type": "integer", "description": "Max items (default: 50)"},
            },
            "required": ["agent_id"],
        },
    ),
    Tool(
        name="memory_replay_task_type",
        description=(
            "Aggregate analysis of all tasks of a given"
            " type. Shows patterns, success rates,"
            " key findings."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_type": {"type": "string", "description": "Task type to analyze"},
                "limit": {
                    "type": "integer",
                    "description": "Max tasks to include (default: 20)",
                },
            },
            "required": ["task_type"],
        },
    ),
    # === Conversation & Message History ===
    Tool(
        name="memory_log_message",
        description=(
            "Log a message into the active conversation."
            " Captures user, assistant, or tool messages."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "role": {
                    "type": "string",
                    "enum": ["user", "assistant", "system", "tool_call", "tool_result"],
                    "description": "Message role",
                },
                "content": {
                    "type": "string",
                    "description": "Message text content",
                },
                "thinking": {
                    "type": "string",
                    "description": "Reasoning trace (if available)",
                },
                "tool_calls": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Tool call data [{name, input, output}]",
                },
                "conversation_id": {
                    "type": "string",
                    "description": "Target conversation (auto-detected if not provided)",
                },
                "session_id": {
                    "type": "string",
                    "description": "Session ID",
                },
                "token_count": {
                    "type": "integer",
                    "description": "Token count for this message",
                },
                "model": {
                    "type": "string",
                    "description": "Model that produced this message",
                },
            },
            "required": ["role", "content"],
        },
    ),
    Tool(
        name="memory_list_conversations",
        description=(
            "List conversations with optional filters."
            " Shows chat history threads."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Filter by session"},
                "agent_id": {"type": "string", "description": "Filter by agent"},
                "task_id": {"type": "string", "description": "Filter by task"},
                "status": {
                    "type": "string",
                    "enum": ["active", "completed", "forked"],
                    "description": "Filter by status",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default: 20)",
                },
            },
        },
    ),
    Tool(
        name="memory_search_messages",
        description=(
            "Semantic + keyword search across all conversation"
            " messages. Find what any agent discussed."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "conversation_id": {
                    "type": "string",
                    "description": "Limit to a specific conversation",
                },
                "role": {
                    "type": "string",
                    "description": "Filter by message role",
                },
                "branch": {"type": "string", "description": "Branch to search"},
                "limit": {
                    "type": "integer",
                    "description": "Max results (default: 10)",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="memory_fork_conversation",
        description=(
            "Fork a conversation from a specific message."
            " Creates a new conversation that shares"
            " history up to the fork point."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Conversation to fork from",
                },
                "message_id": {
                    "type": "string",
                    "description": "Message ID to fork at (inclusive)",
                },
                "branch": {
                    "type": "string",
                    "description": "Optional new branch for the fork",
                },
                "title": {
                    "type": "string",
                    "description": "Title for the forked conversation",
                },
            },
            "required": ["conversation_id", "message_id"],
        },
    ),
]


# ---- Tool Handlers ----


async def handle_tool_call(
    name: str,
    arguments: dict,
    session: AsyncSession,
    get_active_branch: Callable[[], str],
    set_active_branch: Callable[[str], None],
) -> dict:
    """Route tool calls to the appropriate handler."""
    branch = arguments.get("branch") or get_active_branch()
    embedder = get_embedding_provider()

    # === Memory Write ===
    if name == "memory_write_fact":
        engine = FactEngine(session, embedder)
        fact = await engine.write_fact(
            fact_text=arguments["fact_text"],
            category=arguments.get("category"),
            confidence=arguments.get("confidence", 1.0),
            branch_name=branch,
        )
        return {"id": fact.id, "created_at": fact.created_at}

    elif name == "memory_write_observation":
        engine = ObservationEngine(session, embedder)
        obs = await engine.write_observation(
            session_id=arguments.get("session_id", "unknown"),
            observation_type=arguments["observation_type"],
            summary=arguments["summary"],
            tool_name=arguments.get("tool_name"),
            raw_input=arguments.get("raw_input"),
            raw_output=arguments.get("raw_output"),
            branch_name=branch,
        )
        return {"id": obs.id, "created_at": obs.created_at}

    elif name == "memory_write_relation":
        engine = RelationEngine(session)
        rel = await engine.write_relation(
            source_entity=arguments["source_entity"],
            target_entity=arguments["target_entity"],
            relation_type=arguments["relation_type"],
            properties=arguments.get("properties"),
            branch_name=branch,
        )
        return {"id": rel.id}

    # === Search ===
    elif name == "memory_search":
        engine = SearchEngine(session, embedder)
        results = await engine.search(
            query=arguments["query"],
            search_type=arguments.get("search_type", "hybrid"),
            branch_name=branch,
            category=arguments.get("category"),
            limit=arguments.get("limit", 10),
            time_range=arguments.get("time_range"),
        )
        return {"results": results, "count": len(results)}

    elif name == "memory_graph_query":
        engine = RelationEngine(session)
        results = await engine.graph_query(
            entity=arguments["entity"],
            relation_type=arguments.get("relation_type"),
            depth=arguments.get("depth", 1),
            branch_name=branch,
        )
        return {"relations": results, "count": len(results)}

    elif name == "memory_timeline":
        # Combine facts + observations timeline
        fact_engine = FactEngine(session, embedder)
        obs_engine = ObservationEngine(session, embedder)

        facts = await fact_engine.list_facts(
            branch_name=branch,
            limit=arguments.get("limit", 50),
        )
        observations = await obs_engine.timeline(
            branch_name=branch,
            session_id=arguments.get("session_id"),
            after=arguments.get("after"),
            before=arguments.get("before"),
            limit=arguments.get("limit", 50),
        )

        timeline = []
        for f in facts:
            timeline.append(
                {
                    "type": "fact",
                    "id": f.id,
                    "content": f.fact_text,
                    "category": f.category,
                    "timestamp": f.created_at.isoformat() if f.created_at else None,
                }
            )
        for o in observations:
            timeline.append(
                {
                    "type": "observation",
                    "id": o.id,
                    "content": o.summary,
                    "observation_type": o.observation_type,
                    "tool_name": o.tool_name,
                    "timestamp": o.created_at.isoformat() if o.created_at else None,
                }
            )

        timeline.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
        return {"timeline": timeline[: arguments.get("limit", 50)]}

    # === Branch Operations ===
    elif name == "memory_branch_create":
        mgr = BranchManager(session)
        registry = await mgr.create_branch(
            branch_name=arguments["branch_name"],
            parent_branch=arguments.get("parent_branch", "main"),
            description=arguments.get("description"),
        )
        return {
            "branch_name": registry.branch_name,
            "parent_branch": registry.parent_branch,
            "created_at": registry.forked_at,
        }

    elif name == "memory_branch_list":
        mgr = BranchManager(session)
        branches = await mgr.list_branches(status=arguments.get("status"))
        return {
            "branches": [
                {
                    "branch_name": b.branch_name,
                    "parent_branch": b.parent_branch,
                    "status": b.status,
                    "description": b.description,
                    "forked_at": b.forked_at.isoformat() if b.forked_at else None,
                }
                for b in branches
            ]
        }

    elif name == "memory_branch_switch":
        mgr = BranchManager(session)
        await mgr.get_branch(arguments["branch_name"])  # Verify exists
        set_active_branch(arguments["branch_name"])
        return {"active_branch": arguments["branch_name"]}

    elif name == "memory_branch_diff":
        engine = MergeEngine(session)
        diff = await engine.diff(
            source_branch=arguments["source_branch"],
            target_branch=arguments["target_branch"],
            category=arguments.get("category"),
        )
        return diff.to_dict()

    elif name == "memory_branch_merge":
        engine = MergeEngine(session)
        result = await engine.merge(
            source_branch=arguments["source_branch"],
            target_branch=arguments.get("target_branch", "main"),
            strategy=arguments["strategy"],
            items=arguments.get("items"),
        )
        return result

    # === Snapshot & Time Travel ===
    elif name == "memory_snapshot":
        mgr = SnapshotManager(session)
        snapshot = await mgr.create_snapshot(
            branch_name=branch,
            label=arguments.get("label"),
        )
        return {
            "snapshot_id": snapshot.id,
            "label": snapshot.label,
            "created_at": snapshot.created_at,
        }

    elif name == "memory_snapshot_list":
        mgr = SnapshotManager(session)
        snapshots = await mgr.list_snapshots(
            branch_name=arguments.get("branch"),
        )
        return {
            "snapshots": [
                {
                    "id": s.id,
                    "label": s.label,
                    "branch_name": s.branch_name,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                }
                for s in snapshots
            ]
        }

    elif name == "memory_time_travel":
        mgr = SnapshotManager(session)
        results = await mgr.time_travel_query(
            timestamp=arguments["timestamp"],
            branch_name=branch,
        )
        return {"timestamp": arguments["timestamp"], "results": results}

    # === Task Management ===
    elif name == "memory_task_create":
        engine = TaskEngine(session)
        task = await engine.create_task(
            name=arguments["name"],
            description=arguments.get("description"),
            task_type=arguments.get("task_type"),
            tags=arguments.get("tags"),
            objectives=arguments.get("objectives"),
            parent_branch=arguments.get("parent_branch", "main"),
        )
        return {
            "task_id": task.id,
            "branch_name": task.branch_name,
            "objectives": task.objectives,
        }

    elif name == "memory_task_join":
        engine = TaskEngine(session)
        result = await engine.join_task(
            task_id=arguments["task_id"],
            agent_id=arguments["agent_id"],
            role=arguments.get("role"),
            assigned_objectives=arguments.get("objectives"),
        )
        return result

    elif name == "memory_task_status":
        engine = TaskEngine(session)
        return await engine.get_task_context(arguments["task_id"])

    elif name == "memory_task_update":
        engine = TaskEngine(session)
        if arguments.get("objective_id") and arguments.get("objective_status"):
            task = await engine.update_objective(
                task_id=arguments["task_id"],
                objective_id=arguments["objective_id"],
                status=arguments["objective_status"],
                agent_id=arguments.get("agent_id"),
                notes=arguments.get("notes"),
            )
            return {"objectives": task.objectives}
        return {"error": "Must provide objective_id and objective_status"}

    # === Consolidation ===
    elif name == "memory_consolidate":
        consolidation = ConsolidationEngine(session)
        scope = arguments["scope"]
        if scope == "session":
            return await consolidation.consolidate_session(
                session_id=arguments.get("session_id", "unknown"),
                branch_name=arguments.get("branch", branch),
                task_id=arguments.get("task_id"),
                agent_id=arguments.get("agent_id"),
            )
        elif scope == "agent":
            return await consolidation.consolidate_agent(
                task_id=arguments["task_id"],
                agent_id=arguments["agent_id"],
            )
        elif scope == "task":
            return await consolidation.consolidate_task(
                task_id=arguments["task_id"],
            )
        return {"error": f"Unknown scope: {scope}"}

    # === Replay & Cross-Branch Search ===
    elif name == "memory_search_task":
        engine = SearchEngine(session, embedder)
        return {
            "results": await engine.search_cross_branch(
                query=arguments["query"],
                task_id=arguments["task_id"],
                agent_id=arguments.get("agent_id"),
                limit=arguments.get("limit", 10),
            )
        }

    elif name == "memory_agent_timeline":
        engine = TaskEngine(session)
        return await engine.replay_agent(
            agent_id=arguments["agent_id"],
            task_type=arguments.get("task_type"),
            limit=arguments.get("limit", 50),
        )

    elif name == "memory_replay_task_type":
        engine = TaskEngine(session)
        return await engine.replay_task_type(
            task_type=arguments["task_type"],
            limit=arguments.get("limit", 20),
        )

    # === Conversation & Message History ===
    elif name == "memory_log_message":
        conv_engine = ConversationEngine(session)
        msg_engine = MessageEngine(session, embedder)

        conv_id = arguments.get("conversation_id")
        if not conv_id:
            # Auto-detect: find active conversation for session
            sid = arguments.get("session_id", "unknown")
            conv = await conv_engine.get_conversation_by_session(sid)
            if conv is None:
                conv = await conv_engine.create_conversation(session_id=sid)
            conv_id = conv.id

        msg = await msg_engine.write_message(
            conversation_id=conv_id,
            role=arguments["role"],
            content=arguments.get("content"),
            thinking=arguments.get("thinking"),
            tool_calls=arguments.get("tool_calls"),
            token_count=arguments.get("token_count", 0),
            model=arguments.get("model"),
            session_id=arguments.get("session_id"),
            branch_name=branch,
        )
        return {"id": msg.id, "conversation_id": conv_id, "sequence_num": msg.sequence_num}

    elif name == "memory_list_conversations":
        engine = ConversationEngine(session)
        convs = await engine.list_conversations(
            session_id=arguments.get("session_id"),
            agent_id=arguments.get("agent_id"),
            task_id=arguments.get("task_id"),
            status=arguments.get("status"),
            limit=arguments.get("limit", 20),
        )
        return {
            "conversations": [
                {
                    "id": c.id,
                    "session_id": c.session_id,
                    "title": c.title,
                    "status": c.status,
                    "message_count": c.message_count,
                    "total_tokens": c.total_tokens,
                    "branch_name": c.branch_name,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
                for c in convs
            ]
        }

    elif name == "memory_search_messages":
        msg_engine = MessageEngine(session, embedder)
        results = await msg_engine.search_messages(
            query=arguments["query"],
            branch_name=arguments.get("branch", branch),
            conversation_id=arguments.get("conversation_id"),
            role=arguments.get("role"),
            limit=arguments.get("limit", 10),
        )
        return {"results": results, "count": len(results)}

    elif name == "memory_fork_conversation":
        conv_engine = ConversationEngine(session)
        forked = await conv_engine.fork_conversation(
            conversation_id=arguments["conversation_id"],
            fork_at_message_id=arguments["message_id"],
            branch_name=arguments.get("branch"),
            title=arguments.get("title"),
        )
        return {
            "conversation_id": forked.id,
            "parent_conversation_id": forked.parent_conversation_id,
            "message_count": forked.message_count,
            "status": forked.status,
        }

    else:
        return {"error": f"Unknown tool: {name}"}
