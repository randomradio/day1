# Day1 — GitHub for Agent Conversations

**Vision**: A SaaS platform where every agent conversation is captured like git commits — branchable, searchable, forkable.

**Status**: Phase 1-3 Complete, Phase 4 Steps 1-4 Complete (Step 5 In Progress)

---

## Architecture: Three-Layer Model

```
┌───────────────────────────────────────────────────────────┐
│  CLIENTS                                                   │
│  Claude Code ─┐  Cursor ─┐  LangChain ─┐  Any Agent ─┐  │
│               ▼          ▼             ▼              ▼   │
│  ┌────────────────────────────────────────────────────┐   │
│  │  CAPTURE LAYER                                      │   │
│  │  HTTP API (60 endpoints) + Hooks (10) + MCP (35)   │   │
│  └──────────────────────┬─────────────────────────────┘   │
│                         ▼                                  │
│  ┌────────────────────────────────────────────────────┐   │
│  │  Layer 3: ANALYSIS (read-only, cross-branch)       │   │
│  │  SemanticDiff ← ReplayEngine ← AnalyticsEngine     │   │
│  │  replay / semantic-diff / analytics / scoring       │   │
│  ├────────────────────────────────────────────────────┤   │
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

### Data Flow

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

## Phase 3: Hooks Config + Session Continuity (Complete)

| Component | Status |
|-----------|--------|
| 10 hook Python scripts (all 7 events) | Done |
| `claude_code_config.py` config generator | Done |
| `BM_PARENT_SESSION` env var support | Done |
| `SessionManager.get_session_context()` | Done |
| `GET /api/v1/sessions/{id}/context` endpoint | Done |
| `memory_session_context` MCP tool | Done |
| Enhanced SessionStart hook (parent session detection) | Done |

**Commit**: `0ab01a4`

---

## Phase 4: Replay & Analytics Engine (In Progress)

**Why this phase**: Competitive research (Feb 2026) shows 12+ platforms doing
tracing and eval (LangSmith, Braintrust, Arize Phoenix, Langfuse, OpenAI Evals,
W&B Weave, Patronus, AgentOps, Logfire, etc.). **None of them support
conversation branching/forking as a first-class evaluation primitive.** Day1
already has fork + diff + branch on conversations. Replay & analytics turns
that into the agent eval workbench nobody else has.

### Competitive Gap

```
               Tracing   Eval   Replay   Branching   SemanticDiff
LangSmith        ✓        ✓      ~         ✗           ✗
Braintrust       ✓        ✓      ~         ✗           ✗
Arize Phoenix    ✓        ✓      ~         ✗           ✗
Langfuse         ✓        ✓      ~         ✗           ✗
OpenAI Evals     ✓        ✓      ✗         ✗           ✗
Patronus         ✓        ✓      ~         ✗           ✗
Day1             ✓        ✓      ✓         ✓           ✓  ← unique
```

### 4a. Replay Engine (Complete)

| Component | Status |
|-----------|--------|
| `ReplayEngine` — fork at any message, re-execute | Done |
| `ReplayConfig` — model, prompt, temperature, tool filter | Done |
| `ReplayResult` — captures forked conversation state | Done |
| Automatic forking via `ConversationEngine.fork_conversation` | Done |
| `POST /conversations/{id}/replay` | Done |
| `GET /replays/{id}/context` — LLM-ready message history | Done |
| `GET /replays/{id}/diff` — text diff vs original | Done |
| `GET /replays/{id}/semantic-diff` — 3-layer diff vs original | Done |
| `POST /replays/{id}/complete` | Done |
| `GET /replays` — list with filters | Done |
| MCP tools: `replay_conversation`, `replay_diff`, `replay_list` | Done |

**Commit**: `7d276c3`

### 4b. Semantic Diff Engine (Complete)

3-layer diff purpose-built for agent conversations:

| Layer | What it compares | Method |
|-------|------------------|--------|
| Action Trace | Tool calls, order, args, errors | Sequence alignment + bigram similarity |
| Reasoning Trace | Assistant thinking/content | Embedding cosine similarity |
| Outcome Summary | Tokens, errors, efficiency | Aggregate stats + delta |

| Component | Status |
|-----------|--------|
| `SemanticDiffEngine` — 3-layer decomposition | Done |
| Divergence point detection | Done |
| Verdict system (equivalent/similar/divergent/mixed) | Done |
| `GET /conversations/{a}/semantic-diff/{b}` | Done |
| MCP tool: `semantic_diff` | Done |

**Commit**: `a8622c5`

### 4c. Analytics Engine (Complete)

| Component | Status |
|-----------|--------|
| `AnalyticsEngine` — aggregate metrics | Done |
| `overview()` — counts, tokens, activity, consolidation | Done |
| `session_analytics()` — per-session breakdown | Done |
| `agent_analytics()` — per-agent performance | Done |
| `trends()` — time-series by day/hour | Done |
| `conversation_analytics()` — single conversation metrics | Done |
| 5 API endpoints under `/analytics/*` | Done |
| MCP tools: `analytics_overview`, `analytics_session`, `analytics_agent`, `analytics_trends` | Done |

**Commit**: `7d276c3`

### 4d. Scoring Engine (In Progress)

| Component | Status |
|-----------|--------|
| `Score` model + DB table | In Progress |
| `ScoringEngine` — pluggable scorers | In Progress |
| Heuristic scorers (token efficiency, error rate) | In Progress |
| LLM-as-judge integration | Planned |
| API endpoints for scores | In Progress |
| MCP tools for scoring | In Progress |

### 4e. Dashboard — Replay & Analytics UI (In Progress)

| Component | Status |
|-----------|--------|
| `ConversationList` — browse + filter | In Progress |
| `ConversationThread` — message-by-message view | In Progress |
| `SemanticDiffView` — 3-layer diff visualization | In Progress |
| `AnalyticsDashboard` — charts + trends | In Progress |
| TypeScript types + API client for new endpoints | In Progress |

### Phase 4 Execution Order

```
Step 1: ReplayEngine (fork + re-execute)           ✓ Done
Step 2: AnalyticsEngine (aggregate metrics)         ✓ Done
Step 3: API endpoints for replay + analytics        ✓ Done
Step 4: MCP tools for replay + analytics            ✓ Done
     +: SemanticDiffEngine (3-layer agent diff)     ✓ Done
Step 5: Score model + ScoringEngine                 → In Progress
Step 6: Dashboard components                        → In Progress
Step 7: Tests for all Phase 4 engines               → In Progress
```

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

## Inventory (as of Feb 2026)

| Category | Count |
|----------|-------|
| Core engines | 16 |
| DB models | 14 classes |
| API endpoints | 60 |
| MCP tools | 35 |
| Hooks | 10 |
| Dashboard components | 7 (Phase 1 only) |
| Tests | 59 functions |
| Python LOC | ~10.7k |
| TypeScript LOC | ~940 |

---

## Key Files

### Backend (Python)

| File | Purpose |
|------|---------|
| `src/branchedmind/db/models.py` | All ORM models (14 classes) |
| `src/branchedmind/db/engine.py` | DB engine + fulltext indexes |
| `src/branchedmind/core/replay_engine.py` | Replay: fork + re-execute |
| `src/branchedmind/core/semantic_diff.py` | 3-layer agent conversation diff |
| `src/branchedmind/core/analytics_engine.py` | Aggregate metrics + trends |
| `src/branchedmind/core/message_engine.py` | Message CRUD + search |
| `src/branchedmind/core/conversation_engine.py` | Conversation lifecycle + fork + diff |
| `src/branchedmind/core/fact_engine.py` | Fact CRUD |
| `src/branchedmind/core/search_engine.py` | Hybrid BM25 + vector search |
| `src/branchedmind/core/session_manager.py` | Session tracking + context handoff |
| `src/branchedmind/core/branch_manager.py` | MO DATA BRANCH operations |
| `src/branchedmind/core/merge_engine.py` | Multi-strategy merge |
| `src/branchedmind/core/task_engine.py` | Multi-agent task coordination |
| `src/branchedmind/core/consolidation_engine.py` | Memory distillation |
| `src/branchedmind/api/routes/replays.py` | Replay REST endpoints |
| `src/branchedmind/api/routes/analytics.py` | Analytics REST endpoints |
| `src/branchedmind/api/routes/conversations.py` | Conversation REST endpoints |
| `src/branchedmind/api/routes/messages.py` | Message REST endpoints |
| `src/branchedmind/mcp/tools.py` | 35 MCP tool definitions + handlers |
| `src/branchedmind/hooks/` | 10 Claude Code lifecycle hooks |

### Frontend (React + TypeScript)

| File | Purpose |
|------|---------|
| `dashboard/src/types/schema.ts` | All TypeScript interfaces |
| `dashboard/src/api/client.ts` | API client methods |
| `dashboard/src/components/BranchTree.tsx` | Branch DAG visualization |
| `dashboard/src/components/Timeline.tsx` | Chronological view |
| `dashboard/src/components/MergePanel.tsx` | Merge conflict resolution |
| `dashboard/src/components/FactDetail.tsx` | Fact detail view |
| `dashboard/src/components/SearchBar.tsx` | Global search |

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
