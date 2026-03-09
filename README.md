# Day1

Git-like memory layer for agents with branch/snapshot/merge/search primitives, backed by Go and MatrixOne-compatible SQL.

## Runtime

- API entrypoint: `go run ./cmd/day1-api`
- CLI entrypoint: `go run ./cmd/day1`
- Database: optional via `BM_DATABASE_URL`
  - If unset, backend runs in-memory.
  - If set, backend persists to MatrixOne/MySQL-compatible SQL.

## Quick Start (Docker)

```bash
cp .env.example .env

# Go backend (dev profile)
docker compose --profile dev up -d

# Optional: include local MatrixOne from compose
docker compose --profile dev --profile matrixone up -d
```

`BM_DATABASE_URL` precedence:

1. System environment value
2. `.env` value
3. Compose fallback (`127.0.0.1:6001` for `api-dev`, `host.docker.internal:6001` for `api`)

Endpoints:

- API: `http://localhost:9821`
- API docs: `http://localhost:9821/docs`
- MCP: `http://localhost:9821/mcp`
- Health: `http://localhost:9821/health`

## Quick Start (Local)

Prereqs: Go 1.24+, optional MatrixOne.

```bash
cp .env.example .env

# Optional DB check (requires BM_DATABASE_URL)
bash scripts/check_db.sh

# Start API
go run ./cmd/day1-api
```

## Validation

```bash
go test ./...
go build ./...
go run ./cmd/day1-api
```

## BYOK (Embedding + LLM)

Embedding provider:

- `BM_EMBEDDING_PROVIDER=mock|openai|openrouter|custom|doubao`
- `openai`: requires `BM_OPENAI_API_KEY`
- `openrouter`: requires `BM_OPENROUTER_API_KEY`
- `custom`: requires `BM_EMBEDDING_API_KEY` + `BM_EMBEDDING_BASE_URL`
- `doubao`: requires `BM_DOUBAO_API_KEY`

LLM provider:

- `BM_LLM_PROVIDER=mock|openai|anthropic|custom`
- `openai`: requires `BM_OPENAI_API_KEY`
- `anthropic`: requires `BM_ANTHROPIC_API_KEY`
- `custom`: requires `BM_LLM_API_KEY` + `BM_LLM_BASE_URL`

## Docs

- [QUICKSTART.md](QUICKSTART.md)
- [docs/development.md](docs/development.md)
- [docs/api_reference.md](docs/api_reference.md)
- [docs/mcp_tools.md](docs/mcp_tools.md)
- [docs/go-backend-migration.md](docs/go-backend-migration.md)

## License

Private.
