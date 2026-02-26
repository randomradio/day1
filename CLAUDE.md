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
Layer 2 (Memory):   facts, relations, observations    — structured knowledge with vector embeddings
Layer 1 (History):  conversations, messages            — raw chat history with sequence ordering
Metadata:           branch_registry, merge_history     — branch lifecycle tracking
Coordination:       sessions, tasks, task_agents       — multi-agent task management
Templates:          template_branches                  — reusable knowledge template registry
Curation:           handoff_records, knowledge_bundles — verified handoffs and portable packages
Evaluation:         scores, consolidation_history      — quality scoring and audit
Time Travel:        snapshots                          — point-in-time recovery
```

All 5 core tables (`facts`, `relations`, `observations`, `conversations`, `messages`) participate in DATA BRANCH operations. Feature branches use suffixed tables (e.g. `facts_feature_x`) created via `DATA BRANCH CREATE TABLE`.

## Progressive Disclosure

**Before starting work**, read relevant docs from `docs/`:

| File | When to read |
|-------|---------------|
| `docs/code_practices.md` | Writing/modifying Python code |
| `docs/development.md` | Setting up env, running tests, building |
| `docs/architecture.md` | Understanding system design, integration points |
| `docs/architecture-decisions.md` | Architecture decisions, discussion log, evolution plans |
| `docs/mcp_tools.md` | Adding/modifying MCP server tools |
| `docs/dashboard.md` | Building/working on frontend dashboard |
| `docs/E2E_TEST_METHODS.md` | Strict API/CLI/MCP E2E method, latest coverage report summary, and warn explanations |
| `docs/E2E_REAL_ACCEPTANCE.md` | Valid-input real acceptance run guide, DB verification manifest, and concrete SQL checks |

## Key Differentiators

Unlike `claude-mem`, Day1 adds: branch/merge, PITR/time-travel, multi-agent isolation, knowledge graph.

## Engine Architecture (26 Core Engines)

| Category | Engines | LLM Dependency |
|----------|---------|----------------|
| Write | FactEngine, MessageEngine, ObservationEngine, RelationEngine | None (embedding only) |
| Query | SearchEngine, AnalyticsEngine, SessionManager | None |
| Branch | BranchManager, MergeEngine, SnapshotManager, BranchTopologyEngine | None |
| Conversation | ConversationEngine, CherryPick, ReplayEngine | None |
| Task | TaskEngine, ConsolidationEngine | None |
| Templates | TemplateEngine | None |
| Curation | **VerificationEngine**, **HandoffEngine**, **KnowledgeBundleEngine** | VerificationEngine only |
| Analysis | SemanticDiffEngine, ScoringEngine | ScoringEngine only |
| Infrastructure | EmbeddingProvider, LLMClient | By design |

**Pure memory layer principle**: Only 2 of 26 engines (ScoringEngine and VerificationEngine) call LLM directly. Both degrade gracefully to heuristic scoring. All others are transport-agnostic.

## Architecture Evolution

Active decisions and roadmap are tracked in `docs/architecture-decisions.md`.

Implemented (2026-02-24):
- **Branch Topology Management** — BranchTopologyEngine: lifecycle policies, auto-archive, TTL expiry, metadata enrichment, hierarchical tree, naming validation
- **Template Branches** — TemplateEngine + TemplateBranch model: create/version/instantiate/find templates, fork-to-start for new agents
- **Knowledge Curation** — VerificationEngine (LLM-as-judge for facts, merge gate), HandoffEngine (structured task handoff with verified facts), KnowledgeBundleEngine (portable export/import)

Knowledge evolution chain: `Raw Execution → Consolidation → Verification → Curation → Template/Bundle → Reuse`

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

---

## Documentation Maintenance Rules

**IMPORTANT**: Follow these rules to keep docs in sync with code.

### E2E Test Policy (Strict, No Bypass)

- API / CLI / MCP E2E checks must be executed strictly (no manual skipping of endpoints/tools).
- Use `scripts/e2e_surface.py` for dynamic surface enumeration plus real-chain validation.
- `scripts/e2e_surface.py` must run the deep API real-agent scenario (`api_agent_real`) in addition to API/CLI/MCP basic real chains.
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
