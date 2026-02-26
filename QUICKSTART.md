# Day1 Quickstart Guide

## Status

Day1 core delivery is implemented:

- Backend hardening (security / rollback / concurrency)
- CLI MVP
- REST API + Dashboard
- MCP server (50+ tools)
- Strict E2E (surface/contract) + real acceptance (valid-input) flows

## Fastest Local Start (API + CLI + Dashboard)

```bash
# Prereqs: Python 3.11+, Node 22+, MatrixOne (default local port 6001)
uv sync --all-extras
cp .env.example .env

# Verify DB first
uv run scripts/check_db.py

# Start API (terminal A)
uv run uvicorn day1.api.app:app --host 127.0.0.1 --port 8000

# Start Dashboard (terminal B)
npm --prefix dashboard ci
npm --prefix dashboard run dev

# CLI smoke (terminal C)
uv run day1 health --format json
uv run day1 branch create demo/quickstart --parent main --format json
uv run day1 write-fact "Quickstart fact" --branch demo/quickstart --category test --format json
uv run day1 search "Quickstart" --branch demo/quickstart --search-type keyword --format json
```

## MCP Usage (Manual)

Start the MCP server:

```bash
uv run python -m day1.mcp.mcp_server
```

In Claude Code, verify with:

```text
/mcp
```

You should see the `day1` MCP server with 50+ tools.

## Claude Hooks (Repo-Level Automatic Mode)

If using Claude Code with repo hooks enabled, `.claude/settings.json` can auto-capture memory events:

- `SessionStart`
- `UserPromptSubmit`
- `PreToolUse`
- `PostToolUse`
- `Stop`
- `PreCompact`
- `SessionEnd`

## Real Acceptance (Valid Inputs Only, Recommended)

This is the release-style local validation flow. It simulates real agent + user interactions and writes data you can inspect in the database.

```bash
export BM_DATABASE_URL='mysql+aiomysql://root:111@127.0.0.1:6001/day1'
export BM_TEST_DATABASE_URL='mysql+aiomysql://root:111@127.0.0.1:6001/day1'
export BM_EMBEDDING_PROVIDER=mock BM_RATE_LIMIT=0 BM_LOG_LEVEL=CRITICAL

uv run python scripts/e2e_surface.py --real-only --output docs/e2e_real_acceptance_latest.json
```

Outputs:

- `docs/e2e_real_acceptance_latest.json` (report)
- `docs/e2e_real_acceptance_db_manifest.json` (machine-readable DB manifest)
- `docs/E2E_REAL_ACCEPTANCE.md` (human verification guide with concrete SQL)

## Strict Surface + Real (Contract Safety + Acceptance)

This includes negative/synthetic input checks (for example `Field required`, `not found`) and is separate from real acceptance criteria.

```bash
uv run python scripts/e2e_surface.py --output docs/e2e_surface_latest_report.json
```

See `docs/E2E_TEST_METHODS.md` for methodology and all surface `warn` explanations.

## Key CLI Commands

```bash
uv run day1 branch create <branch> --parent main --format json
uv run day1 branch list --format json
uv run day1 branch switch <branch> --format json

uv run day1 write-fact "text" --branch <branch> --format json
uv run day1 write-observation "summary" --branch <branch> --session-id <sid> --format json
uv run day1 search "query" --branch <branch> --search-type keyword --format json

uv run day1 snapshot create --branch <branch> --label <label> --format json
uv run day1 snapshot list --branch <branch> --format json
uv run day1 time-travel 2099-01-01T00:00:00Z --branch <branch> --format json
```

## Troubleshooting

- DB unreachable: run `uv run scripts/check_db.py` and verify MatrixOne on `127.0.0.1:6001`
- API health fails: check `uvicorn` logs and `uv run day1 health --format json`
- MCP client not seeing tools: start server with `uv run python -m day1.mcp.mcp_server`, then re-check `/mcp`
- Dashboard build issues: run `npm --prefix dashboard ci` before `npm --prefix dashboard run dev`

## Docs to Read Next

- `README.md` (high-level setup + local usage)
- `docs/mcp_tools.md` (tool reference)
- `docs/E2E_REAL_ACCEPTANCE.md` (valid-input local verification)
- `docs/E2E_TEST_METHODS.md` (strict surface/contract methodology)
- `CLAUDE.md` (repo-specific Claude Code instructions)
