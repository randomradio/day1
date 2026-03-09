# Claude Code Hooks Integration

Day1 integrates with Claude Code via hooks to auto-capture session events into the memory layer.

## What Hooks Do

- **Auto-capture** Claude Code session events (start, prompts, responses, end)
- **Auto-create** session rows in the `sessions` table on first event
- **Store** each event as append-only entries in the `hook_logs` table
- **Enrich** events into memory entries (via `memory_write`) with category/source_type metadata

## Setup

Add the following to `.claude/settings.local.json` in your project:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "/bin/bash -lc 'cat | curl -sS -m 3 -X POST http://localhost:9821/api/v1/ingest/hook -H \"Content-Type: application/json\" -H \"X-Day1-Hook-Event: SessionStart\" -H \"X-Day1-Session-Id: $CLAUDE_SESSION_ID\" --data-binary @- >/dev/null 2>&1 || true'"
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "/bin/bash -lc 'cat | curl -sS -m 3 -X POST http://localhost:9821/api/v1/ingest/hook -H \"Content-Type: application/json\" -H \"X-Day1-Hook-Event: UserPromptSubmit\" -H \"X-Day1-Session-Id: $CLAUDE_SESSION_ID\" --data-binary @- >/dev/null 2>&1 || true'"
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "/bin/bash -lc 'cat | curl -sS -m 3 -X POST http://localhost:9821/api/v1/ingest/hook -H \"Content-Type: application/json\" -H \"X-Day1-Hook-Event: Stop\" -H \"X-Day1-Session-Id: $CLAUDE_SESSION_ID\" --data-binary @- >/dev/null 2>&1 || true'"
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "/bin/bash -lc 'cat | curl -sS -m 3 -X POST http://localhost:9821/api/v1/ingest/hook -H \"Content-Type: application/json\" -H \"X-Day1-Hook-Event: SessionEnd\" -H \"X-Day1-Session-Id: $CLAUDE_SESSION_ID\" --data-binary @- >/dev/null 2>&1 || true'"
          }
        ]
      }
    ]
  }
}
```

## How It Works

1. Claude Code fires each hook event as JSON via stdin
2. The hook command pipes stdin to `curl`, which POSTs to Day1's `/api/v1/ingest/hook`
3. Day1 stores the raw payload in `hook_logs` (append-only, no processing)
4. Session rows are auto-created in the `sessions` table on first event per session

### Event Flow

```
Claude Code Event → stdin JSON → curl POST → Day1 API
                                                |
                                    +-----------+----------+
                                    |                      |
                              hook_logs table       sessions table
                              (append-only)        (auto-created)
```

### Headers

| Header | Value | Description |
|--------|-------|-------------|
| `X-Day1-Hook-Event` | Event name (e.g. `SessionStart`) | Identifies the hook event type |
| `X-Day1-Session-Id` | `$CLAUDE_SESSION_ID` | Claude Code's session UUID |
| `Content-Type` | `application/json` | Payload format |

### Event Types

| Event | When | Category | Source Type |
|-------|------|----------|-------------|
| `SessionStart` | Session begins | `session` | `session_start` |
| `UserPromptSubmit` | User sends a prompt | `conversation` | `user_input` |
| `Stop` | Assistant finishes responding | `conversation` | `assistant_response` |
| `SessionEnd` | Session ends | `session` | `session_end` |

### Enriched Hook Endpoint

There is also an enriched endpoint at `POST /api/v1/ingest/claude-hook` that:
- Extracts message content from the payload
- Creates memory entries via `memory_write`
- Maps events to categories and source types with confidence scores

The basic `/api/v1/ingest/hook` is simpler and more reliable — it just stores raw payloads.

## Viewing Hook Data

### Dashboard

Navigate to the **Sessions** tab to see auto-tracked sessions and their hook event counts.

### REST API

```bash
# List hook logs (newest first)
curl http://localhost:9821/api/v1/ingest/hook?limit=20

# Filter by session
curl http://localhost:9821/api/v1/ingest/hook?session_id=YOUR_SESSION_ID

# Filter by event type
curl http://localhost:9821/api/v1/ingest/hook?event=SessionStart

# List sessions
curl http://localhost:9821/api/v1/sessions

# Get session detail (includes memories, traces, hook count)
curl http://localhost:9821/api/v1/sessions/YOUR_SESSION_ID
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Hooks not firing | Check `claude mcp list` — hooks are in settings, not MCP |
| `curl: connection refused` | Ensure Day1 API is running on port 9821 |
| Events not showing in API results | Check `curl http://localhost:9821/api/v1/ingest/hook` |
| Session not created | First hook event auto-creates session — check API logs |
| Timeout errors | The `-m 3` flag limits curl to 3 seconds; hooks fail silently via `|| true` |

## Notes

- Hooks are **fire-and-forget** — failures are silently ignored (`|| true`)
- The 3-second timeout (`-m 3`) prevents hooks from blocking Claude Code
- Each hook pipes stdin (event JSON) directly to curl — no local processing
- The `$CLAUDE_SESSION_ID` env var is set automatically by Claude Code
