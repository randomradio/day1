# Day1 MCP Memory Integration Plan

**Status**: Completed

## Context

User wants Claude Code to automatically use the Day1 (formerly BranchedMind) MCP memory tools for managing chat history and memories across sessions. Currently:
- `autoMemoryEnabled: true` stores to CLAUDE.md (file-based)
- MCP server has 20+ memory tools but requires manual invocation
- Project needs renaming from "branchedmind" to "Day1"

## Goal

Make Claude Code automatically use MCP memory tools during conversations:
1. Add instructions to CLAUDE.md so Claude knows when/how to use memory tools
2. Rename project references to "Day1"
3. No manual "init" needed - automatic session tracking

## Implementation

### Stage 1: Update CLAUDE.md with Memory Instructions ✅

**File:** `/Users/randomradio/src/day1/CLAUDE.md`

Added "Day1 Memory Integration" section with:
- Automatic session tracking explanation
- Key MCP memory tools reference table
- Initialization guidance ("No manual init needed")
- Usage patterns for starting work, learning, and risky changes

### Stage 2: Update .mcp.json Server Name ✅

**File:** `/Users/randomradio/src/day1/.mcp.json`

Changed server name from "branchedmind" to "day1":

```json
{
  "mcpServers": {
    "day1": {
      "command": "/Users/randomradio/src/day1/.venv/bin/python",
      "args": ["-m", "branchedmind.mcp.server"],
      "cwd": "/Users/randomradio/src/day1"
    }
  }
}
```

### Stage 3: Update CLAUDE.md Project Header ✅

Changed from `## Project: BranchedMind v2` to `## Project: Day1 (BranchedMind v2 Memory Layer)`

### Stage 4: Update .env.example ✅

Updated header comment with Day1 branding.

## Key Decision: Hybrid Memory Approach ✅

**User chose:** Hybrid mode

**What this means:**
- **Automatic**: Tool observations captured via hooks (session_start, post_tool_use, session_end)
- **Manual**: Explicit `memory_write_fact` calls for important decisions, patterns, learnings
- **Manual**: Explicit `memory_search` before starting work to find context

**Configuration needed:**
Hooks to be added to `/Users/randomradio/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [{
      "type": "command",
      "command": "/Users/randomradio/src/day1/.venv/bin/python -m branchedmind.hooks.session_start"
    }],
    "PostToolUse": [{
      "type": "command",
      "command": "/Users/randomradio/src/day1/.venv/bin/python -m branchedmind.hooks.post_tool_use"
    }],
    "SessionEnd": [{
      "type": "command",
      "command": "/Users/randomradio/src/day1/.venv/bin/python -m branchedmind.hooks.session_end"
    }],
    "Stop": [{
      "type": "command",
      "command": "/Users/randomradio/src/day1/.venv/bin/python -m branchedmind.hooks.stop"
    }]
  },
  "env": {
    "BM_DATABASE_URL": "mysql+aiomysql://...",
    "BM_EMBEDDING_PROVIDER": "doubao"
  }
}
```

## Commits

- `c723a3f` - feat: rename project to Day1 and add MCP memory integration docs
- `8367f67` - feat: add vector store and Doubao embedding support

## Testing Checklist

- [x] `.mcp.json` server renamed to "day1"
- [x] CLAUDE.md references "Day1" project name
- [x] Memory integration instructions added to CLAUDE.md
- [ ] `/mcp` command shows "day1" server (user to verify)
- [ ] `memory_search` returns results from previous sessions (user to verify)
- [ ] `memory_write_fact` stores data successfully (user to verify)
- [ ] Hooks configured in global settings.json (user to configure)

## Critical Files

- `/Users/randomradio/src/day1/CLAUDE.md` - Memory instructions (PRIMARY)
- `/Users/randomradio/src/day1/.mcp.json` - Server configuration
- `/Users/randomradio/.claude/settings.json` - Hooks configuration (not in repo)
