# Architecture

BranchedMind system design and integration points. Read this when understanding how components connect.

## Layer Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              Upper Layer (NOT our concern)               │
│  Claude Code │ Multi-Agent │ Cursor │ Any Client  │
└──────────────┬───────────────────┬────────────────┘
               │                   │
               ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│              Integration Layer                        │
│                                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────┐  │
│  │ Claude Code  │  │  MCP Server  │  │ REST │  │
│  │   Plugin     │  │  (stdio/SSE)  │  │ API  │  │
│  │  (Hooks+)     │  │              │  │      │  │
│  │   Skills      │  │  memory_*    │  │/api/│  │
│  └──────┬───────┘  └──────┬───────┘  └──┬───┘  │
│         │                   │               │        │
│         └─────────────────────┼───────────────┘        │
│                             ▼                          │
│  ┌───────────────────────────────────────────────┐       │
│  │      Memory Orchestrator (Core)           │       │
│  │                                           │       │
│  │ Branch │ Fact │ Search │ Merge │ Trace │       │
│  │ Mgr    │ Engine│ Engine  │ Engine  │ Logger  │       │
│  └─────────────────────┬─────────────────────┘       │
│                       ▼                              │
│  ┌───────────────────────────────────────────────┐       │
│  │         MatrixOne Database                  │       │
│  │                                            │
│  │ main_memory.facts       (vector + BM25)     │
│  │ main_memory.relations  (entity graph)        │
│  │ main_memory.observations (tool calls)          │
│  │ branch_*  (isolated via CLONE)            │
│  └───────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

## Integration Points

### 1. MCP Server (Primary)

Standard interface for any MCP-compatible client. Tools exposed:

| Tool | Purpose |
|-------|---------|
| `memory_write_fact` | Store structured fact |
| `memory_write_observation` | Store tool call result |
| `memory_search` | Hybrid BM25+Vector search |
| `memory_graph_query` | Query entity relations |
| `memory_branch_create` | Create isolated branch |
| `memory_branch_merge` | Merge branches |
| `memory_timeline` | Get chronological history |
| `memory_snapshot` | Create point-in-time snapshot |

### 2. Claude Code Plugin (Hooks)

Automatic capture - user doesn't call tools manually.

| Hook | Trigger | Purpose |
|-------|----------|---------|
| `SessionStart` | Session init | Inject relevant historical memory |
| `PostToolUse` | After tool call | Compress and store observation |
| `PreCompact` | Before context compress | Extract facts/relations |
| `Stop` | After response | Generate interim summary |
| `SessionEnd` | Session close | Generate final summary |

### 3. REST API

HTTP interface for dashboards, external tools, CI/CD.

```
POST   /api/v1/facts              # Write fact
GET    /api/v1/facts/search       # Search
GET    /api/v1/facts/:id          # Get single fact

POST   /api/v1/branches           # Create branch
GET    /api/v1/branches           # List branches
POST   /api/v1/branches/:name/merge # Merge
```

## Key Design Decisions

1. **MySQL Protocol** - MatrixOne is MySQL-compatible. Use standard drivers (`pymysql`, `go-sql-driver/mysql`).

2. **Branch = Database** - MatrixOne CLONE creates zero-copy independent database. Each agent gets isolated storage.

3. **Merge is Application-Layer** - MatrixOne lacks cherry-pick. We implement merge logic in Python.

4. **Vector + BM25 Hybrid** - Union both results for better semantic + keyword matching.

5. **Hooks Over Skills** - Automatic capture via Hooks > manual Skill invocation.

## File Locations

| Component | Path |
|-----------|-------|
| MCP Server | `src/mcp/server.py` |
| Hooks | `src/hooks/*.py` |
| Core Logic | `src/core/` |
| Database | `src/db/models.py`, `src/db/engine.py` |
| REST API | `src/api/app.py` |
