# MCP Tools Reference

Complete reference for all MCP server tools. Read this when adding/modifying tools.

## Tool Conventions

All tools follow this pattern:
- `memory_*` prefix for memory operations
- `memory_branch_*` prefix for branch operations
- Return structured JSON responses
- Use `branch` parameter (defaults to "main")

## Memory Operations

### memory_write_fact

Store a structured fact in memory.

```python
tool("memory_write_fact", {
    "fact_text": str,           # Required: Natural language description
    "category": str | None,      # Optional: bug_fix, architecture, preference...
    "confidence": float | None,    # Optional: 0.0-1.0, default 1.0
    "branch": str | None,         # Optional: branch name, default "main"
})
# Returns: { "id": str, "created_at": str }
```

### memory_write_observation

Store a tool call observation (compressed).

```python
tool("memory_write_observation", {
    "observation_type": str,       # Required: tool_use, discovery, decision, error, insight
    "summary": str,              # Required: Compressed observation text
    "tool_name": str | None,      # Optional: Bash, Edit, Read, Write...
    "raw_input": str | None,      # Optional: Truncated input for debugging
    "raw_output": str | None,     # Optional: Truncated output for debugging
    "branch": str | None,         # Optional: branch name
})
# Returns: { "id": str, "created_at": str }
```

### memory_write_relation

Store an entity relationship.

```python
tool("memory_write_relation", {
    "source_entity": str,         # Required: "AuthService"
    "target_entity": str,         # Required: "UserModel"
    "relation_type": str,          # Required: depends_on, causes, fixes...
    "properties": dict | None,     # Optional: Relation metadata
    "branch": str | None,         # Optional: branch name
})
# Returns: { "id": str }
```

## Search Operations

### memory_search

Hybrid semantic + keyword search.

```python
tool("memory_search", {
    "query": str,                 # Required: Natural language query
    "search_type": str,           # Optional: "hybrid" (default), "vector", "keyword"
    "category": str | None,         # Optional: Filter by category
    "branch": str | None,           # Optional: Branch to search, default "main"
    "limit": int | None,           # Optional: Max results, default 10
    "time_range": dict | None,      # Optional: { "after": ISO date, "before": ISO date }
})
# Returns: [
#   { "id": str, "fact_text": str, "category": str, "score": float, ... }
# ]
```

### memory_graph_query

Query entity relationship graph.

```python
tool("memory_graph_query", {
    "entity": str,                 # Required: Entity name
    "relation_type": str | None,     # Optional: Filter by relation type
    "depth": int | None,           # Optional: Traverse depth, default 1
    "branch": str | None,           # Optional: Branch to query
})
# Returns: [
#   { "source": str, "target": str, "relation": str, "properties": dict }
# ]
```

### memory_timeline

Get chronological memory.

```python
tool("memory_timeline", {
    "session_id": str | None,       # Optional: Filter by session
    "branch": str | None,           # Optional: Branch name
    "after": str | None,           # Optional: ISO timestamp
    "before": str | str | None,      # Optional: ISO timestamp
    "limit": int | None,           # Optional: Max results
})
# Returns: [ { "type": "fact|observation", "timestamp": str, "content": str } ]
```

## Branch Operations

### memory_branch_create

Create isolated branch (zero-copy CLONE).

```python
tool("memory_branch_create", {
    "branch_name": str,            # Required: New branch name
    "parent_branch": str | None,     # Optional: Parent, default "main"
    "description": str | None,       # Optional: Branch purpose
})
# Returns: { "branch_name": str, "created_at": str }
```

### memory_branch_list

List all branches.

```python
tool("memory_branch_list", {
    "status": str | None,           # Optional: "active", "merged", "archived"
})
# Returns: [
#   { "branch_name": str, "parent": str, "status": str, "description": str }
# ]
```

### memory_branch_switch

Set default branch for subsequent operations.

```python
tool("memory_branch_switch", {
    "branch_name": str,             # Required: Branch to switch to
})
# Returns: { "active_branch": str }
```

### memory_branch_diff

Compare two branches.

```python
tool("memory_branch_diff", {
    "source_branch": str,          # Required
    "target_branch": str,          # Required
    "category": str | None,         # Optional: Filter diff by category
})
# Returns: {
#   "new_facts": [...],
#   "new_relations": [...],
#   "conflicts": [{ "id": str, "source": str, "target": str }]
# }
```

### memory_branch_merge

Merge source into target.

```python
tool("memory_branch_merge", {
    "source_branch": str,          # Required
    "target_branch": str | None,     # Optional: default "main"
    "strategy": str,               # Required: "auto", "cherry_pick", "squash"
    "items": list[str] | None,      # Required for cherry_pick: fact/observation IDs
})
# Returns: {
#   "merged_count": int,
#   "rejected_count": int,
#   "merge_id": str
# }
```

## Snapshot & Time Travel

### memory_snapshot

Create point-in-time snapshot.

```python
tool("memory_snapshot", {
    "label": str | None,            # Optional: Snapshot label
    "branch": str | None,           # Optional: Branch name
})
# Returns: { "snapshot_id": str, "created_at": str }
```

### memory_snapshot_list

List snapshots.

```python
tool("memory_snapshot_list", {
    "branch": str | None,           # Optional: Branch name
})
# Returns: [{ "id": str, "label": str, "created_at": str }]
```

### memory_time_travel

Query memory as it was at a point in time.

```python
tool("memory_time_travel", {
    "timestamp": str,              # Required: ISO format
    "query": str,                  # Required: Search query to run at that time
    "branch": str | None,           # Optional: Branch name
})
# Returns: Same as memory_search, but from historical state
```

## Task Management

### memory_task_create

Create a multi-agent task with objectives.

```python
tool("memory_task_create", {
    "name": str,                   # Required: Task name
    "description": str | None,    # Optional: Task description
    "task_type": str | None,      # Optional: Category (e.g., "bug_fix", "feature")
    "tags": list[str] | None,    # Optional: Tags for discovery
    "objectives": list[dict] | None,  # Optional: [{description, priority}]
    "parent_branch": str | None,  # Optional: Parent branch (default "main")
})
# Returns: { "task_id": str, "branch_name": str }
```

### memory_task_join

Join a task as an agent.

```python
tool("memory_task_join", {
    "task_id": str,                # Required
    "agent_id": str,              # Required
    "role": str | None,           # Optional: "implementer", "reviewer", "tester"
    "assigned_objectives": list[int] | None,  # Optional: Objective indices
})
# Returns: { "branch_name": str, "objectives": [...] }
```

### memory_task_status

Get task status including agents and objectives.

```python
tool("memory_task_status", {
    "task_id": str,               # Required
})
# Returns: { "task": {...}, "agents": [...], "objectives": [...] }
```

### memory_task_update

Update task objective status.

```python
tool("memory_task_update", {
    "task_id": str,               # Required
    "objective_id": int,          # Required: Objective index
    "status": str,                # Required: "pending", "in_progress", "completed"
    "agent_id": str | None,       # Optional
    "notes": str | None,          # Optional
})
```

### memory_consolidate

Consolidate observations into candidate facts (session/agent/task level).

```python
tool("memory_consolidate", {
    "level": str,                  # Required: "session", "agent", "task"
    "session_id": str | None,      # Required for "session"
    "task_id": str | None,         # Required for "agent"/"task"
    "agent_id": str | None,        # Required for "agent"
})
# Returns: { "new_facts": int, "duplicates_merged": int }
```

### memory_search_task

Search within a task's scope (cross-agent).

```python
tool("memory_search_task", {
    "task_id": str,               # Required
    "query": str,                 # Required
    "agent_id": str | None,       # Optional: Filter by agent
    "limit": int | None,          # Optional
})
```

### memory_agent_timeline

Get agent's activity timeline.

```python
tool("memory_agent_timeline", {
    "agent_id": str,              # Required
    "limit": int | None,          # Optional
})
```

### memory_replay_task_type

Analyze patterns across tasks of same type.

```python
tool("memory_replay_task_type", {
    "task_type": str,             # Required
    "limit": int | None,          # Optional
})
```

## Conversation Management

### memory_log_message

Add a message to a conversation.

```python
tool("memory_log_message", {
    "conversation_id": str | None,  # Optional: Auto-creates if absent
    "role": str,                    # Required: "user", "assistant", "system", "tool"
    "content": str,                 # Required
    "thinking": str | None,         # Optional: Chain-of-thought
    "tool_calls": list | None,      # Optional
    "model": str | None,            # Optional
    "branch": str | None,           # Optional
})
# Returns: { "message_id": str, "conversation_id": str }
```

### memory_list_conversations

List conversations with filters.

```python
tool("memory_list_conversations", {
    "branch": str | None,          # Optional
    "session_id": str | None,      # Optional
    "agent_id": str | None,        # Optional
    "task_id": str | None,         # Optional
    "limit": int | None,           # Optional
})
```

### memory_search_messages

Search across messages.

```python
tool("memory_search_messages", {
    "query": str,                  # Required
    "branch": str | None,         # Optional
    "conversation_id": str | None, # Optional
    "role": str | None,           # Optional
    "limit": int | None,          # Optional
})
```

### memory_fork_conversation

Fork a conversation at a message (for replay).

```python
tool("memory_fork_conversation", {
    "conversation_id": str,       # Required
    "fork_at_message_id": str,    # Required
    "branch": str | None,        # Optional: Target branch
    "title": str | None,         # Optional
})
# Returns: { "forked_conversation_id": str, "messages_copied": int }
```

### memory_cherry_pick_conversation

Cherry-pick a conversation or message range to another branch.

```python
tool("memory_cherry_pick_conversation", {
    "conversation_id": str,       # Required
    "target_branch": str,         # Required
    "from_sequence": int | None,  # Optional: Start of range
    "to_sequence": int | None,    # Optional: End of range
})
# Returns: { "new_conversation_id": str, "messages_copied": int }
```

## Curation

### memory_branch_create_curated

Create a curated branch from selected conversations and facts.

```python
tool("memory_branch_create_curated", {
    "branch_name": str,           # Required
    "parent_branch": str | None,  # Optional (default "main")
    "conversation_ids": list[str] | None,  # Optional
    "fact_ids": list[str] | None,          # Optional
    "description": str | None,    # Optional
})
# Returns: { "branch_name": str, "conversations": int, "facts": int }
```

### memory_session_context

Get full session context (facts, conversations, observations).

```python
tool("memory_session_context", {
    "session_id": str,            # Required
    "message_limit": int | None,  # Optional
    "fact_limit": int | None,     # Optional
})
# Returns: { "session": {...}, "facts": [...], "conversations": [...], "observations": [...] }
```

## Branch Topology

### memory_branch_topology

Get the hierarchical branch topology tree.

```python
tool("memory_branch_topology", {
    "root_branch": str | None,       # Optional: root (default "main")
    "max_depth": int | None,         # Optional: max tree depth (default 10)
    "include_archived": bool | None, # Optional: include archived (default false)
})
# Returns: { "branch_name": str, "children": [...], "status": str, "metadata": dict }
```

### memory_branch_enrich

Enrich branch metadata with purpose, owner, TTL, tags.

```python
tool("memory_branch_enrich", {
    "branch_name": str,              # Required: branch to enrich
    "purpose": str | None,           # Optional: branch purpose
    "owner": str | None,             # Optional: owner agent/team
    "ttl_days": int | None,          # Optional: time-to-live hint
    "tags": list[str] | None,       # Optional: discovery tags
})
# Returns: { "branch_name": str, "metadata": dict }
```

## Templates

### memory_template_list

List available branch templates.

```python
tool("memory_template_list", {
    "task_type": str | None,         # Optional: filter by task type
    "status": str | None,            # Optional: "active" or "deprecated" (default "active")
    "limit": int | None,             # Optional: max results (default 20)
})
# Returns: { "templates": [{ "name": str, "version": int, "branch_name": str, ... }] }
```

### memory_template_create

Create a template from a curated branch.

```python
tool("memory_template_create", {
    "name": str,                     # Required: template name (unique)
    "source_branch": str,            # Required: branch to snapshot
    "description": str | None,      # Optional
    "applicable_task_types": list[str] | None,  # Optional
    "tags": list[str] | None,       # Optional
})
# Returns: { "name": str, "version": int, "branch_name": str, "fact_count": int, "conversation_count": int }
```

### memory_template_instantiate

Fork a template into a working branch.

```python
tool("memory_template_instantiate", {
    "template_name": str,            # Required: template to instantiate
    "target_branch_name": str,       # Required: new working branch name
    "task_id": str | None,          # Optional: task to associate
})
# Returns: { "branch_name": str, "template_name": str, "template_version": int, "facts_inherited": int }
```

## Verification

### verify_fact

Verify a fact using LLM-as-judge. Evaluates accuracy, relevance, specificity.

```python
tool("verify_fact", {
    "fact_id": str,              # Required: Fact ID to verify
    "dimensions": list[str],     # Optional: Evaluation dimensions
    "context": str | None,       # Optional: Additional context
})
# Returns: { "fact_id": str, "verdict": str, "reason": str, "scores": [...] }
```

### verify_batch

Batch-verify all unverified facts on a branch.

```python
tool("verify_batch", {
    "branch_name": str | None,   # Optional: Branch to verify
    "limit": int | None,         # Optional: Max facts (default: 50)
    "only_unverified": bool,     # Optional: Skip verified (default: true)
})
# Returns: { "total_processed": int, "verified": int, "invalidated": int, ... }
```

### verify_merge_gate

Check if a branch passes the verification merge gate.

```python
tool("verify_merge_gate", {
    "source_branch": str,        # Required: Branch to check
    "require_verified": bool,    # Optional: Require all verified (default: true)
})
# Returns: { "can_merge": bool, "verified": int, "unverified": int, ... }
```

## Handoff

### memory_handoff_create

Create a structured handoff between branches/agents with verified facts.

```python
tool("memory_handoff_create", {
    "source_branch": str,        # Required: Source branch
    "target_branch": str,        # Required: Target branch
    "handoff_type": str,         # Optional: task_continuation, agent_switch, etc.
    "include_unverified": bool,  # Optional: Include unverified facts (default: false)
    "context_summary": str,      # Optional: Manual summary
})
# Returns: { "handoff_id": str, "fact_count": int, "conversation_count": int, ... }
```

### memory_handoff_get

Retrieve the full handoff packet for a receiving agent.

```python
tool("memory_handoff_get", {
    "handoff_id": str,           # Required: Handoff record ID
})
# Returns: { "facts": [...], "conversations": [...], "context_summary": str, ... }
```

## Knowledge Bundles

### knowledge_bundle_create

Create a portable knowledge bundle from a branch.

```python
tool("knowledge_bundle_create", {
    "name": str,                 # Required: Bundle name
    "source_branch": str,        # Required: Branch to export from
    "description": str | None,   # Optional: Description
    "tags": list[str] | None,   # Optional: Discovery tags
    "only_verified": bool,       # Optional: Only verified facts (default: true)
})
# Returns: { "id": str, "name": str, "fact_count": int, ... }
```

### knowledge_bundle_import

Import a knowledge bundle into a target branch.

```python
tool("knowledge_bundle_import", {
    "bundle_id": str,            # Required: Bundle to import
    "target_branch": str,        # Required: Target branch
})
# Returns: { "facts_imported": int, "conversations_imported": int, ... }
```

### knowledge_bundle_list

List available knowledge bundles.

```python
tool("knowledge_bundle_list", {
    "status": str | None,        # Optional: active, deprecated (default: active)
    "limit": int | None,         # Optional: Max results (default: 20)
})
# Returns: { "bundles": [...] }
```

## Implementation File

- **Definition & Handlers**: `src/day1/mcp/tools.py` (42 tools)
- **MCP Server**: `src/day1/mcp/mcp_server.py` (stdio mode)
- **MCP HTTP Server**: `src/day1/mcp/mcp_server_http.py` (SSE mode)
- **Handler pattern**: Each tool = async function dispatched via `handle_tool_call()`
