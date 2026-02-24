"""MCP tool definitions and handlers for all memory_* tools."""

from __future__ import annotations

from collections.abc import Callable

from mcp.types import Tool
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.analytics_engine import AnalyticsEngine
from day1.core.branch_manager import BranchManager
from day1.core.branch_topology_engine import BranchTopologyEngine
from day1.core.consolidation_engine import ConsolidationEngine
from day1.core.conversation_cherry_pick import ConversationCherryPick
from day1.core.conversation_engine import ConversationEngine
from day1.core.embedding import get_embedding_provider
from day1.core.fact_engine import FactEngine
from day1.core.merge_engine import MergeEngine
from day1.core.message_engine import MessageEngine
from day1.core.observation_engine import ObservationEngine
from day1.core.relation_engine import RelationEngine
from day1.core.replay_engine import ReplayConfig, ReplayEngine
from day1.core.scoring_engine import ScoringEngine
from day1.core.search_engine import SearchEngine
from day1.core.semantic_diff import SemanticDiffEngine
from day1.core.session_manager import SessionManager
from day1.core.snapshot_manager import SnapshotManager
from day1.core.task_engine import TaskEngine
from day1.core.template_engine import TemplateEngine

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
    # === Cherry-Pick ===
    Tool(
        name="memory_cherry_pick_conversation",
        description=(
            "Cherry-pick a conversation (or message range)"
            " to another branch. Copies the conversation and"
            " its messages to the target branch."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Source conversation to cherry-pick",
                },
                "target_branch": {
                    "type": "string",
                    "description": "Branch to copy into",
                },
                "from_sequence": {
                    "type": "integer",
                    "description": (
                        "Start of message range (optional —"
                        " omit to copy entire conversation)"
                    ),
                },
                "to_sequence": {
                    "type": "integer",
                    "description": "End of message range (inclusive)",
                },
                "title": {
                    "type": "string",
                    "description": "Title for the extracted conversation (range mode only)",
                },
            },
            "required": ["conversation_id", "target_branch"],
        },
    ),
    Tool(
        name="memory_branch_create_curated",
        description=(
            "Create a curated branch from selected conversations"
            " and facts. Builds a starter-kit branch for future"
            " agents with only the context that matters."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "branch_name": {
                    "type": "string",
                    "description": "Name for the new curated branch",
                },
                "parent_branch": {
                    "type": "string",
                    "description": "Parent branch (default: main)",
                },
                "conversation_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Conversations to include (with all messages)",
                },
                "fact_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Facts to include",
                },
                "description": {
                    "type": "string",
                    "description": "Branch description",
                },
            },
            "required": ["branch_name"],
        },
    ),
    # === Session Context Handoff ===
    Tool(
        name="memory_session_context",
        description=(
            "Get full context from a previous session for"
            " handoff. Returns session metadata, conversations"
            " with messages, facts, and observation summary."
            " Use this when continuing work from a prior session."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID to retrieve context from",
                },
                "message_limit": {
                    "type": "integer",
                    "description": "Max messages per conversation (default: 50)",
                },
                "fact_limit": {
                    "type": "integer",
                    "description": "Max facts to include (default: 20)",
                },
            },
            "required": ["session_id"],
        },
    ),
    # === Replay ===
    Tool(
        name="replay_conversation",
        description=(
            "Fork a conversation at a specific message and prepare for"
            " re-execution with different parameters. Returns the forked"
            " conversation ready for new messages. Use this to explore"
            " 'what if' scenarios — replay with a different model,"
            " system prompt, or context."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Source conversation to replay from",
                },
                "from_message_id": {
                    "type": "string",
                    "description": (
                        "Fork at this message (inclusive — this and all"
                        " prior messages are copied)"
                    ),
                },
                "system_prompt": {
                    "type": "string",
                    "description": "Override system prompt for the replay",
                },
                "model": {
                    "type": "string",
                    "description": "Override model for the replay",
                },
                "extra_context": {
                    "type": "string",
                    "description": (
                        "Additional context injected as a system message"
                        " before the replay point"
                    ),
                },
                "title": {
                    "type": "string",
                    "description": "Title for the replayed conversation",
                },
            },
            "required": ["conversation_id", "from_message_id"],
        },
    ),
    Tool(
        name="replay_diff",
        description=(
            "Diff a replayed conversation against its original."
            " Shows what changed between the original and the replay."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "replay_id": {
                    "type": "string",
                    "description": "The replay (forked) conversation ID",
                },
            },
            "required": ["replay_id"],
        },
    ),
    Tool(
        name="replay_list",
        description=(
            "List replay conversations, optionally filtered by"
            " source conversation or session."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Filter replays of this conversation",
                },
                "session_id": {
                    "type": "string",
                    "description": "Filter replays from this session",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default: 20)",
                },
            },
        },
    ),
    # === Semantic Diff ===
    Tool(
        name="semantic_diff",
        description=(
            "Three-layer semantic diff between two agent conversations."
            " Unlike text diff, this compares: (1) Action traces — what"
            " tools were called, in what order, with what args."
            " (2) Reasoning — whether the agent's thinking diverged"
            " (via embedding similarity). (3) Outcomes — token efficiency,"
            " error counts, final result. Use this to understand WHY two"
            " conversation branches differ, not just WHERE."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "conversation_a": {
                    "type": "string",
                    "description": "First conversation ID (typically original)",
                },
                "conversation_b": {
                    "type": "string",
                    "description": (
                        "Second conversation ID (typically replay or fork)"
                    ),
                },
            },
            "required": ["conversation_a", "conversation_b"],
        },
    ),
    # === Analytics ===
    Tool(
        name="analytics_overview",
        description=(
            "Get top-level dashboard metrics: entity counts, token usage,"
            " recent activity, and consolidation stats. Useful for"
            " understanding overall system health and usage."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "branch": {
                    "type": "string",
                    "description": "Filter to branch (omit for all)",
                },
                "days": {
                    "type": "integer",
                    "description": "Lookback window in days (default: 30)",
                },
            },
        },
    ),
    Tool(
        name="analytics_session",
        description=(
            "Get per-session analytics: conversation count, messages,"
            " tokens, facts created, tool usage breakdown, and"
            " message role distribution."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session to analyze",
                },
            },
            "required": ["session_id"],
        },
    ),
    Tool(
        name="analytics_agent",
        description=(
            "Get per-agent performance: sessions, conversations,"
            " facts by category, tool usage with outcomes,"
            " and task assignments."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Agent to analyze",
                },
                "days": {
                    "type": "integer",
                    "description": "Lookback window in days (default: 30)",
                },
            },
            "required": ["agent_id"],
        },
    ),
    Tool(
        name="analytics_trends",
        description=(
            "Get time-series metrics: messages, facts, and conversations"
            " over time. Useful for spotting usage patterns and growth."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "branch": {
                    "type": "string",
                    "description": "Filter to branch (omit for all)",
                },
                "days": {
                    "type": "integer",
                    "description": "Lookback window in days (default: 30)",
                },
                "granularity": {
                    "type": "string",
                    "description": "'day' or 'hour' (default: 'day')",
                    "enum": ["day", "hour"],
                },
            },
        },
    ),
    # === Scoring ===
    Tool(
        name="score_conversation",
        description=(
            "Evaluate a conversation using LLM-as-judge. Default dimensions:"
            " helpfulness, correctness, coherence, efficiency. You can also"
            " pass custom dimensions like safety, instruction_following,"
            " creativity, completeness. Scores are stored and aggregated."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Conversation to evaluate",
                },
                "dimensions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Dimensions to evaluate (default: helpfulness,"
                        " correctness, coherence, efficiency)"
                    ),
                },
            },
            "required": ["conversation_id"],
        },
    ),
    Tool(
        name="score_summary",
        description=(
            "Get aggregate score summary for a conversation or message."
            " Returns avg, min, max per dimension."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "target_type": {
                    "type": "string",
                    "description": "'conversation' or 'message'",
                },
                "target_id": {
                    "type": "string",
                    "description": "ID of the target",
                },
            },
            "required": ["target_type", "target_id"],
        },
    ),
    # === Branch Topology ===
    Tool(
        name="memory_branch_topology",
        description=(
            "Get the hierarchical branch topology tree for visualization."
            " Shows parent-child relationships, branch status, and metadata."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "root_branch": {
                    "type": "string",
                    "description": "Root of the tree (default: main)",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Max tree depth (default: 10)",
                },
                "include_archived": {
                    "type": "boolean",
                    "description": "Include archived branches (default: false)",
                },
            },
        },
    ),
    Tool(
        name="memory_branch_enrich",
        description=(
            "Enrich a branch with metadata: purpose, owner, TTL, and tags."
            " Useful for organizing branches at scale."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "branch_name": {
                    "type": "string",
                    "description": "Branch to enrich",
                },
                "purpose": {
                    "type": "string",
                    "description": "Branch purpose description",
                },
                "owner": {
                    "type": "string",
                    "description": "Branch owner (agent ID or team)",
                },
                "ttl_days": {
                    "type": "integer",
                    "description": "Time-to-live in days (auto-expire hint)",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for discovery and filtering",
                },
            },
            "required": ["branch_name"],
        },
    ),
    # === Templates ===
    Tool(
        name="memory_template_list",
        description=(
            "List available branch templates. Templates are reusable"
            " knowledge snapshots that new agents can fork from."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_type": {
                    "type": "string",
                    "description": "Filter by applicable task type",
                },
                "status": {
                    "type": "string",
                    "enum": ["active", "deprecated"],
                    "description": "Filter by status (default: active)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default: 20)",
                },
            },
        },
    ),
    Tool(
        name="memory_template_create",
        description=(
            "Create a template from a curated branch. The template"
            " snapshots the branch content (facts, conversations) for reuse."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Template name (unique)",
                },
                "source_branch": {
                    "type": "string",
                    "description": "Branch to create template from",
                },
                "description": {
                    "type": "string",
                    "description": "Template description",
                },
                "applicable_task_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Task types this template applies to",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Discovery tags",
                },
            },
            "required": ["name", "source_branch"],
        },
    ),
    Tool(
        name="memory_template_instantiate",
        description=(
            "Fork a template into a working branch. The new branch"
            " inherits all facts and conversations from the template."
            " Use this to start a new task with pre-loaded knowledge."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "template_name": {
                    "type": "string",
                    "description": "Template to instantiate",
                },
                "target_branch_name": {
                    "type": "string",
                    "description": "Name for the new working branch",
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task to associate",
                },
            },
            "required": ["template_name", "target_branch_name"],
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

    # === Cherry-Pick ===
    elif name == "memory_cherry_pick_conversation":
        cherry = ConversationCherryPick(session)
        from_seq = arguments.get("from_sequence")
        to_seq = arguments.get("to_sequence")
        if from_seq is not None and to_seq is not None:
            return await cherry.cherry_pick_message_range(
                conversation_id=arguments["conversation_id"],
                from_sequence=from_seq,
                to_sequence=to_seq,
                target_branch=arguments["target_branch"],
                title=arguments.get("title"),
            )
        else:
            return await cherry.cherry_pick_conversation(
                conversation_id=arguments["conversation_id"],
                target_branch=arguments["target_branch"],
            )

    elif name == "memory_branch_create_curated":
        cherry = ConversationCherryPick(session)
        return await cherry.cherry_pick_to_curated_branch(
            branch_name=arguments["branch_name"],
            parent_branch=arguments.get("parent_branch", "main"),
            conversation_ids=arguments.get("conversation_ids"),
            fact_ids=arguments.get("fact_ids"),
            description=arguments.get("description"),
        )

    # === Session Context Handoff ===
    elif name == "memory_session_context":
        mgr = SessionManager(session)
        return await mgr.get_session_context(
            session_id=arguments["session_id"],
            message_limit=arguments.get("message_limit", 50),
            fact_limit=arguments.get("fact_limit", 20),
        )

    # === Replay ===
    elif name == "replay_conversation":
        engine = ReplayEngine(session)
        config = ReplayConfig(
            system_prompt=arguments.get("system_prompt"),
            model=arguments.get("model"),
            extra_context=arguments.get("extra_context"),
            title=arguments.get("title"),
        )
        result = await engine.start_replay(
            conversation_id=arguments["conversation_id"],
            from_message_id=arguments["from_message_id"],
            config=config,
        )
        return {
            "replay_id": result.replay_id,
            "original_conversation_id": result.original_conversation_id,
            "forked_conversation_id": result.forked_conversation_id,
            "status": result.status,
            "messages_copied": result.messages_copied,
        }

    elif name == "replay_diff":
        engine = ReplayEngine(session)
        return await engine.diff_replay(arguments["replay_id"])

    elif name == "replay_list":
        engine = ReplayEngine(session)
        replays = await engine.list_replays(
            conversation_id=arguments.get("conversation_id"),
            session_id=arguments.get("session_id"),
            limit=arguments.get("limit", 20),
        )
        return {"replays": replays, "count": len(replays)}

    # === Semantic Diff ===
    elif name == "semantic_diff":
        engine = SemanticDiffEngine(session, embedder)
        return await engine.semantic_diff(
            conversation_a_id=arguments["conversation_a"],
            conversation_b_id=arguments["conversation_b"],
        )

    # === Analytics ===
    elif name == "analytics_overview":
        engine = AnalyticsEngine(session)
        return await engine.overview(
            branch_name=arguments.get("branch"),
            days=arguments.get("days", 30),
        )

    elif name == "analytics_session":
        engine = AnalyticsEngine(session)
        return await engine.session_analytics(arguments["session_id"])

    elif name == "analytics_agent":
        engine = AnalyticsEngine(session)
        return await engine.agent_analytics(
            agent_id=arguments["agent_id"],
            days=arguments.get("days", 30),
        )

    elif name == "analytics_trends":
        engine = AnalyticsEngine(session)
        return await engine.trends(
            branch_name=arguments.get("branch"),
            days=arguments.get("days", 30),
            granularity=arguments.get("granularity", "day"),
        )

    # === Scoring ===
    elif name == "score_conversation":
        engine = ScoringEngine(session)
        return {
            "scores": await engine.score_conversation(
                conversation_id=arguments["conversation_id"],
                dimensions=arguments.get("dimensions"),
            )
        }

    elif name == "score_summary":
        engine = ScoringEngine(session)
        return await engine.get_score_summary(
            target_type=arguments["target_type"],
            target_id=arguments["target_id"],
        )

    # === Branch Topology ===
    elif name == "memory_branch_topology":
        engine = BranchTopologyEngine(session)
        return await engine.get_topology(
            root_branch=arguments.get("root_branch", "main"),
            max_depth=arguments.get("max_depth", 10),
            include_archived=arguments.get("include_archived", False),
        )

    elif name == "memory_branch_enrich":
        engine = BranchTopologyEngine(session)
        branch = await engine.enrich_branch_metadata(
            branch_name=arguments["branch_name"],
            purpose=arguments.get("purpose"),
            owner=arguments.get("owner"),
            ttl_days=arguments.get("ttl_days"),
            tags=arguments.get("tags"),
        )
        return {
            "branch_name": branch.branch_name,
            "metadata": branch.metadata_json,
        }

    # === Templates ===
    elif name == "memory_template_list":
        engine = TemplateEngine(session)
        templates = await engine.list_templates(
            task_type=arguments.get("task_type"),
            status=arguments.get("status", "active"),
            limit=arguments.get("limit", 20),
        )
        return {
            "templates": [
                {
                    "name": t.name,
                    "description": t.description,
                    "version": t.version,
                    "branch_name": t.branch_name,
                    "applicable_task_types": t.applicable_task_types,
                    "tags": t.tags,
                    "fact_count": t.fact_count,
                    "conversation_count": t.conversation_count,
                    "status": t.status,
                }
                for t in templates
            ]
        }

    elif name == "memory_template_create":
        engine = TemplateEngine(session)
        template = await engine.create_template(
            name=arguments["name"],
            source_branch=arguments["source_branch"],
            description=arguments.get("description"),
            applicable_task_types=arguments.get("applicable_task_types"),
            tags=arguments.get("tags"),
        )
        return {
            "name": template.name,
            "version": template.version,
            "branch_name": template.branch_name,
            "fact_count": template.fact_count,
            "conversation_count": template.conversation_count,
        }

    elif name == "memory_template_instantiate":
        engine = TemplateEngine(session)
        return await engine.instantiate_template(
            template_name=arguments["template_name"],
            target_branch_name=arguments["target_branch_name"],
            task_id=arguments.get("task_id"),
        )

    else:
        return {"error": f"Unknown tool: {name}"}
