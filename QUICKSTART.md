# Day1 Quickstart

## 1. Docker Compose (recommended)

```bash
cp .env.example .env

# Go backend
docker compose --profile dev up -d

# Optional local MatrixOne via compose
# docker compose --profile dev --profile matrixone up -d
```

Service URLs:

- API: `http://localhost:9821`
- API docs: `http://localhost:9821/docs`
- MCP: `http://localhost:9821/mcp`
- Health: `http://localhost:9821/health`

Check:

```bash
docker compose --profile dev ps
curl -fsS http://localhost:9821/health
```

Stop:

```bash
docker compose --profile dev down
docker compose --profile dev down -v
```

## 2. Local run (without Docker)

Prereqs: Go 1.24+ and optional MatrixOne if you want SQL persistence.

```bash
cp .env.example .env

# If using SQL persistence, set BM_DATABASE_URL (env or .env)
# Example:
# export BM_DATABASE_URL='mysql+aiomysql://root:111@127.0.0.1:6001/day1'

# Optional DB schema/connectivity check
bash scripts/check_db.sh

# Run API
go run ./cmd/day1-api
```

Then verify:

```bash
curl -fsS http://localhost:9821/health
```

## 3. CLI entrypoint

```bash
go run ./cmd/day1 help
go run ./cmd/day1 health
go run ./cmd/day1 test
```

## 4. MCP setup (Claude Code)

```bash
claude mcp add --scope project --transport http day1 http://localhost:9821/mcp
claude mcp get day1
```

Or `.mcp.json`:

```json
{
  "mcpServers": {
    "day1": {
      "type": "http",
      "url": "http://localhost:9821/mcp"
    }
  }
}
```

## 5. Validation commands

```bash
go test ./...
go build ./...
go run ./cmd/day1-api
```

## 6. Troubleshooting

| Problem | Fix |
|---------|-----|
| DB connection failed | Set `BM_DATABASE_URL` correctly, then run `bash scripts/check_db.sh` |
| API health check fails | Confirm `go run ./cmd/day1-api` is running on port 9821 |
| MCP tools missing | Check `claude mcp get day1` and API health |
