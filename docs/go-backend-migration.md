# Day1 Go Backend Migration Notes

## Scope

This Go rewrite targets backend paths only:

- `cmd/**`
- `internal/**`
- `tests/**`
- `docs/**`

Excluded from rewrite:

- `client-package/**`

## Runtime validation

- `go test ./...`
- `go build ./...`
- `go run ./cmd/day1-api`

## Persistence backend

- `DAY1_DATABASE_URL` enables MatrixOne/MySQL-compatible SQL persistence.
- Without `DAY1_DATABASE_URL`, the service runs with in-memory state.
- SQL backend bootstraps required tables for:
  - `memories`
  - `branches`
  - `snapshots`
  - `memory_relations`
  - `sessions`
  - `hook_logs`
  - `traces`
  - `trace_comparisons`

## Memory-kernel API (Go)

The kernel contract is centered in `internal/kernel` and includes:

- memory CRUD and batch writes
- semantic search and timeline
- branch create/switch/archive/delete
- snapshot create/list/restore
- merge (dedup by text)
- relation graph APIs

## BYOK configuration

Embedding providers:

- `DAY1_EMBEDDING_PROVIDER=mock|openai|openrouter|custom|doubao`
- `DAY1_OPENAI_API_KEY` (required for `openai`)
- `DAY1_OPENROUTER_API_KEY` (required for `openrouter`)
- `DAY1_EMBEDDING_API_KEY` + `DAY1_EMBEDDING_BASE_URL` (required for `custom`)
- `DAY1_DOUBAO_API_KEY` (required for `doubao`)

LLM providers:

- `DAY1_LLM_PROVIDER=mock|openai|anthropic|custom`
- `DAY1_OPENAI_API_KEY` (required for `openai`)
- `DAY1_ANTHROPIC_API_KEY` (required for `anthropic`)
- `DAY1_LLM_API_KEY` + `DAY1_LLM_BASE_URL` (required for `custom`)

Common:

- `DAY1_PORT` (default `9821`)
- `DAY1_EMBEDDING_MODEL`
- `DAY1_EMBEDDING_DIMENSIONS`
- `DAY1_LLM_MODEL`

## API compatibility status

Implemented compatibility surfaces:

- `GET /health`
- `GET /api/v1/memories/timeline`
- `GET /api/v1/memories/count`
- `GET|PATCH|DELETE /api/v1/memories/{memory_id}`
- `POST /api/v1/memories`
- `POST|DELETE /api/v1/memories/batch`
- relation routes
- `GET /api/v1/ingest/mcp-tools`
- `POST /api/v1/ingest/mcp`
- `POST /api/v1/ingest/mcp-tools/{tool_name}`
- hook ingestion/listing routes
- sessions routes:
  - `GET /api/v1/sessions`
  - `GET /api/v1/sessions/{session_id}`
  - `GET /api/v1/sessions/{session_id}/summary`
  - `POST /api/v1/sessions/{session_id}/checkpoints`
- traces routes:
  - `GET /api/v1/traces`
  - `GET /api/v1/traces/{trace_id}`
  - `POST /api/v1/traces`
  - `POST /api/v1/traces/extract`
  - `POST /api/v1/traces/{trace_a_id}/compare/{trace_b_id}`

MCP tool names are registered in `internal/mcp/registry.go`.

## Known compatibility deltas

- Trace comparison scoring is heuristic parity and does not yet replicate full Python comparison-engine behavior.

## CLI starter

- Added `cmd/day1` compatibility CLI with command families:
  - system: `help`, `test`, `api`, `migrate`, `init`, `health`
  - memory: `write`, `search`, `timeline`, `count`
  - branch/snapshot/merge: `branch`, `snapshot`, `merge`
- CLI routes operations through the Go API/MCP wrappers for parity-oriented behavior.
- `test` runs `go test ./...` and propagates the underlying exit code.
- `migrate` and `init` bootstrap both kernel and API metadata SQL schemas when `DAY1_DATABASE_URL` is set.
