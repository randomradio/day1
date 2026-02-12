# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: BranchedMind v2

**WHAT**: A Git-like memory layer for AI agents - managing writes, retrieval, branching, merging, snapshots, and time-travel.

**WHY**: Pure memory layer independent of upper layer. Works with single Claude Code session, multi-agent systems, Cursor/Copilot, or any MCP-compatible client.

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ |
| Framework | FastAPI (async, type-safe) |
| Database | SQLAlchemy 2.0 (async) + pymysql |
| Storage | MatrixOne (Docker) - MySQL-compatible, Vector + BM25 + Branch + PITR |
| MCP Server | `mcp` (official Python SDK) |
| LLM | Claude API (Anthropic SDK) |
| Embedding | OpenAI text-embedding-3-small |

## Core Data Model

```
facts              - Structured facts with vector embeddings
relations          - Entity relationship graph
observations       - Tool call observation records
sessions           - Session tracking
branch_registry    - Branch registry
merge_history      - Audit trail for merges
```

All branches share same schema. `main_memory` = default, `branch_*` = created via CLONE.

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

Unlike `claude-mem`, BranchedMind adds: branch/merge, PITR/time-travel, multi-agent isolation, knowledge graph.

---

**Full design document**: `branched-memory-v2-pure-memory-layer.md`
