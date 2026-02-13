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
│  │        MatrixOne Database (Native)           │       │
│  │                                              │
│  │ facts          (vecf32 + FULLTEXT INDEX)     │
│  │ relations      (entity graph)                │
│  │ observations   (tool calls + FULLTEXT INDEX) │
│  │ facts_<branch> (via DATA BRANCH CREATE)      │
│  └───────────────────────────────────────────────┘       │
│                                                         │
│  ┌───────────────────────────────────────────────┐       │
│  │      Dashboard (React + Vite)                │       │
│  │ BranchTree │ Timeline │ MergePanel │ Search  │       │
│  └───────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

## MatrixOne Native Capabilities

| Feature | SQL Syntax | Replaces |
|---------|-----------|----------|
| **Git4Data Branch** | `DATA BRANCH CREATE TABLE t2 FROM t1` | Application-level row copying |
| **Git4Data Diff** | `DATA BRANCH DIFF t2 AGAINST t1` | Application-level fact comparison |
| **Git4Data Merge** | `DATA BRANCH MERGE t2 INTO t1 WHEN CONFLICT SKIP/ACCEPT` | Application-level merge |
| **Fulltext Search** | `MATCH(col) AGAINST('q' IN NATURAL LANGUAGE MODE)` | SQLite FTS5 virtual tables |
| **Vector Search** | `cosine_similarity(embedding, '[...]')` | In-memory Python cosine_similarity |
| **Time Travel** | `SELECT ... FROM t {AS OF TIMESTAMP 'ts'}` | Application-level timestamp filtering |
| **PITR** | `CREATE PITR name FOR DATABASE db RANGE 1 "d"` | JSON snapshot serialization |
| **Snapshot** | `CREATE SNAPSHOT sp FOR DATABASE db` | Application-level JSON dumps |

## Branch Model

Each branch = a set of suffixed tables:
- **main** branch: `facts`, `relations`, `observations`
- **feature_x** branch: `facts_feature_x`, `relations_feature_x`, `observations_feature_x`

Tables are created via `DATA BRANCH CREATE TABLE` (zero-copy, CoW semantics).

## Integration Points

### 1. MCP Server (Primary)

Standard interface for any MCP-compatible client. Tools exposed:

| Tool | Purpose |
|-------|---------|
| `memory_write_fact` | Store structured fact |
| `memory_write_observation` | Store tool call result |
| `memory_search` | Hybrid BM25+Vector search |
| `memory_graph_query` | Query entity relations |
| `memory_branch_create` | Create isolated branch (DATA BRANCH) |
| `memory_branch_merge` | Merge branches (native or application-layer) |
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
POST   /api/v1/facts                          # Write fact
GET    /api/v1/facts/search                   # Search (hybrid/keyword/vector)
GET    /api/v1/facts/:id                      # Get single fact

POST   /api/v1/branches                       # Create branch (DATA BRANCH)
GET    /api/v1/branches                       # List branches
GET    /api/v1/branches/:name/diff/native     # MO native row-level diff
GET    /api/v1/branches/:name/diff/native/count  # Diff counts
POST   /api/v1/branches/:name/merge           # Merge (native/auto/cherry_pick/squash)
DELETE /api/v1/branches/:name                 # Archive branch

POST   /api/v1/snapshots                      # Create snapshot (app or native)
GET    /api/v1/time-travel                    # MO {AS OF TIMESTAMP} query
```

## Key Design Decisions

1. **MySQL Protocol** - MatrixOne is MySQL-compatible. Use `aiomysql` async driver.

2. **Branch = Table-level** - MO `DATA BRANCH CREATE TABLE` creates zero-copy table-level branches. Each branch gets suffixed tables (`facts_feature_x`).

3. **Merge is Dual-Strategy** - MO provides native `DATA BRANCH MERGE` with SKIP/ACCEPT conflict strategies. Application layer retains auto/cherry_pick/squash for advanced use cases.

4. **Vector + BM25 Hybrid** - MO `cosine_similarity()` SQL function + `MATCH AGAINST` fulltext for best semantic + keyword matching.

5. **Hooks Over Skills** - Automatic capture via Hooks > manual Skill invocation.

## File Locations

| Component | Path |
|-----------|-------|
| MCP Server | `src/branchedmind/mcp/server.py` |
| Hooks | `src/branchedmind/hooks/*.py` |
| Core Logic | `src/branchedmind/core/` |
| Database | `src/branchedmind/db/models.py`, `src/branchedmind/db/engine.py` |
| REST API | `src/branchedmind/api/app.py` |
| Dashboard | `dashboard/` (React + Vite + React Flow + D3.js + Zustand) |
