#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:9821}"

curl -fsS -X POST "$BASE_URL/api/v1/ingest/mcp" \
  -H 'Content-Type: application/json' \
  -d '{"tool":"memory_write","arguments":{"text":"release checklist complete","category":"status"}}' >/tmp/day1-write.json

echo "write:"
cat /tmp/day1-write.json

echo

echo "search:"
curl -fsS -X POST "$BASE_URL/api/v1/ingest/mcp" \
  -H 'Content-Type: application/json' \
  -d '{"tool":"memory_search","arguments":{"query":"release checklist","limit":3}}'
