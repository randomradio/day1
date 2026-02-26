# Day1

Git-like memory layer for AI agents — branching, merging, snapshots, time-travel, and semantic search.

Powered by [MatrixOne](https://matrixorigin.io) (vecf32 + FULLTEXT INDEX + DATA BRANCH + PITR).

## Quick Start (Docker)

One command to run everything:

```bash
cp .env.example .env          # edit API keys as needed
docker compose up -d --build
```

| Service | URL |
|---------|-----|
| Dashboard (Nginx) | http://localhost:9904 |
| REST API | http://localhost:9903 |
| API Docs | http://localhost:9903/docs |
| Health | http://localhost:9903/health |

Verify Docker services:

```bash
docker compose ps
curl -s http://127.0.0.1:9903/health
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:9904/
```

Run the API smoke test against the Docker API port:

```bash
./scripts/smoke_test.sh http://127.0.0.1:9903
```

### MCP in Docker (stdio, no TCP port)

Day1 MCP currently uses `stdio` transport. It is not an HTTP service and does not expose a port.

Run it inside the Docker `api` container on demand:

```bash
docker compose exec -T api python -m day1.mcp.mcp_server
```

This command is what your MCP client (for example Claude Code) should execute.

### Remote Client Access (Host → Client)

If your client machine can reach the host machine:

- Dashboard: `http://<HOST_IP>:9904`
- API: `http://<HOST_IP>:9903`
- API Docs: `http://<HOST_IP>:9903/docs`

For MCP, use SSH to launch the stdio server on the host (inside Docker):

```json
{
  "mcpServers": {
    "day1": {
      "command": "ssh",
      "args": [
        "user@HOST",
        "cd /home/momo/src/day1 && docker compose exec -T api python -m day1.mcp.mcp_server"
      ]
    }
  }
}
```

## Quick Start (Local Dev)

```bash
# Prerequisites: Python 3.11+, Node 22+, MatrixOne running on port 6001
uv sync --all-extras
cp .env.example .env           # configure DB URL + embedding provider

# Verify DB
uv run scripts/check_db.py

# Start API (terminal A)
uv run uvicorn day1.api.app:app --reload --port 8000

# Start dashboard (terminal B)
cd dashboard && npm install && npm run dev

# CLI health check (terminal C)
uv run day1 health --format json
```

## Local Usage (API / CLI / MCP)

### REST API

- Docs: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health`

Example:

```bash
curl -s http://127.0.0.1:8000/health | jq
```

### CLI

```bash
uv run day1 branch create demo/local --parent main --format json
uv run day1 write-fact "Local test fact" --branch demo/local --category test --format json
uv run day1 search "Local test" --branch demo/local --search-type keyword --format json
uv run day1 snapshot create --branch demo/local --label local-check --format json
uv run day1 time-travel 2099-01-01T00:00:00Z --branch demo/local --format json
```

### MCP Server (stdio)

```bash
uv run python -m day1.mcp.mcp_server
```

See tool reference in `docs/mcp_tools.md`.

Docker variant (runs the same MCP server inside the `api` container):

```bash
docker compose exec -T api python -m day1.mcp.mcp_server
```

## Testing: Real Acceptance vs Negative Surface

Two test modes are intentionally separated:

- `Real acceptance` (valid inputs only, release-style): simulates real agent + human dialogue/task workflows and writes persistent data you can verify in DB.
- `Negative surface` (contract safety): enumerates every endpoint/tool with synthetic invalid inputs and checks error handling (`4xx` mapping, no `500`).

### Real Acceptance (Recommended for local validation)

```bash
export BM_DATABASE_URL='mysql+aiomysql://root:111@127.0.0.1:6001/day1'
export BM_TEST_DATABASE_URL='mysql+aiomysql://root:111@127.0.0.1:6001/day1'
export BM_EMBEDDING_PROVIDER=mock BM_RATE_LIMIT=0 BM_LOG_LEVEL=CRITICAL

uv run python scripts/e2e_surface.py --real-only --output docs/e2e_real_acceptance_latest.json
```

Artifacts produced:

- `docs/e2e_real_acceptance_latest.json` (run report, valid inputs only)
- `docs/e2e_real_acceptance_db_manifest.json` (machine-readable DB verification manifest)
- `docs/E2E_REAL_ACCEPTANCE.md` (human verification guide with concrete SQL)

### Strict Surface + Real (full contract coverage)

```bash
uv run python scripts/e2e_surface.py --output docs/e2e_surface_latest_report.json
```

This includes negative/synthetic input coverage. See `docs/E2E_TEST_METHODS.md` for warn explanations.

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
| [docs/E2E_REAL_ACCEPTANCE.md](docs/E2E_REAL_ACCEPTANCE.md) | Valid-input real acceptance guide + DB verification SQL |
| [docs/E2E_TEST_METHODS.md](docs/E2E_TEST_METHODS.md) | Strict surface/contract E2E method and warn baselines |
| [docs/dashboard.md](docs/dashboard.md) | Dashboard development guide |
| [docs/plan.md](docs/plan.md) | Implementation plan and roadmap |

## License

Private.
