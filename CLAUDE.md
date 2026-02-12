# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BranchedMind v2 is a **conceptual design** for a Git-like memory layer system for AI agents. Currently this repository contains only design documentation - no implementation exists yet.

### Core Concept

BranchedMind is a "pure memory layer" that manages memory lifecycle (write, retrieve, branch, merge, snapshot, time-travel) independent of the underlying agent system. Think: "Git for Agent Memory."

### Design Philosophy (from the document)

- **Does not care about the upper layer** - could be 1 Claude Code session, 20 parallel agents, Cursor/Copilot, or any AI agent
- **Only cares about memory lifecycle** - writes, retrieval, branching, merging, snapshots, time travel
- **Exposes capabilities via standard interfaces** - MCP Server + Claude Code Plugin + REST API
- **Naturally covers all scenarios** - single-agent persistent memory, multi-agent shared memory, memory branching and merging

## Planned Architecture

### Tech Stack

- **Language**: Python 3.11+
- **Framework**: FastAPI (async, type-safe, modern)
- **Database**: SQLAlchemy 2.0 (async ORM) + pymysql (MySQL protocol driver)
- **MCP Server**: `mcp` (official Python SDK)
- **MatrixOne**: Docker - built-in Vector + BM25 + Branch + PITR (MySQL-compatible)
- **LLM**: Claude API (fact extraction, conflict resolution, observation compression)
- **Embedding**: OpenAI text-embedding-3-small or local models
- **Plugin**: Claude Code Plugin format (.claude-plugin/)

### Core Data Model (Planned)

```
facts              - Structured facts with vector embeddings
relations          - Entity relationship graph
observations       - Tool call observation records
sessions           - Session tracking
branch_registry    - Branch registry
merge_history      - Audit trail for merges
```

All branches share the same schema. `main_memory` is the default branch, `branch_*` are created via CLONE.

### Integration Layers (Planned)

1. **MCP Server** - Primary integration point for any MCP-compatible client
   - Tools: `memory_write_fact`, `memory_search`, `memory_branch_create`, `memory_branch_merge`, etc.
   - Supports stdio/SSE/HTTP modes

2. **Claude Code Plugin** - Automatic memory capture via Hooks
   - SessionStart: Inject historical memory context
   - PostToolUse: Capture each tool call asynchronously
   - PreCompact: Extract facts before context compression
   - Stop/SessionEnd: Generate summaries

3. **REST API** - General HTTP interface for dashboards, external tools, CI/CD

## Key Differentiators from Existing Solutions

Unlike `claude-mem` (18k stars), BranchedMind adds:
- Branch/merge capability
- PITR (Point-In-Time Recovery) / time travel
- Multi-agent memory isolation
- Structured knowledge graph
- MatrixOne native vector + BM25 (no Chroma dependency)

## Document Contents

The main design document `branched-memory-v2-pure-memory-layer.md` contains:
- Detailed architecture diagrams
- SQL schema definitions
- MCP tool specifications
- Hook implementation examples
- Usage scenarios (single agent, multi-agent, cross-project)
- 72-hour MVP implementation plan
- Comparison with v1 design

---

## Code Practices

### Python Style Guide
- Follow [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
- **Linter**: `ruff` (fast, Google-style compatible)
- **Formatter**: `black` (line length 88, consistent formatting)
- **Type checker**: `mypy` strict mode
- **Test runner**: `pytest` with `pytest-asyncio`

### Project Structure
```
branchedmind/
├── src/                    # Application code
│   ├── api/              # FastAPI endpoints
│   ├── core/             # Business logic
│   ├── db/               # Database layer
│   ├── mcp/              # MCP server
│   └── hooks/            # Claude Code hooks
├── tests/                 # All tests (co-located with src structure)
├── pyproject.toml         # Project config
└── CLAUDE.md
```

### Naming Conventions
- **Modules**: `lowercase_with_underscores` (e.g., `memory_client.py`)
- **Classes**: `CapitalizedWords` (e.g., `MemoryClient`)
- **Functions/Methods**: `lowercase_with_underscores` (e.g., `write_fact()`)
- **Constants**: `UPPERCASE_WITH_UNDERSCORES` (e.g., `DEFAULT_BRANCH`)
- **Private**: `_leading_underscore` (e.g., `_embed_text()`)

### Docstring Style (Google Style)
```python
def write_fact(fact_text: str, category: str | None = None) -> Fact:
    """Write a new fact to memory.

    Args:
        fact_text: The natural language description of the fact.
        category: Optional category (bug_fix, architecture, preference, etc.)

    Returns:
        The created Fact object with generated ID and timestamp.

    Raises:
        DatabaseError: If the write operation fails.
    """
    pass
```

### Type Annotations
- **All functions** must have type hints
- Use `X | Y` syntax for unions (Python 3.10+)
- Use `typing.Protocol` for interfaces
- Avoid `Any` - use `object` or specific types

### Error Handling
- Define custom exceptions in `src/core/exceptions.py`
- Raise specific exceptions, never generic `Exception`
- Use context managers for resources
- Document exceptions in docstrings (Raises section)

### Testing
- Use `pytest` with `pytest-asyncio`
- Aim for 80%+ coverage on core logic
- Test behavior, not implementation

---

## Development Commands

### Environment Setup
```bash
# Install development dependencies
pip install -e ".[dev]"

# Start MatrixOne (Docker)
docker run -d -p 6001:6001 matrixorigin/matrixone:latest

# Run database migrations
python -m scripts.migrate

# Start MCP server (stdio mode)
python -m branchedmind.mcp.server

# Start MCP server (SSE mode for testing)
uvicorn branchedmind.mcp.server_http:app --reload

# Run FastAPI with auto-reload
uvicorn branchedmind.api:app --reload --port 8000
```

### Testing
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/core/test_fact_engine.py

# Run with coverage
pytest --cov=src --cov-report=html

# Type checking
mypy src

# Linting
ruff check src

# Format code
black src tests
```

### Pre-commit
```bash
# Install pre-commit hooks
pre-commit install

# Run manually
pre-commit run --all-files
```
