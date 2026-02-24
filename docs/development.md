# Development Commands

Commands for setting up, running, and testing Day1. Read this when setting up env or running builds/tests.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (package manager)
- Node.js 18+ (for dashboard)

## Environment Setup

```bash
# Clone and navigate
git clone git@github.com:randomradio/day1.git
cd day1

# Install all dependencies (creates .venv automatically)
uv sync --all-extras
```

## MatrixOne Database

### Option A: MO Cloud (Default)

The default connection is pre-configured in `config.py`. No env vars needed to get started.

```bash
# Verify MO features (uses default connection)
uv run python scripts/test_mo_features.py

# Or connect directly via mycli/mysql for debugging
mycli -h freetier-01.cn-hangzhou.cluster.matrixonecloud.cn -P 6001 \
  -u "0193bd50-818d-76ba-bb43-a2abd031d6e5:admin:accountadmin" \
  -p"AIcon2024" day1

# Override connection via env var if needed
export BM_DATABASE_URL="mysql+aiomysql://0193bd50-818d-76ba-bb43-a2abd031d6e5%3Aadmin%3Aaccountadmin:AIcon2024@freetier-01.cn-hangzhou.cluster.matrixonecloud.cn:6001/day1"
```

### Option B: Local Docker

```bash
# Start MatrixOne (Docker)
docker run -d -p 6001:6001 --name matrixone matrixorigin/matrixone:latest

# Wait for MatrixOne to be ready
docker logs -f matrixone

# Set connection string (local)
export BM_DATABASE_URL="mysql+aiomysql://root:111@127.0.0.1:6001/day1"

# Connect directly (for debugging)
docker exec -it matrixone mysql -h 127.0.0.1 -P 6001 -uroot -p111
```

## Quick Start (run.sh)

```bash
# One-command: install + test MO + start API + start dashboard
bash scripts/run.sh all

# Or run individual commands:
bash scripts/run.sh install     # uv sync --all-extras
bash scripts/run.sh test        # Verify MO connection & features
bash scripts/run.sh api         # Start FastAPI server (:8000)
bash scripts/run.sh dashboard   # Start React dashboard (:5173)
```

## Running Services (Manual)

```bash
# FastAPI REST API
uv run uvicorn day1.api.app:app --reload --port 8000

# FastAPI with debug
uv run uvicorn day1.api.app:app --reload --port 8000 --log-level debug

# MCP server (stdio mode) - for Claude Code integration
uv run python -m day1.mcp.mcp_server

# MCP server (SSE mode) - for testing/debug
uv run uvicorn day1.mcp.mcp_server_http:app --reload --port 3001
```

## Dashboard (Frontend)

```bash
# Install and start dashboard dev server
cd dashboard
npm install
npm run dev     # http://localhost:5173 (proxies /api to :8000)

# Build for production
npm run build

# Type check
npx tsc --noEmit
```

## Database Operations

```bash
# Verify MO features (branch/diff/merge/vector/fulltext/time-travel)
uv run python scripts/test_mo_features.py

# Run migrations
uv run python -m scripts.migrate

# Create snapshot (native MO)
curl -X POST http://localhost:8000/api/v1/snapshots -H 'Content-Type: application/json' -d '{"native": true, "label": "before-refactor"}'
```

## Testing

```bash
# Run all tests (requires MO connection)
uv run pytest

# Run specific test
uv run pytest tests/test_core/test_fact_engine.py

# Run with coverage
uv run pytest --cov=src --cov-report=html --cov-report=term

# Run only fast tests (skip integration)
uv run pytest -m "not integration"

# Run only integration tests
uv run pytest -m integration

# Use a specific MO connection for tests
BM_TEST_DATABASE_URL="mysql+aiomysql://root:111@localhost:6001/day1_test" uv run pytest
```

## Linting & Type Checking

```bash
# Type check
uv run mypy src

# Lint check
uv run ruff check src

# Auto-fix lint issues
uv run ruff check --fix src

# Format code
uv run black src tests

# Format check only (don't write)
uv run black --check src tests
```

## Adding Dependencies

```bash
# Add a runtime dependency
uv add <package>

# Add a dev dependency
uv add --group dev <package>

# Remove a dependency
uv remove <package>
```

## Useful Combinations

```bash
# Full check before commit (format + lint + type + test)
uv run black src tests && uv run ruff check src && uv run mypy src && uv run pytest
```
