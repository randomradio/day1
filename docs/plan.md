# Day1 — GitHub for Agent Conversations

**Vision**: A SaaS platform where every agent conversation is captured like git commits — branchable, searchable, forkable.

**Status**: Phase 1-2 Complete, Phase 3 In Progress, Phase 4 Planned

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

## Phase 4: Replay & Analytics Engine (Planned)

**Why this phase**: Competitive research (Feb 2026) shows 12+ platforms doing
tracing and eval (LangSmith, Braintrust, Arize Phoenix, Langfuse, OpenAI Evals,
W&B Weave, Patronus, AgentOps, Logfire, etc.). **None of them support
conversation branching/forking as a first-class evaluation primitive.** Day1
already has fork + diff + branch on conversations. Replay & analytics turns
that into the agent eval workbench nobody else has.

### Competitive Gap

```
               Tracing   Eval   Replay   Branching
LangSmith        ✓        ✓      ~         ✗
Braintrust       ✓        ✓      ~         ✗
Arize Phoenix    ✓        ✓      ~         ✗
Langfuse         ✓        ✓      ~         ✗
OpenAI Evals     ✓        ✓      ✗         ✗
Patronus         ✓        ✓      ~         ✗
Day1             ✓        →      →         ✓  ← unique
```

### 4a. Replay Engine (Backend)

Re-execute a conversation from any fork point with different parameters.

| Component | Description |
|-----------|-------------|
| `ReplayEngine` | Reconstruct conversation state at any message_id, optionally re-run from that point |
| `ReplayConfig` | Specify what changes: model, system prompt, tool availability, temperature |
| `ReplayResult` | Captures the new branch of messages produced by replay |
| Automatic forking | Replay creates a fork at the replay point, new messages go to the forked conversation |
| Diff on replay | Compare original vs replayed conversation (already have `diff_conversations`) |

**New files:**
- `src/branchedmind/core/replay_engine.py`

**New API endpoints:**
- `POST /api/v1/conversations/{id}/replay` — start replay from a message
- `GET /api/v1/replays/{id}` — get replay status + result
- `GET /api/v1/replays/{id}/diff` — diff original vs replay

**New MCP tools:**
- `replay_conversation(conversation_id, from_message_id, config)` — trigger replay
- `replay_diff(replay_id)` — get the diff

**How it works:**
```
Original conversation:
  msg-1 (user) → msg-2 (assistant) → msg-3 (user) → msg-4 (assistant/bad)

Replay from msg-3 with different system prompt:
  → fork_conversation at msg-3
  → inject new system prompt into forked conversation context
  → call LLM with messages [msg-1..msg-3] + new system prompt
  → store result as msg-4' in forked conversation
  → diff msg-4 vs msg-4' to see what changed
```

### 4b. Scoring & Evaluation

Score conversations and individual messages using multiple strategies.

| Component | Description |
|-----------|-------------|
| `ScoringEngine` | Pluggable scoring: LLM-as-judge, heuristic, human annotation |
| `Score` model | New DB table: score_id, target_type (message/conversation), target_id, scorer, dimension, value, explanation |
| LLM-as-judge | Use Claude to score on dimensions: helpfulness, correctness, safety, tool_use_quality |
| Heuristic scorers | Token efficiency, tool call count, error rate, latency |
| Pairwise comparison | Score branch A vs branch B (leverages existing diff) |
| Annotation API | Human-in-the-loop scoring via API + dashboard |

**New files:**
- `src/branchedmind/core/scoring_engine.py`
- `src/branchedmind/db/models.py` — add `Score` model

**New DB table:**
```sql
CREATE TABLE scores (
    id          VARCHAR(36) PRIMARY KEY,
    target_type ENUM('message', 'conversation', 'replay'),
    target_id   VARCHAR(36) NOT NULL,
    scorer      VARCHAR(100) NOT NULL,   -- 'llm_judge', 'heuristic', 'human'
    dimension   VARCHAR(100) NOT NULL,   -- 'helpfulness', 'correctness', etc.
    value       FLOAT NOT NULL,          -- 0.0 - 1.0
    explanation TEXT,
    metadata    TEXT,                     -- JsonText for scorer config
    branch_name VARCHAR(255) DEFAULT 'main',
    created_at  DATETIME DEFAULT NOW()
);
```

**New API endpoints:**
- `POST /api/v1/scores` — create a score
- `GET /api/v1/scores` — list scores (filter by target, dimension, scorer)
- `POST /api/v1/conversations/{id}/evaluate` — run LLM-as-judge on a conversation
- `GET /api/v1/conversations/{a}/compare/{b}` — pairwise comparison with scoring

**New MCP tools:**
- `score_conversation(conversation_id, dimensions)` — run auto-eval
- `score_message(message_id, dimensions)` — score a single message
- `compare_conversations(conv_a, conv_b, dimensions)` — pairwise eval

### 4c. Analytics Aggregation

Compute and expose metrics across sessions, conversations, and agents.

| Metric | Description |
|--------|-------------|
| Messages per session | Volume tracking |
| Tokens per conversation | Cost tracking |
| Facts extracted per session | Memory effectiveness |
| Tool call success rate | Tool reliability |
| Consolidation yield | Observations → facts conversion rate |
| Score distributions | Quality over time per dimension |
| Branch divergence | How much forked conversations differ |
| Replay improvement rate | % of replays that score higher than originals |

**New files:**
- `src/branchedmind/core/analytics_engine.py`

**New API endpoints:**
- `GET /api/v1/analytics/overview` — top-level dashboard metrics
- `GET /api/v1/analytics/sessions/{id}` — per-session breakdown
- `GET /api/v1/analytics/trends` — time-series metrics
- `GET /api/v1/analytics/agents/{id}` — per-agent performance

**New MCP tools:**
- `analytics_overview(branch, time_range)` — summary stats
- `analytics_session(session_id)` — session-level metrics

### 4d. Dashboard — Replay & Analytics UI

| Component | Description |
|-----------|-------------|
| Conversation list | Browse all conversations, filter by session/agent/status |
| Message thread view | Replay a conversation message-by-message |
| Fork visualization | Show conversation forks as a tree (React Flow) |
| Diff view | Side-by-side comparison of original vs replay |
| Score overlay | Show scores inline on messages + aggregate on conversations |
| Analytics dashboard | Charts: token usage, quality scores, tool success, trends over time |
| Replay controls | "Replay from here" button on any message, configure model/prompt |
| Session timeline | Combined view: messages + facts + observations chronologically |
| Search | Global semantic search with highlighted results |

### Phase 4 Execution Order

```
Step 1: Score model + ScoringEngine (foundation)
Step 2: ReplayEngine (fork + re-execute)
Step 3: AnalyticsEngine (aggregate metrics)
Step 4: API endpoints for all three
Step 5: MCP tools for all three
Step 6: Dashboard components
```

Each step ships independently. Step 1 has no dependencies. Steps 2-3 depend
on Step 1 (replays produce scores, analytics aggregate scores). Steps 4-5
wrap the engines. Step 6 is the UI layer.

---

## Phase 5: SaaS Platform (Planned)

Transform from developer tool to multi-tenant SaaS.

| Feature | Description |
|---------|-------------|
| Auth + multi-tenancy | User accounts, API keys, org-level isolation |
| Ingest API | Universal REST endpoint for any agent framework |
| OpenTelemetry ingest | Accept OTel traces, convert to Day1 conversations |
| Webhooks | Push notifications on conversation events |
| Usage tracking | Token counts, storage, API calls per tenant |
| Public conversation sharing | Share a conversation like a GitHub gist |
| CLI tool | `day1 push`, `day1 pull`, `day1 fork` from terminal |
| CI/CD eval integration | Run evals in GitHub Actions, gate PRs on score thresholds |

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
