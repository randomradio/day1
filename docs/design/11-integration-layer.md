# Integration Layer

> MCP Server, REST API, Claude Code Hooks, CLI — the four surfaces that expose Day1's 26 engines.

## Design Principle

All four integration surfaces call the same core engines. **No business logic lives in the integration layer** — it is pure routing, parameter mapping, and response formatting.

```
┌──────────────────────────────────────────────────────┐
│                INTEGRATION SURFACES                    │
│                                                        │
│  ┌──────────┐  ┌──────────┐  ┌──────┐  ┌──────────┐│
│  │  Hooks   │  │   MCP    │  │ REST │  │   CLI    ││
│  │ 11 hooks │  │ 8 tools  │  │85+eps│  │ 20+ cmds ││
│  │ automatic│  │ on-demand│  │ CRUD │  │ terminal ││
│  └────┬─────┘  └────┬─────┘  └──┬───┘  └────┬─────┘│
│       │              │           │            │      │
│       │     Same 26 Core Engines               │      │
│       │              │           │            │      │
│       └──────────────┴───────────┴────────────┘      │
└──────────────────────────────────────────────────────┘
```

---

## MCP Server (8 Tools, HTTP streamable_http)

**Source**: `src/day1/mcp/tools.py`, `src/day1/mcp/mcp_server.py`

### Transport

- Protocol: MCP Streamable HTTP
- Endpoint: `/mcp` (mounted as ASGI sub-application)
- Methods: GET, POST, DELETE
- Session tracking: Per-session branch state via `MCP_SESSION_ID_HEADER`

### Tool Catalog

| Tool | Purpose | Key Parameters |
|---|---|---|
| `memory_write` | Store a memory | text (required), context, file_context, session_id, branch |
| `memory_search` | Search memories | query (required), file_context, branch, limit |
| `memory_branch_create` | Create branch | branch_name (required), parent, description |
| `memory_branch_switch` | Switch active branch | branch_name (required) |
| `memory_branch_list` | List branches | status |
| `memory_snapshot` | Create snapshot | label, branch |
| `memory_snapshot_list` | List snapshots | branch |
| `memory_restore` | Restore snapshot | snapshot_id (required) |

### NL-First Design

MCP tools use **natural language parameters** — no structured categories, no enums. The agent writes what it knows in natural language, and the engine handles categorization and structuring internally.

```
memory_write:
  text: "The auth middleware needs to check both Bearer and API key headers"
  context: "Discovered while debugging the 401 errors in the integration tests"
  file_context: "src/day1/api/app.py"
```

### Session Branch State

Each MCP session maintains its own active branch:

```python
_active_branches_by_session: dict[str, str] = {}

# memory_branch_switch updates the session's active branch
# All subsequent operations use that branch
```

This enables multi-agent scenarios where each agent's MCP session operates on its own branch.

### Request Flow

```
MCP Client → POST /mcp
    │
    ├──→ ASGI handler extracts MCP session ID from header
    │
    ├──→ StreamableHTTPSessionManager.handle_request()
    │
    ├──→ @app.call_tool() → dispatch_tool_call(name, args, session_id)
    │
    ├──→ Resolve active branch for session
    │
    ├──→ handle_tool_call(name, args, get_branch, set_branch)
    │
    ├──→ Create DB session → Create engine → Execute operation
    │
    └──→ Return TextContent result to MCP client
```

---

## REST API (85+ Endpoints, FastAPI)

**Source**: `src/day1/api/app.py`, `src/day1/api/routes/*.py`

### Route Organization

| Route File | Prefix | Endpoints | Engines Used |
|---|---|---|---|
| `facts.py` | `/facts` | 5 | FactEngine |
| `observations.py` | `/observations` | 3 | ObservationEngine |
| `relations.py` | `/relations` | 3 | RelationEngine |
| `messages.py` | `/messages`, `/conversations/*/messages` | 5 | MessageEngine |
| `conversations.py` | `/conversations` | 7 | ConversationEngine, SemanticDiffEngine |
| `branches.py` | `/branches` | 7 | BranchManager, MergeEngine |
| `branch_topology.py` | `/branches` | 6 | BranchTopologyEngine |
| `snapshots.py` | `/snapshots`, `/time-travel` | 5 | SnapshotManager |
| `sessions.py` | `/sessions` | 3 | SessionManager |
| `search.py` | `/facts/search`, `/observations/search` | 3 | SearchEngine |
| `tasks.py` | `/tasks`, `/agents` | 10 | TaskEngine, ConsolidationEngine |
| `replays.py` | `/replays` | 6 | ReplayEngine |
| `analytics.py` | `/analytics` | 5 | AnalyticsEngine |
| `scores.py` | `/scores` | 4 | ScoringEngine |
| `verification.py` | `/verification`, `/facts/*/verify` | 6 | VerificationEngine |
| `handoffs.py` | `/handoffs` | 3 | HandoffEngine |
| `bundles.py` | `/bundles` | 5 | KnowledgeBundleEngine |
| `templates.py` | `/templates` | 7 | TemplateEngine |
| `ingest.py` | `/ingest` | 4 | Multiple (MCP wrapper) |

### Middleware Stack

```
Request
    │
    ├──→ CORS Middleware (allow all origins in dev)
    │
    ├──→ Rate Limit Middleware (per-IP, 60/min)
    │       └──→ Exempts: /health, /mcp/*
    │
    ├──→ API Key Auth (Bearer token, optional)
    │       └──→ Exempts: /health, /mcp
    │
    └──→ Route Handler → Engine → DB → Response
```

### Dependency Injection

```python
@router.post("/facts")
async def create_fact(
    body: FactCreateRequest,
    session: AsyncSession = Depends(get_session),
):
    embedder = get_embedding_provider()
    engine = FactEngine(session, embedder)
    return await engine.write_fact(**body.dict())
```

---

## Claude Code Hooks (11 Hooks)

**Source**: `src/day1/hooks/*.py`

### Hook Architecture

Hooks are shell scripts invoked by Claude Code at specific lifecycle events. They run as subprocesses of Claude Code — trusted, local, zero-auth.

```
┌──────────────────────────────────────────────────────┐
│             HOOK ARCHITECTURE                         │
│                                                        │
│  Claude Code Process                                   │
│       │                                                │
│       ├──→ SessionStart   → hooks/session_start.py    │
│       │                    [Inject prior context]      │
│       │                                                │
│       ├──→ UserPrompt     → hooks/user_prompt.py      │
│       │                    [Record user input]         │
│       │                                                │
│       ├──→ PreToolUse     → hooks/pre_tool_use.py     │
│       │                    [Pre-context capture]       │
│       │                                                │
│       ├──→ PostToolUse    → hooks/post_tool_use.py    │
│       │                    [Observation + message]     │
│       │                                                │
│       ├──→ AssistantResp  → hooks/assistant_response.py│
│       │                    [Record agent response]     │
│       │                                                │
│       ├──→ PreCompact     → hooks/pre_compact.py      │
│       │                    [Extract facts before       │
│       │                     context window compress]   │
│       │                                                │
│       ├──→ Stop           → hooks/stop.py             │
│       │                    [Interim summary]           │
│       │                                                │
│       └──→ SessionEnd     → hooks/session_end.py      │
│                            [Consolidation]             │
│                                                        │
│  Environment Context:                                  │
│  BM_BRANCH, BM_TASK_ID, BM_AGENT_ID,                 │
│  BM_PARENT_SESSION, CLAUDE_CODE_SESSION_ID            │
└──────────────────────────────────────────────────────┘
```

### Zero-Config Design

Hooks require **zero user configuration**:
- Session ID from `CLAUDE_CODE_SESSION_ID` environment variable
- Branch from `BM_BRANCH` (defaults to "main")
- Database connection from `.env` file
- Embedding from configured provider (degrades to mock)

### Graceful Degradation

Every hook follows this pattern:
```python
async with get_db_session() as session:
    if session is None:
        return {}  # DB unavailable → skip silently
    try:
        # ... do work ...
    except Exception as e:
        _debug_log(f"Hook error: {e}")
        return {}  # Any error → skip silently
```

Hooks **never block** Claude Code. They return quickly (async where possible) and fail silently.

---

## CLI

**Source**: `src/day1/cli.py`, `src/day1/cli/commands/*.py`

### Command Structure

```
day1
├── write-fact <text>          # FactEngine
├── write-observation <summary> # ObservationEngine
├── write-relation <src> <type> <tgt> # RelationEngine
├── search <query>             # SearchEngine
├── graph-query <entity>       # RelationEngine
├── timeline                   # Observation timeline
├── branch
│   ├── create <name>          # BranchManager
│   ├── list                   # BranchManager
│   ├── switch <name>          # Local branch state
│   ├── diff <src> <tgt>       # MergeEngine
│   └── merge <src>            # MergeEngine
├── snapshot
│   ├── create                 # SnapshotManager
│   ├── list                   # SnapshotManager
│   └── restore <id>           # SnapshotManager
├── api [--host] [--port]      # Start FastAPI server
├── dashboard                  # Start React dashboard
├── migrate                    # Run DB migrations
├── init                       # Initialize DB + main branch
├── health                     # Check API health
└── test                       # Run MatrixOne tests
```

---

## Entry Point Matrix

Complete mapping from every integration surface to every engine:

| Engine | MCP | API | Hook | CLI |
|---|---|---|---|---|
| FactEngine | `memory_write` | `POST /facts` | PreCompact, SessionEnd (via Consolidation) | `write-fact` |
| MessageEngine | — | `POST .../messages` | UserPrompt, AssistantResponse, PostToolUse | — |
| ObservationEngine | — | `POST /observations` | PostToolUse | `write-observation` |
| RelationEngine | — | `POST /relations` | — | `write-relation` |
| SearchEngine | `memory_search` | `GET /facts/search` | SessionStart (context) | `search` |
| AnalyticsEngine | — | `GET /analytics/*` | — | — |
| SessionManager | — | `GET /sessions/*` | SessionStart, SessionEnd | — |
| BranchManager | `memory_branch_create/list` | `POST/GET /branches` | — | `branch create/list` |
| MergeEngine | — | `POST /branches/*/merge` | — | `branch merge` |
| SnapshotManager | `memory_snapshot/*` | `POST/GET /snapshots` | — | `snapshot *` |
| BranchTopologyEngine | — | `GET /branches/topology` | — | — |
| ConversationEngine | — | `POST/GET /conversations` | SessionStart, SessionEnd | — |
| CherryPick | — | `POST .../cherry-pick` | — | — |
| ReplayEngine | — | `POST .../replay` | — | — |
| TaskEngine | — | `POST/GET /tasks` | SessionStart (context) | — |
| ConsolidationEngine | — | `POST /tasks/*/consolidate` | SessionEnd | — |
| TemplateEngine | — | `POST/GET /templates` | — | — |
| VerificationEngine | — | `POST /facts/*/verify` | — | — |
| HandoffEngine | — | `POST/GET /handoffs` | — | — |
| KnowledgeBundleEngine | — | `POST/GET /bundles` | — | — |
| SemanticDiffEngine | — | `GET .../semantic-diff` | — | — |
| ScoringEngine | — | `POST .../evaluate` | — | — |

---

## Discussion

1. **MCP tool count**: Currently 8 NL-first tools. The full API has 85+ endpoints. Which additional operations should be exposed as MCP tools?
2. **Hook performance**: Hooks are subprocesses — each invocation has startup cost. Can we batch or optimize?
3. **API versioning**: Currently all routes are unversioned. Should we add `/api/v1/` prefix?
4. **WebSocket/SSE**: Dashboard currently polls API. Should we add real-time push for live updates?
5. **GraphQL**: Would a GraphQL endpoint serve the dashboard better than REST for complex queries?
