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

## Implementation File

- **Definition**: `src/mcp/tools/__init__.py`
- **Registration**: `src/mcp/server.py`
- **Handler pattern**: Each tool = async function with typed args
