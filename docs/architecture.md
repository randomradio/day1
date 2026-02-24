# Architecture

Day1 system design and integration points. Read this when understanding how components connect.

**Last updated**: 2026-02-24

## Layer Architecture

```
┌─────────────────────────────────────────────────────────┐
│            Upper Layer (NOT our concern)                 │
│  Claude Code │ Multi-Agent │ Cursor │ Any MCP Client    │
└──────────────┬──────────────────────┬───────────────────┘
               │                      │
               ▼                      ▼
┌─────────────────────────────────────────────────────────┐
│            Integration Layer                             │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Claude Code   │  │  MCP Server  │  │   REST API   │  │
│  │  Plugin       │  │ (stdio/SSE)  │  │  (FastAPI)   │  │
│  │ (11 Hooks)    │  │  29 tools    │  │  55+ endpts  │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         └──────────────────┼─────────────────┘          │
│                            ▼                             │
│  ┌──────────────────────────────────────────────────┐   │
│  │         Core Engine Layer (19 engines)            │   │
│  │                                                   │   │
│  │  Write:  Fact │ Message │ Observation │ Relation  │   │
│  │  Query:  Search │ Analytics │ SessionManager      │   │
│  │  Branch: BranchMgr │ Merge │ Snapshot             │   │
│  │  Conv:   Conversation │ CherryPick │ Replay       │   │
│  │  Task:   TaskEngine │ Consolidation               │   │
│  │  Eval:   SemanticDiff │ Scoring (LLM-as-judge)    │   │
│  └───────────────────────┬──────────────────────────┘   │
│                          ▼                               │
│  ┌──────────────────────────────────────────────────┐   │
│  │     Infrastructure                                │   │
│  │  Embedding: OpenAI │ Doubao │ Mock                │   │
│  │  LLM:       OpenAI-compatible (for Scoring only)  │   │
│  │  DB:        SQLAlchemy 2.0 async + aiomysql       │   │
│  └───────────────────────┬──────────────────────────┘   │
│                          ▼                               │
│  ┌──────────────────────────────────────────────────┐   │
│  │     MatrixOne Database (Native Capabilities)      │   │
│  │                                                   │   │
│  │  facts, relations, observations   (Layer 2: Memory)│  │
│  │  conversations, messages          (Layer 1: History)│  │
│  │  branch_registry, merge_history   (Metadata)       │  │
│  │  sessions, tasks, task_agents     (Coordination)   │  │
│  │  scores, consolidation_history    (Evaluation)     │  │
│  │  snapshots                        (Time Travel)    │  │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │     Dashboard (React + Vite + Tailwind)           │   │
│  │  BranchTree │ ConversationList │ ConversationThread│  │
│  │  MergePanel │ Timeline │ SearchBar │ FactDetail    │  │
│  │  ReplayList │ SemanticDiffView │ AnalyticsDashboard│  │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## Two-Layer Data Model

Day1 manages two data layers, both participating in the branch infrastructure:

| Layer | Tables | Purpose | Branching |
|-------|--------|---------|-----------|
| **Layer 2 (Memory)** | facts, relations, observations | Structured knowledge with vector embeddings | Yes — via DATA BRANCH |
| **Layer 1 (History)** | conversations, messages | Raw chat history with sequence ordering | Yes — via DATA BRANCH |

All 5 tables (`facts`, `relations`, `observations`, `conversations`, `messages`) are in `BRANCH_TABLES` and participate in branch/diff/merge operations.

## MatrixOne Native Capabilities

| Feature | SQL Syntax | Replaces |
|---------|-----------|----------|
| **Git4Data Branch** | `DATA BRANCH CREATE TABLE t2 FROM t1` | Application-level row copying |
| **Git4Data Diff** | `DATA BRANCH DIFF t2 AGAINST t1` | Application-level fact comparison |
| **Git4Data Merge** | `DATA BRANCH MERGE t2 INTO t1 WHEN CONFLICT SKIP/ACCEPT` | Application-level merge |
| **Fulltext Search** | `MATCH(col) AGAINST('q' IN NATURAL LANGUAGE MODE)` | SQLite FTS5 |
| **Vector Search** | `cosine_similarity(embedding, '[...]')` | In-memory Python cosine |
| **Time Travel** | `SELECT ... FROM t {AS OF TIMESTAMP 'ts'}` | Application-level timestamp filtering |
| **PITR** | `CREATE PITR name FOR DATABASE db RANGE 1 "d"` | JSON snapshot serialization |
| **Snapshot** | `CREATE SNAPSHOT sp FOR DATABASE db` | Application-level JSON dumps |

## Branch Model

Each branch = a set of suffixed tables (zero-copy, CoW via DATA BRANCH):
- **main**: `facts`, `relations`, `observations`, `conversations`, `messages`
- **feature_x**: `facts_feature_x`, `relations_feature_x`, `observations_feature_x`, `conversations_feature_x`, `messages_feature_x`

## Core Engine Layer

### LLM Dependency Map

| Category | Engines | LLM? | Embedding? |
|----------|---------|------|------------|
| Write | FactEngine, MessageEngine, ObservationEngine, RelationEngine | No | Optional (non-blocking) |
| Query | SearchEngine, AnalyticsEngine, SessionManager | No | SearchEngine: for vector search |
| Branch | BranchManager, MergeEngine, SnapshotManager | No | MergeEngine: for conflict detection |
| Conversation | ConversationEngine, ConversationCherryPick, ReplayEngine | No | No |
| Task | TaskEngine, ConsolidationEngine | No | No |
| Evaluation | SemanticDiffEngine, ScoringEngine | **ScoringEngine only** | SemanticDiff: for reasoning comparison |

**Pure memory layer principle**: Only 1 of 19 engines calls LLM directly. Embedding failures are non-blocking — all write engines save content with `embedding=None` on failure and can be backfilled later.

### Merge Strategies

| Strategy | Use Case | Implementation |
|----------|----------|----------------|
| **native** | Simple merges, SKIP/ACCEPT conflicts | MatrixOne `DATA BRANCH MERGE` |
| **auto** | Multi-fact merges with embedding-based conflict detection | Application layer, cosine similarity > 0.85 = conflict |
| **cherry_pick** | Selective item adoption | Copy by ID with conversation/message ID remapping |
| **squash** | Consolidate branch into summary | Summarize + single fact creation |

### Consolidation Pipeline

Three-level hierarchy for distilling observations into knowledge:

```
Session observations → consolidate_session() → candidate facts (Jaccard dedup > 0.85)
Agent facts         → consolidate_agent()   → cross-session dedup + agent summary
Task facts          → consolidate_task()    → durable (≥0.8 confidence) promoted to parent
```

## Integration Points

### 1. MCP Server (29 tools)

Standard interface for any MCP-compatible client. Tool categories:

| Category | Tools | Count |
|----------|-------|-------|
| Memory Write | `memory_write_fact`, `memory_write_observation`, `memory_write_relation` | 3 |
| Search | `memory_search`, `memory_graph_query`, `memory_timeline` | 3 |
| Branch | `memory_branch_create`, `memory_branch_list`, `memory_branch_switch`, `memory_branch_diff`, `memory_branch_merge` | 5 |
| Snapshot | `memory_snapshot`, `memory_snapshot_list`, `memory_time_travel` | 3 |
| Task | `memory_task_create`, `memory_task_join`, `memory_task_status`, `memory_task_update`, `memory_consolidate`, `memory_search_task`, `memory_agent_timeline`, `memory_replay_task_type` | 8 |
| Conversation | `memory_log_message`, `memory_list_conversations`, `memory_search_messages`, `memory_fork_conversation`, `memory_cherry_pick_conversation` | 5 |
| Curation | `memory_branch_create_curated`, `memory_session_context` | 2 |

### 2. Claude Code Plugin (11 Hooks)

Automatic capture — user doesn't call tools manually.

| Hook | Trigger | Purpose |
|------|---------|---------|
| `SessionStart` | Session init | Inject relevant historical memory + task context |
| `SessionEnd` | Session close | Consolidate observations, generate summary |
| `PostToolUse` | After tool call | Compress and store observation |
| `PreCompact` | Before context compress | Extract facts/relations from transcript |
| `Stop` | After response | Generate interim summary |
| `UserPrompt` | User input | Create/continue conversation |
| `AssistantResponse` | LLM response | Record assistant messages |
| `PreToolUse` | Before tool call | Pre-capture tool context |

All hooks are branch-aware (respect `BM_BRANCH` env var) and resilient (embedding failures don't block capture).

### 3. REST API (55+ endpoints across 13 route files)

| Route File | Key Endpoints |
|------------|---------------|
| `facts.py` | POST /facts, GET /facts, GET /facts/{id}, PATCH /facts/{id} |
| `messages.py` | POST /conversations/{id}/messages, GET /messages/search |
| `conversations.py` | POST /conversations, GET /conversations, POST /conversations/{id}/fork, POST /conversations/{id}/cherry-pick, GET /conversations/{a}/diff/{b}, GET /conversations/{a}/semantic-diff/{b} |
| `branches.py` | POST /branches, GET /branches, GET /branches/{name}/diff, POST /branches/{name}/merge, DELETE /branches/{name}, POST /branches/curated |
| `tasks.py` | POST /tasks, GET /tasks, POST /tasks/{id}/join, POST /tasks/{id}/complete, PATCH /tasks/{id}/objectives |
| `sessions.py` | POST /sessions, GET /sessions, POST /sessions/{id}/end |
| `snapshots.py` | POST /snapshots, GET /snapshots, GET /snapshots/{id}/time-travel |
| `observations.py` | POST /observations, GET /observations/timeline |
| `relations.py` | POST /relations, GET /relations/graph |
| `replays.py` | POST /conversations/{id}/replay, GET /replays/{id}/context, GET /replays/{id}/diff, GET /replays/{id}/semantic-diff |
| `search.py` | GET /search, GET /search/observations, GET /search/cross-branch |
| `scores.py` | POST /scores, POST /scores/evaluate, GET /scores/summary |
| `analytics.py` | GET /analytics/overview, GET /analytics/sessions/{id}, GET /analytics/trends |

## Key Design Decisions

1. **MySQL Protocol** — MatrixOne is MySQL-compatible. Use `aiomysql` async driver via SQLAlchemy 2.0.

2. **Branch = Table-level** — MO `DATA BRANCH CREATE TABLE` creates zero-copy table-level branches. 5 tables branched together: facts, relations, observations, conversations, messages.

3. **Merge is Dual-Strategy** — MO native `DATA BRANCH MERGE` for simple cases + application-layer (auto/cherry_pick/squash) for advanced conflict resolution.

4. **Vector + BM25 Hybrid** — MO `cosine_similarity()` SQL function + `MATCH AGAINST` fulltext for best semantic + keyword matching.

5. **Hooks Over Skills** — Automatic capture via Hooks beats manual Skill invocation.

6. **Embedding Never Blocks Writes** — All write engines wrap embedding calls in try/except. Content always saved; embedding is best-effort enrichment. Records with `embedding=None` can be backfilled.

7. **Conversations are First-Class Branch Citizens** — Both Layer 1 (history) and Layer 2 (memory) participate in branching, diffing, and merging. `Conversation.metadata_json` uses `JsonText` (not native JSON) for DATA BRANCH DIFF compatibility.

8. **Only ScoringEngine Calls LLM** — Keeps the memory layer transport-agnostic. Scoring gracefully degrades to 0.5 when LLM unavailable.

## File Locations

| Component | Path |
|-----------|------|
| Core Engines | `src/day1/core/` (19 engines + embedding + llm + exceptions) |
| Database Models | `src/day1/db/models.py` |
| MCP Server | `src/day1/mcp/mcp_server.py` |
| MCP Tools | `src/day1/mcp/tools.py` (29 tools) |
| Hooks | `src/day1/hooks/` (11 hook files) |
| REST API | `src/day1/api/app.py` + `src/day1/api/routes/` (13 route files) |
| Dashboard | `dashboard/` (React + Vite + React Flow + D3.js + Zustand + Tailwind) |
| Tests | `tests/test_core/` (9 test files) + `tests/conftest.py` |
| Config | `src/day1/config.py` |
