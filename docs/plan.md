# Day1 — GitHub for Agent Conversations

**Vision**: A SaaS platform where every agent conversation is captured like git commits — branchable, searchable, forkable.

**Status**: Phase 1-2 Complete, Phase 3 In Progress

---

## Architecture: Two-Layer Model

```
┌───────────────────────────────────────────────────────────┐
│  CLIENTS                                                   │
│  Claude Code ─┐  Cursor ─┐  LangChain ─┐  Any Agent ─┐  │
│               ▼          ▼             ▼              ▼   │
│  ┌────────────────────────────────────────────────────┐   │
│  │  CAPTURE LAYER                                      │   │
│  │  HTTP API (/api/v1/*)  +  Hooks  +  MCP (27 tools) │   │
│  └──────────────────────┬─────────────────────────────┘   │
│                         ▼                                  │
│  ┌────────────────────────────────────────────────────┐   │
│  │  Layer 1: HISTORY (append-only, branchable)        │   │
│  │  conversations ← messages                           │   │
│  │  fork / replay / diff / search                      │   │
│  ├────────────────────────────────────────────────────┤   │
│  │  Layer 2: MEMORY (mutable, branchable)             │   │
│  │  facts ← relations ← observations                  │   │
│  │  branch / merge / consolidate / time-travel         │   │
│  └────────────────────────────────────────────────────┘   │
│                         │                                  │
│                  MatrixOne (git4data)                       │
└───────────────────────────────────────────────────────────┘
```

---

## Phase 1: Memory Layer (Complete)

Original BranchedMind v2 — git-like memory for AI agents.

| Component | Status |
|-----------|--------|
| Facts, Relations, Observations models | Done |
| Branch/Merge with MO DATA BRANCH | Done |
| Hybrid search (BM25 + vector) | Done |
| Snapshots + time-travel (PITR) | Done |
| Multi-agent tasks + consolidation | Done |
| 23 MCP tools | Done |
| FastAPI REST API | Done |
| React dashboard (branch viz) | Done |
| 4 hooks: SessionStart, PostToolUse, PreCompact, Stop | Done |

**Commits**: `c723a3f`, `8367f67`, `5e1ce3d`, `67bd7c6`, `9ccb1b0`

---

## Phase 2: Conversation & Message History (Complete)

Layer 1 — capture everything, operate like git on conversations.

| Component | Status |
|-----------|--------|
| `Conversation` + `Message` models (branchable) | Done |
| `ConversationEngine` (create, list, fork, diff) | Done |
| `MessageEngine` (write, list, hybrid search) | Done |
| 9 HTTP API endpoints (conversations + messages) | Done |
| +4 MCP tools (log_message, list_conversations, search_messages, fork_conversation) | Done |
| 3 new capture hooks (UserPromptSubmit, Stop/assistant, PreToolUse) | Done |
| Enhanced existing hooks (session_start → creates conv, post_tool_use → writes msg) | Done |
| Dashboard TypeScript types + API client | Done |

**Commit**: `d7654cf`

### New Data Flow

```
User types message
  → UserPromptSubmit hook fires
    → stores message in conversations.messages (Layer 1)
    → searches memory, injects relevant facts (Layer 2)
  → Claude processes + calls tools
    → PreToolUse hook fires → stores tool_call message (Layer 1)
    → tool executes
    → PostToolUse hook fires
      → stores observation (Layer 2)
      → stores tool_result message (Layer 1)
  → Claude responds
    → Stop hook fires → stores assistant message (Layer 1)
  → Context compresses
    → PreCompact hook fires → extracts facts (Layer 2)
  → Session ends
    → SessionEnd hook fires → summarizes + consolidates (Layer 2)
```

---

## Phase 3: Hooks Config + Session Continuity (In Progress)

### 3a. Complete Hooks Wiring

The hook Python scripts exist but need to be registered in Claude Code settings.

**7 hooks to register:**

| Event | Hook Script | Purpose |
|-------|-------------|---------|
| SessionStart | `branchedmind.hooks.session_start` | Register session, create conversation, inject memory |
| UserPromptSubmit | `branchedmind.hooks.user_prompt` | Capture user messages, inject relevant facts |
| PreToolUse | `branchedmind.hooks.pre_tool_use` | Capture tool call intent |
| PostToolUse | `branchedmind.hooks.post_tool_use` | Capture tool results + observations |
| Stop | `branchedmind.hooks.assistant_response` | Capture assistant responses |
| PreCompact | `branchedmind.hooks.pre_compact` | Extract facts before compression |
| SessionEnd | `branchedmind.hooks.session_end` | Summarize + consolidate |

**Files to update:**
- `hooks/claude_code_config.py` — add all 7 hooks
- `.claude/settings.json` — generate actual config file

### 3b. Session Continuity / Context Handoff

**Problem**: When a new agent starts, it needs to pick up all context from prior sessions — not just facts but full conversations.

**Solution**: `BM_PARENT_SESSION` env var + `memory_session_context` MCP tool.

**How it works:**

```
Agent A (session-001) runs, builds context
  → conversations, messages, facts, observations all stored

Agent B starts with BM_PARENT_SESSION=session-001
  → SessionStart hook detects parent session
  → Loads: session summary, conversation messages, key facts
  → Injects into context as additionalContext
  → Agent B continues exactly where Agent A left off
```

**What to build:**

1. `SessionManager.get_session_context(session_id)` — returns full session package:
   - Session metadata (summary, branch, timestamps)
   - Conversations with recent messages
   - Key facts produced during that session
   - Observations summary

2. `GET /api/v1/sessions/{session_id}/context` — HTTP endpoint for any client

3. `memory_session_context` MCP tool — for MCP clients

4. Enhanced `SessionStart` hook — checks `BM_PARENT_SESSION` env var, loads parent context

---

## Phase 4: Dashboard — Conversation Browser (Planned)

Build a conversation replay UI in the React dashboard.

| Feature | Description |
|---------|-------------|
| Conversation list | Browse all conversations, filter by session/agent/status |
| Message thread view | Replay a conversation message-by-message |
| Fork visualization | Show conversation forks as a tree (like git branches) |
| Diff view | Side-by-side comparison of two conversations |
| Search across messages | Global semantic search with highlighted results |
| Session timeline | Combined view: messages + facts + observations chronologically |

---

## Phase 5: SaaS Platform (Planned)

Transform from developer tool to multi-tenant SaaS.

| Feature | Description |
|---------|-------------|
| Auth + multi-tenancy | User accounts, API keys, org-level isolation |
| Ingest API | Universal REST endpoint for any agent framework |
| Webhooks | Push notifications on conversation events |
| Usage tracking | Token counts, storage, API calls per tenant |
| Public conversation sharing | Share a conversation like a GitHub gist |
| CLI tool | `day1 push`, `day1 pull`, `day1 fork` from terminal |

---

## Key Files

### Backend (Python)

| File | Purpose |
|------|---------|
| `src/branchedmind/db/models.py` | All ORM models (11 tables) |
| `src/branchedmind/db/engine.py` | DB engine + fulltext indexes |
| `src/branchedmind/core/message_engine.py` | Message CRUD + search |
| `src/branchedmind/core/conversation_engine.py` | Conversation lifecycle + fork + diff |
| `src/branchedmind/core/fact_engine.py` | Fact CRUD |
| `src/branchedmind/core/search_engine.py` | Hybrid BM25 + vector search |
| `src/branchedmind/core/session_manager.py` | Session tracking |
| `src/branchedmind/core/branch_manager.py` | MO DATA BRANCH operations |
| `src/branchedmind/core/merge_engine.py` | Multi-strategy merge |
| `src/branchedmind/core/task_engine.py` | Multi-agent task coordination |
| `src/branchedmind/core/consolidation_engine.py` | Memory distillation |
| `src/branchedmind/api/routes/conversations.py` | Conversation REST endpoints |
| `src/branchedmind/api/routes/messages.py` | Message REST endpoints |
| `src/branchedmind/mcp/tools.py` | 27 MCP tool definitions + handlers |
| `src/branchedmind/hooks/` | 7 Claude Code lifecycle hooks |
| `src/branchedmind/hooks/claude_code_config.py` | Hook config generator |

### Frontend (React + TypeScript)

| File | Purpose |
|------|---------|
| `dashboard/src/types/schema.ts` | All TypeScript interfaces |
| `dashboard/src/api/client.ts` | API client methods |
| `dashboard/src/components/BranchTree.tsx` | Branch DAG visualization |

### Configuration

| File | Purpose |
|------|---------|
| `.claude/settings.json` | Hooks + MCP config for Claude Code |
| `.mcp.json` | MCP server config |
| `CLAUDE.md` | Agent instructions |

---

## Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `CLAUDE_SESSION_ID` | Current session ID (set by Claude Code) | Auto |
| `BM_DATABASE_URL` | MatrixOne connection string | Yes |
| `BM_EMBEDDING_PROVIDER` | "openai", "doubao", or "mock" | Yes |
| `BM_TASK_ID` | Active task ID (multi-agent) | Optional |
| `BM_AGENT_ID` | Agent identifier | Optional |
| `BM_PARENT_SESSION` | Parent session for context handoff | Optional |
