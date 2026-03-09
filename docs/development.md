# Development

## Prerequisites

- Go 1.24+
- Docker + Docker Compose (optional)
- MatrixOne/MySQL-compatible database (optional, only if using SQL persistence)

## Environment

```bash
cp .env.example .env
```

Important env vars:

- `DAY1_PORT` (default `9821`)
- `DAY1_DATABASE_URL` (empty = in-memory backend)
- `DAY1_EMBEDDING_PROVIDER` / `DAY1_LLM_PROVIDER` and related BYOK keys

## Run API and CLI

```bash
# API server
go run ./cmd/day1-api

# CLI
go run ./cmd/day1 help
go run ./cmd/day1 health
```

## SQL persistence check

```bash
# No-op when DAY1_DATABASE_URL is not set
bash scripts/check_db.sh

# Explicit schema bootstrap
go run ./cmd/day1 migrate
```

## Test and build

```bash
go test ./...
go build ./...
```

## Docker Compose

```bash
# Dev profile (Go API)
docker compose --profile dev up -d

# Optional local MatrixOne from compose
docker compose --profile dev --profile matrixone up -d

# Validate config
docker compose config
```

## MCP endpoint

When API is running, MCP endpoint is:

- `http://localhost:9821/mcp`

Configure Claude Code:

```bash
claude mcp add --scope project --transport http day1 http://localhost:9821/mcp
```
