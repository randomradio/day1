# Examples

## Write and search via REST wrapper

```bash
curl -X POST http://localhost:9821/api/v1/ingest/mcp \
  -H 'Content-Type: application/json' \
  -d '{"tool":"memory_write","arguments":{"text":"remember this","category":"note"}}'

curl -X POST http://localhost:9821/api/v1/ingest/mcp \
  -H 'Content-Type: application/json' \
  -d '{"tool":"memory_search","arguments":{"query":"remember","limit":5}}'
```
