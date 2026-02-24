#!/bin/bash
# Start Day1 MCP server (for use with Claude Code)

set -e

cd "$(dirname "$0")/.."

export BM_DATABASE_URL="mysql+aiomysql://root:111@localhost:6001/mo_catalog"

echo "Starting Day1 MCP server..."
echo "Database: $BM_DATABASE_URL"
echo ""

.venv/bin/python -m day1.mcp.server
