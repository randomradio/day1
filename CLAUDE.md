# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: Day1 (Day1 v2 Memory Layer)

**WHAT**: A Git-like memory layer for AI agents - managing writes, retrieval, branching, merging, snapshots, and time-travel.

**WHY**: Pure memory layer independent of upper layer. Works with single Claude Code session, multi-agent systems, Cursor/Copilot, or any MCP-compatible client.

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ |
| Framework | FastAPI (async, type-safe) |
| Database | SQLAlchemy 2.0 (async) + aiomysql |
| Storage | MatrixOne (Cloud/Docker) — vecf32 + FULLTEXT INDEX + git4data (DATA BRANCH) + PITR |
| MCP Server | `mcp` (official Python SDK) |
| LLM | Claude API (Anthropic SDK) |
| Embedding | OpenAI text-embedding-3-small |
| Frontend | React + Vite + React Flow + D3.js + Zustand + Tailwind CSS |

## Core Data Model

```
facts              - Structured facts with vector embeddings
relations          - Entity relationship graph
observations       - Tool call observation records
sessions           - Session tracking
branch_registry    - Branch registry
merge_history      - Audit trail for merges
```

Main branch uses base tables (`facts`, `relations`, `observations`). Feature branches use suffixed tables (e.g. `facts_feature_x`, `relations_feature_x`) created via `DATA BRANCH CREATE TABLE`.

## Progressive Disclosure

**Before starting work**, read relevant docs from `docs/`:

| File | When to read |
|-------|---------------|
| `docs/code_practices.md` | Writing/modifying Python code |
| `docs/development.md` | Setting up env, running tests, building |
| `docs/architecture.md` | Understanding system design, integration points |
| `docs/mcp_tools.md` | Adding/modifying MCP server tools |
| `docs/dashboard.md` | Building/working on frontend dashboard |

## Key Differentiators

Unlike `claude-mem`, Day1 adds: branch/merge, PITR/time-travel, multi-agent isolation, knowledge graph.

---

**Full design document**: `branched-memory-v2-pure-memory-layer.md`

---

## Day1 Memory Integration

This project uses Day1 (Day1 v2) MCP tools for persistent memory across sessions.

### Automatic Session Tracking

Every Claude Code session is tracked with a unique `session_id`. Memory operations happen automatically:

- **Session facts** are stored via `memory_write_fact`
- **Tool observations** are captured via `memory_write_observation`
- **Semantic search** retrieves relevant context via `memory_search`

### Key MCP Memory Tools

Use these during work:

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `memory_write_fact` | Store structured facts | After learning decisions, patterns, bugs |
| `memory_search` | Semantic + keyword search | Before starting work, to find context |
| `memory_graph_query` | Query entity relationships | Exploring connections between components |
| `memory_branch_create` | Create isolated branch | Before experimental changes |
| `memory_branch_switch` | Switch branches | Working on different features |
| `memory_snapshot` | Point-in-time snapshot | Before risky changes |
| `memory_timeline` | Chronological history | Reviewing session activity |

### Initialization

**No manual init needed** - The first session automatically:
- Creates "main" branch
- Registers the current session
- Makes memory tools available

Just start working - memory is automatic!

### Before Starting Work

```
# Search for relevant context from prior sessions
Use memory_search with query describing your task
```

### After Learning Something

```
# Store for future reference
Use memory_write_fact with:
- fact_text: Clear description
- category: "pattern" | "decision" | "bug_fix" | "architecture"
- confidence: 0.0-1.0
```

### Before Risky Changes

```
# Create snapshot to revert if needed
Use memory_snapshot with label describing the change
```
