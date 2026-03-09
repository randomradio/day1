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
| Storage | MatrixOne (Cloud/Docker) — vecf32 + FULLTEXT INDEX |
| MCP Server | `mcp` (official Python SDK) |
| Embedding | OpenAI text-embedding-3-small (configurable: openai/doubao/openrouter/mock) |
| Frontend | React + Vite + Zustand + Tailwind CSS |

## MCP Transport (Current)

- MCP is exposed as HTTP `streamable_http` at FastAPI route `/mcp` (single supported MCP transport).
- Do not document or rely on `stdio` MCP startup for this repo's current runtime path.

## Core Data Model

```
Memory:       memories, memory_relations         — NL text + vector embeddings + knowledge graph
Branch:       branches, snapshots                — branch registry + point-in-time recovery
Sessions:     sessions, hook_logs                — session tracking + raw Claude Code events
Traces:       session_traces, trace_comparisons  — execution traces + scored diffs
Skills:       skill_registry, skill_mutations, evolution_runs — versioned skills + evolution
```

All tables use column-level branching (`branch_name` column). 11 tables total.

## Progressive Disclosure

**Before starting work**, read relevant docs from `docs/`:

| File | When to read |
|-------|---------------|
| `docs/code_practices.md` | Writing/modifying Python code |
| `docs/development.md` | Setting up env, running tests, building |
| `docs/architecture.md` | Understanding system design, integration points |
| `docs/architecture-decisions.md` | Architecture decisions, discussion log, evolution plans |
| `docs/mcp_tools.md` | Adding/modifying MCP server tools |
| `docs/api_reference.md` | REST API endpoints reference |
| `docs/hooks.md` | Claude Code hooks integration |
| `docs/E2E_TEST_METHODS.md` | Strict API/CLI/MCP E2E method, latest coverage report summary, and warn explanations |
| `docs/E2E_REAL_ACCEPTANCE.md` | Valid-input real acceptance run guide, DB verification manifest, and concrete SQL checks |

## Key Differentiators

Unlike `claude-mem`, Day1 adds: branch/merge, PITR/time-travel, multi-agent isolation, knowledge graph.

## Engine Architecture (4 Core Engines)

| Engine | Responsibility | LLM? | Embedding? |
|--------|---------------|------|------------|
| `MemoryEngine` | Write, search, branch, snapshot, merge, graph | No | Yes |
| `TraceEngine` | Extract/store session traces | No | No |
| `ComparisonEngine` | Compare traces (9 dimensions) | Heuristic | No |
| `SkillEvolutionEngine` | Register, evolve, promote skills | No | No |

**Pure memory layer principle**: No engine calls LLM directly. Embedding is the only external dependency, and it degrades gracefully (mock provider available).

---

## Day1 Memory Integration

This project uses Day1 (Day1 v2) MCP tools for persistent memory across sessions.

### Automatic Session Tracking

Every Claude Code session is tracked with a unique `session_id`. Memory operations happen automatically:

- **Memories** are stored via `memory_write`
- **Semantic search** retrieves relevant context via `memory_search`
- **Session events** are captured via Claude Code hooks (see `docs/hooks.md`)

### Key MCP Memory Tools (28 total)

Use these during work:

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `memory_write` | Store a memory (text + context) | After learning decisions, patterns, bugs |
| `memory_search` | Semantic + keyword search | Before starting work, to find context |
| `memory_get` | Get memory by ID | When you need full details |
| `memory_update` | Update memory (re-embeds if text changes) | Correcting or enriching a memory |
| `memory_archive` | Soft-delete a memory | Removing outdated/wrong memories |
| `memory_branch_create` | Create isolated branch | Before experimental changes |
| `memory_branch_switch` | Switch branches | Working on different features |
| `memory_snapshot` | Point-in-time snapshot | Before risky changes |
| `memory_relate` | Create relation between memories | Building knowledge graph |
| `memory_graph` | Graph traversal from a memory | Exploring connected knowledge |
| `memory_timeline` | Chronological history | Reviewing session activity |
| `memory_count` | Count memories on a branch | Quick branch overview |

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
Use memory_write with:
- text: Clear description of what happened
- context: Why / how / outcome
- category: "pattern" | "decision" | "bug_fix" | "architecture"
- confidence: 0.0-1.0
```

### Before Risky Changes

```
# Create snapshot to revert if needed
Use memory_snapshot with label describing the change
```

---

## Documentation Maintenance Rules

**IMPORTANT**: Follow these rules to keep docs in sync with code.

### E2E Test Policy (Strict, No Bypass)

- API / CLI / MCP E2E checks must be executed strictly (no manual skipping of endpoints/tools).
- Use `scripts/e2e_surface.py` for dynamic surface enumeration plus real-chain validation.
- `scripts/e2e_surface.py` must run the deep API real-agent scenario (`api_agent_real`) in addition to API/CLI/MCP basic real chains.
- MCP E2E (`mcp_surface` / `mcp_real`) must run through HTTP MCP (`/mcp`, `streamable_http`) and must not fall back to direct dispatch or `stdio`.
- Release-style acceptance should use `scripts/e2e_surface.py --real-only` and preserve `docs/e2e_real_acceptance_latest.json` plus DB manifest artifacts.
- Preserve the latest machine-readable report in `docs/e2e_surface_latest_report.json`.
- Surface `warn` is allowed only when it matches the explicit strict baseline in `scripts/e2e_surface.py`; otherwise treat it as `fail`.
- Every `warn` in surface mode must be explained in `docs/E2E_TEST_METHODS.md`.
- Any `fail` in E2E surface/real sections must be fixed and rerun before release.

### When to Update CLAUDE.md

- After adding/removing engines, MCP tools, or API route files
- After changing the data model (new tables, new columns)
- After architectural decisions that affect the system design
- After completing a major feature or phase

### When to Update docs/architecture-decisions.md

- After any architecture discussion or decision
- When deferring a feature — record why
- When encountering and fixing a bug — record the pattern to prevent recurrence
- Use timestamp format: `## YYYY-MM-DD: [Topic]`

### When to Update docs/architecture.md

- After adding/removing integration points (engines, tools, endpoints, hooks)
- After changing the branch model or data layer structure
- After file path changes (renames, moves)

### Error Log & Lessons Learned

Record mistakes here to avoid repeating them:

| Date | Error | Root Cause | Prevention |
|------|-------|------------|------------|
| 2026-02-24 | `docs/architecture.md` had stale `branchedmind/` paths for months | Rename refactor didn't update docs | Always grep docs/ after file renames |
| 2026-02-24 | `docs/plan.md` still showed "planned" for implemented phases | No habit of marking completed work in docs | Mark phases done immediately after commit |
| 2026-02-24 | `docs/mcp_tools.md` only listed 12 of 29 tools | New tools added without doc updates | Update mcp_tools.md when adding tools to tools.py |
