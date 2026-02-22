# Day1

Git-like memory layer for AI agents — branching, merging, snapshots, time-travel, and semantic search.

Powered by [MatrixOne](https://matrixorigin.io) (vecf32 + FULLTEXT INDEX + DATA BRANCH + PITR).

## Quick Start (Docker)

One command to run everything:

```bash
cp .env.example .env          # edit API keys as needed
docker compose up --build
```

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:3000 |
| REST API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Health | http://localhost:8000/health |

Run the smoke test to verify:

```bash
./scripts/smoke_test.sh
```

## Quick Start (Local Dev)

```bash
# Prerequisites: Python 3.11+, Node 22+, MatrixOne running on port 6001
uv sync --all-extras
cp .env.example .env           # configure DB URL + embedding provider

# Start API
uv run uvicorn day1.api.app:app --reload --port 8000

# Start dashboard (separate terminal)
cd dashboard && npm install && npm run dev
```

## Architecture

```
Clients (Claude Code / Cursor / Dashboard / Any MCP Client)
    |
    +-- MCP Server (50+ tools, stdio transport)
    |
    +-- REST API (FastAPI, 65+ endpoints)
            |
            +-- 19 Core Engines (fact, branch, merge, replay, search, ...)
            |
            +-- MatrixOne Database
                +-- Branch-enabled tables (facts, relations, observations)
                +-- DATA BRANCH (zero-copy fork, row-level diff, native merge)
                +-- PITR / Time-travel ({AS OF TIMESTAMP})
                +-- Hybrid search (FULLTEXT BM25 + vecf32 cosine)
```

## Key Features

- **Branch & Merge** -- Zero-copy forks via MatrixOne DATA BRANCH. Auto/cherry-pick/squash/native merge strategies.
- **Semantic Search** -- Hybrid BM25 + vector search with temporal decay scoring.
- **Conversation History** -- Full message capture, fork at any point, replay with parameter overrides.
- **3-Layer Semantic Diff** -- Compare agent runs by actions, reasoning, and outcomes.
- **LLM-as-Judge Scoring** -- Evaluate conversation quality on arbitrary dimensions.
- **Multi-Agent Tasks** -- Create tasks with objectives, assign agents with isolated branches, merge results.
- **Time Travel** -- Query facts at any historical timestamp via MatrixOne PITR.
- **MCP-First** -- 50+ tools exposed via Model Context Protocol for any compatible client.

## Security

```bash
# Optional: protect API with a Bearer token
BM_API_KEY=your-secret-key     # Empty = open access (dev mode)

# Optional: rate limiting
BM_RATE_LIMIT=120              # Requests per minute per IP (0 = disabled)

# Optional: restrict CORS origins
BM_CORS_ORIGINS='["http://localhost:3000"]'
```

Dashboard passes the API key automatically via `?key=` query param or `localStorage`.

## Documentation

| Doc | Description |
|-----|-------------|
| [docs/architecture.md](docs/architecture.md) | System design and integration points |
| [docs/development.md](docs/development.md) | Dev environment setup, running tests |
| [docs/code_practices.md](docs/code_practices.md) | Code style and conventions |
| [docs/mcp_tools.md](docs/mcp_tools.md) | MCP tool reference |
| [docs/dashboard.md](docs/dashboard.md) | Dashboard development guide |
| [docs/plan.md](docs/plan.md) | Implementation plan and roadmap |

## License

Private.
