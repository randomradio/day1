# Development Commands

Commands for setting up, running, and testing BranchedMind. Read this when setting up env or running builds/tests.

## Environment Setup

```bash
# Clone and navigate
git clone git@github.com:randomradio/day1.git
cd day1

# Create venv
python -m venv .venv
source .venv/bin/activate  # Linux/mac
# .venv\Scripts\activate   # Windows

# Install dependencies (aiomysql included in main deps)
pip install -e ".[dev]"
```

## MatrixOne Database

### Option A: MO Cloud (Recommended)

```bash
# Set connection string (MO Cloud)
export BM_DATABASE_URL="mysql+aiomysql://0193bd50-818d-76ba-bb43-a2abd031d6e5%3Aadmin%3Aaccountadmin:AIcon2024@freetier-01.cn-hangzhou.cluster.matrixonecloud.cn:6001/branchedmind"

# Verify MO features
python scripts/test_mo_features.py
```

### Option B: Local Docker

```bash
# Start MatrixOne (Docker)
docker run -d -p 6001:6001 --name matrixone matrixorigin/matrixone:latest

# Wait for MatrixOne to be ready
docker logs -f matrixone

# Set connection string (local)
export BM_DATABASE_URL="mysql+aiomysql://root:111@127.0.0.1:6001/branchedmind"

# Connect directly (for debugging)
docker exec -it matrixone mysql -h 127.0.0.1 -P 6001 -uroot -p111
```

## Running Services

```bash
# FastAPI REST API
uvicorn branchedmind.api.app:app --reload --port 8000

# FastAPI with debug
uvicorn branchedmind.api.app:app --reload --port 8000 --log-level debug

# MCP server (stdio mode) - for Claude Code integration
python -m branchedmind.mcp.server

# MCP server (SSE mode) - for testing/debug
uvicorn branchedmind.mcp.server_http:app --reload --port 3001
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
python scripts/test_mo_features.py

# Run migrations
python -m scripts.migrate

# Create snapshot (native MO)
curl -X POST http://localhost:8000/api/v1/snapshots -H 'Content-Type: application/json' -d '{"native": true, "label": "before-refactor"}'
```

## Testing

```bash
# Run all tests (requires MO connection)
pytest

# Run specific test
pytest tests/test_core/test_fact_engine.py

# Run with coverage
pytest --cov=src --cov-report=html --cov-report=term

# Run only fast tests (skip integration)
pytest -m "not integration"

# Run only integration tests
pytest -m integration

# Use a specific MO connection for tests
BM_TEST_DATABASE_URL="mysql+aiomysql://root:111@localhost:6001/branchedmind_test" pytest
```

## Linting & Type Checking

```bash
# Type check
mypy src

# Lint check
ruff check src

# Auto-fix lint issues
ruff check --fix src

# Format code
black src tests

# Format check only (don't write)
black --check src tests
```

## Pre-commit

```bash
# Install hooks
pre-commit install

# Run manually on all files
pre-commit run --all-files

# Run on staged files only
pre-commit run
```

## Useful Combinations

```bash
# Full check before commit (format + lint + type + test)
black src tests && ruff check src && mypy src && pytest
```
