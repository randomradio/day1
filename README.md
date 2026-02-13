# BranchedMind v2

Git-like memory layer for AI agents — managing writes, retrieval, branching, merging, snapshots, and time-travel.

Powered by [MatrixOne](https://matrixorigin.io) (vecf32 + FULLTEXT INDEX + git4data + PITR).

## Quick Start

```bash
# Install (requires uv)
uv sync --all-extras

# Verify MO connection
uv run python scripts/test_mo_features.py

# Start API server
uv run uvicorn branchedmind.api.app:app --reload --port 8000

# Start dashboard
cd dashboard && npm install && npm run dev
```

See `docs/development.md` for full setup instructions.
