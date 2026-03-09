# REST API Reference (Go backend)

Base URL: `http://localhost:9821`

## Health

- `GET /health`

## Memory

- `POST /api/v1/memories`
- `GET /api/v1/memories/timeline`
- `GET /api/v1/memories/count`
- `GET /api/v1/memories/{memory_id}`
- `PATCH /api/v1/memories/{memory_id}`
- `DELETE /api/v1/memories/{memory_id}`
- `POST /api/v1/memories/batch`
- `DELETE /api/v1/memories/batch`

## Relations / Graph

- `POST /api/v1/memories/{memory_id}/relations`
- `GET /api/v1/memories/{memory_id}/relations`
- `GET /api/v1/memories/{memory_id}/graph`
- `DELETE /api/v1/relations/{relation_id}`

## MCP wrappers and hook ingest

- `GET /api/v1/ingest/mcp-tools`
- `POST /api/v1/ingest/mcp`
- `POST /api/v1/ingest/mcp-tools/{tool_name}`
- `POST /api/v1/ingest/claude-hook`
- `POST /api/v1/ingest/hook`
- `GET /api/v1/ingest/hook`

## Sessions

- `GET /api/v1/sessions`
- `GET /api/v1/sessions/{session_id}`
- `GET /api/v1/sessions/{session_id}/summary`
- `POST /api/v1/sessions/{session_id}/checkpoints`

## Traces

- `GET /api/v1/traces`
- `GET /api/v1/traces/{trace_id}`
- `POST /api/v1/traces`
- `POST /api/v1/traces/extract`
- `POST /api/v1/traces/{trace_a_id}/compare/{trace_b_id}`

## Notes

- The API returns structured error payloads with HTTP status codes mapped from kernel/domain errors.
- `DAY1_DATABASE_URL` controls persistence backend:
  - set: SQL persistence
  - unset: in-memory mode
- MCP endpoint is exposed at `/mcp` and can be called directly by MCP clients.
