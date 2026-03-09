# Architecture (Go backend)

## High-level

Day1 provides a Go API + MCP surface over a memory-kernel service with optional SQL persistence.

```
Clients (REST / MCP / hooks)
  -> cmd/day1-api (Gin HTTP server)
    -> internal/api (routes + adapters)
      -> internal/mcp (tool registry)
      -> internal/kernel (memory-kernel primitives)
      -> internal/storage (MatrixOne/MySQL persistence)
      -> internal/providers (embedding + llm BYOK providers)
```

## Runtime components

- API entrypoint: `cmd/day1-api/main.go`
- CLI entrypoint: `cmd/day1/main.go`
- HTTP routes: `internal/api/server.go`
- MCP tools: `internal/mcp/registry.go`
- Memory kernel: `internal/kernel/service.go`
- SQL store: `internal/storage/mysql_store.go`
- Config/BYOK validation: `internal/config/config.go`

## Storage mode

- `DAY1_DATABASE_URL` set: SQL persistence (`memories`, `branches`, `snapshots`, `memory_relations`, plus metadata tables)
- `DAY1_DATABASE_URL` unset: in-memory backend

## Memory-kernel primitives

- write / batch-write / get / update / archive
- search / timeline / count
- branch create/switch/list/archive/delete
- snapshot create/list/restore
- merge
- relation create/list/delete
- graph traversal

## MCP surface

MCP is exposed at `/mcp` and mirrors kernel operations through tool handlers in `internal/mcp/registry.go`.

## BYOK providers

Embedding:

- `DAY1_EMBEDDING_PROVIDER=mock|openai|openrouter|custom|doubao`
- Provider-specific API keys and base URLs are validated at startup.

LLM:

- `DAY1_LLM_PROVIDER=mock|openai|anthropic|custom`
- Provider-specific API keys and base URLs are validated at startup.
