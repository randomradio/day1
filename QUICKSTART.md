# Day1 Quickstart Guide

## Status: Implementation Complete ✅

All stages from the original plan are implemented and pushed. The Day1 MCP server is ready to use.

## How to Start Using Day1 Memory

### Option 1: Manual Mode (Works Now)

The MCP server is already configured. Just start using the memory tools:

```bash
# List available tools - you should see "day1" server with 20+ tools
/mcp
```

Then during conversation:
- Claude will automatically use `memory_search` before starting work
- Use `memory_write_fact` to store decisions, patterns, learnings
- Use `memory_snapshot` before risky changes

### Option 2: Automatic Mode (Repo-Level Config)

For fully automatic memory tracking, hooks are already configured in `.claude/settings.json`.

The hooks capture:
- **SessionStart** - Injects relevant historical memory into context
- **UserPromptSubmit** - Captures user messages in conversation history
- **PreToolUse** - Captures tool invocations before execution
- **PostToolUse** - Captures tool results after execution
- **Stop** - Captures assistant responses in conversation history
- **PreCompact** - Handles context compaction
- **SessionEnd** - Generates final session summary and consolidation

## Quick Verification

After configuration, verify:

1. **Check MCP server is running:**
   ```
   /mcp
   ```
   Should show "day1" server with 20+ tools

2. **Test memory search:**
   ```
   Use memory_search with query "Day1 project setup"
   ```

3. **Test fact storage:**
   ```
   Use memory_write_fact with fact_text="Test fact", category="test", confidence=1.0
   ```

## What Already Works

- ✅ `.mcp.json` configured with "day1" server
- ✅ `.claude/settings.json` has hooks configured
- ✅ `.env` has MatrixOne connection + Doubao embeddings
- ✅ CLAUDE.md has memory integration instructions
- ✅ Vector store + Doubao embeddings implemented
- ✅ All code committed and pushed

## Environment Configuration

The following environment variables are configured in `.env`:

```bash
BM_DATABASE_URL=mysql+aiomysql://<MatrixOne connection>
BM_EMBEDDING_PROVIDER=doubao
BM_DOUBAO_API_KEY=<your-key>
BM_DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
BM_DOUBAO_EMBEDDING_MODEL=doubao-embedding-vision-251215
```

## Key MCP Memory Tools

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `memory_write_fact` | Store structured facts | After learning decisions, patterns, bugs |
| `memory_search` | Semantic + keyword search | Before starting work, to find context |
| `memory_graph_query` | Query entity relationships | Exploring connections between components |
| `memory_branch_create` | Create isolated branch | Before experimental changes |
| `memory_branch_switch` | Switch branches | Working on different features |
| `memory_snapshot` | Point-in-time snapshot | Before risky changes |
| `memory_timeline` | Chronological history | Reviewing session activity |
| `memory_task_create` | Create long-running task | Multi-agent collaboration |
| `memory_task_join` | Join agent to task | Multi-agent isolation |
| `memory_task_status` | Get task progress | Reviewing task state |
| `memory_consolidate` | Distill observations | Cleaning up memory |

## Memory Architecture

Day1 provides a Git-like memory layer with:

1. **Facts** - Structured knowledge with vector embeddings
2. **Relations** - Entity relationship graph
3. **Observations** - Tool call records (compressed)
4. **Sessions** - Conversation tracking with summaries
5. **Branches** - Isolated experimentation (git-like)
6. **Tasks** - Multi-agent coordination with objectives
7. **Snapshots** - Point-in-time memory state
8. **Time Travel** - Query memory as it was at any point

## Next Steps

1. **Start using memory tools** - Try `memory_search` for your next task
2. **Store important learnings** - Use `memory_write_fact` after discovering patterns
3. **Create snapshots** - Use `memory_snapshot` before risky changes
4. **Explore branches** - Use `memory_branch_create` for experiments

## Troubleshooting

If hooks don't work:
- Verify `.claude/settings.json` has correct Python path
- Check that `.venv/bin/python` exists and works
- Ensure `.env` has valid `BM_DATABASE_URL`

For MCP issues:
- Run `/mcp` to verify server connection
- Check logs in `.claude/logs/mcp.log`

## Documentation

- `docs/architecture.md` - System design and integration points
- `docs/mcp_tools.md` - MCP server tools reference
- `docs/development.md` - Setting up env, running tests
- `CLAUDE.md` - Project-specific Claude Code instructions
