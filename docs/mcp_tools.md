# MCP Tools Reference (Go backend)

Day1 exposes MCP over HTTP `streamable_http` at:

- `http://localhost:9821/mcp`

## Connect Claude Code

```bash
claude mcp add --scope project --transport http day1 http://localhost:9821/mcp
```

## Tool groups (22 total)

## Memory (9)

- `memory_write`
- `memory_write_batch`
- `memory_get`
- `memory_update`
- `memory_archive`
- `memory_archive_batch`
- `memory_search`
- `memory_timeline`
- `memory_count`

## Branch (5)

- `memory_branch_create`
- `memory_branch_switch`
- `memory_branch_list`
- `memory_branch_archive`
- `memory_branch_delete`

## Snapshot / Merge (4)

- `memory_snapshot`
- `memory_snapshot_list`
- `memory_restore`
- `memory_merge`

## Relation graph (4)

- `memory_relate`
- `memory_relations`
- `memory_graph`
- `memory_relation_delete`

## REST wrappers

- `GET /api/v1/ingest/mcp-tools`
- `POST /api/v1/ingest/mcp`
- `POST /api/v1/ingest/mcp-tools/{tool_name}`

## Implementation files

- Tool registry and handlers: `internal/mcp/registry.go`
- HTTP adapters: `internal/api/server.go`
- API entrypoint: `cmd/day1-api/main.go`
