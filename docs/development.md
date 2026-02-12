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

# Install dependencies
pip install -e ".[dev]"

# Start MatrixOne (Docker)
docker run -d -p 6001:6001 --name matrixone matrixorigin/matrixone:latest

# Wait for MatrixOne to be ready (check logs)
docker logs -f matrixone
```

## Running Services

```bash
# MCP server (stdio mode) - for Claude Code integration
python -m branchedmind.mcp.server

# MCP server (SSE mode) - for testing/debug
uvicorn branchedmind.mcp.server_http:app --reload --port 3001

# FastAPI REST API
uvicorn branchedmind.api:app --reload --port 8000

# FastAPI with debug
uvicorn branchedmind.api:app --reload --port 8000 --log-level debug
```

## Database

```bash
# Run migrations
python -m scripts.migrate

# Connect to MatrixOne directly (for debugging)
docker exec -it matrixone mysql -h 127.0.0.1 -P 6001 -udump -p111

# Create snapshot
python -m scripts.snapshot create --label "before-refactor"

# List snapshots
python -m scripts.snapshot list
```

## Testing

```bash
# Run all tests
pytest

# Run specific test
pytest tests/core/test_fact_engine.py

# Run with coverage
pytest --cov=src --cov-report=html --cov-report=term

# Run only fast tests (skip integration)
pytest -m "not integration"

# Run only integration tests
pytest -m integration
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
