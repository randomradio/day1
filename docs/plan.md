# Day1 — GitHub for Agent Conversations

**Vision**: A SaaS platform where every agent conversation is captured like git commits — branchable, searchable, forkable.

**Status**: Phase 1-4 Complete. Preparing for v0.1 Public Launch.

---

## Architecture: Three-Layer Model

```
┌───────────────────────────────────────────────────────────┐
│  CLIENTS                                                   │
│  Claude Code ─┐  Cursor ─┐  LangChain ─┐  Any Agent ─┐  │
│               ▼          ▼             ▼              ▼   │
│  ┌────────────────────────────────────────────────────┐   │
│  │  CAPTURE LAYER                                      │   │
│  │  HTTP API (65 endpoints) + Hooks (10) + MCP (37)   │   │
│  └──────────────────────┬─────────────────────────────┘   │
│                         ▼                                  │
│  ┌────────────────────────────────────────────────────┐   │
│  │  Layer 3: ANALYSIS (read-only, cross-branch)       │   │
│  │  ReplayEngine → SemanticDiff → LLM-as-Judge        │   │
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

**Commit**: `0ab01a4`

---

## Phase 4: Replay, Analytics & Eval (Complete)

**Why this phase**: Competitive research (Feb 2026) shows 12+ platforms doing
tracing and eval (LangSmith, Braintrust, Arize Phoenix, Langfuse, OpenAI Evals,
W&B Weave, Patronus, AgentOps, Logfire, etc.). **None of them support
conversation branching/forking as a first-class evaluation primitive.** Day1
already has fork + diff + branch on conversations. Replay & analytics turns
that into the agent eval workbench nobody else has.

### Competitive Gap

```
               Tracing   Eval   Replay   Branching   SemanticDiff
LangSmith        Y        Y      ~         N           N
Braintrust       Y        Y      ~         N           N
Arize Phoenix    Y        Y      ~         N           N
Langfuse         Y        Y      ~         N           N
OpenAI Evals     Y        Y      N         N           N
Patronus         Y        Y      ~         N           N
Day1             Y        Y      Y         Y           Y  <- unique
```

### 4a. Replay Engine (Complete)

| Component | Status |
|-----------|--------|
| `ReplayEngine` — fork at any message, re-execute | Done |
| `ReplayConfig` — model, prompt, temperature, tool filter | Done |
| 6 API endpoints: start, context, diff, semantic-diff, complete, list | Done |
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
| `AnalyticsEngine` — overview, session, agent, trends, conversation | Done |
| 5 API endpoints under `/analytics/*` | Done |
| MCP tools: `analytics_overview`, `analytics_session`, `analytics_agent`, `analytics_trends` | Done |

**Commit**: `7d276c3`

### 4d. Scoring Engine — LLM-as-Judge (Complete)

| Component | Status |
|-----------|--------|
| `Score` model + DB table (5 indexes) | Done |
| `ScoringEngine` with LLM-as-judge | Done |
| Default dimensions: helpfulness, correctness, coherence, efficiency | Done |
| Custom dimensions: safety, instruction_following, creativity, completeness | Done |
| Graceful fallback when no LLM configured (0.5 neutral scores) | Done |
| API endpoints: create, list, evaluate, summary | Done |
| MCP tools: `score_conversation`, `score_summary` | Done |

### 4e. Dashboard Phase 2 (Complete)

| Component | Status |
|-----------|--------|
| Tab navigation: Memory / Conversations / Analytics | Done |
| `ConversationList` — browse + select | Done |
| `ConversationThread` — message-by-message + inline LLM eval | Done |
| `ReplayList` — replay entries + diff trigger | Done |
| `SemanticDiffView` — 3-layer diff visualization | Done |
| `AnalyticsDashboard` — stat cards + D3 trend charts | Done |
| `conversationStore` — Zustand store for all new state | Done |
| API client with 13 new methods | Done |

### 4f. Tests (Complete)

| Test Class | Tests | Coverage |
|------------|-------|----------|
| TestReplayEngine | 8 | start, config, context, complete, list, diff |
| TestAnalyticsEngine | 6 | overview, session, conversation, trends |
| TestSemanticDiffEngine | 4 | identical, different tools, outcomes, divergence |
| TestScoringEngine | 7 | LLM judge, custom dims, fallback, manual, list, summary, clamp |
| TestLLMJudge | 3 | mock call, clamp, no-client fallback |

---

## v0.1 Public Launch Roadmap

### Release Goals

Ship a usable product that demonstrates Day1's unique value:
**branch, fork, replay, and evaluate any agent conversation**.

### Launch Blocklist (Must Complete)

| # | Item | Description | Status |
|---|------|-------------|--------|
| 1 | Docker Compose | Single `docker compose up` for FastAPI + MatrixOne + dashboard | Planned |
| 2 | Auto-create tables | `create_all` on startup (no Alembic needed for v0.1) | Planned |
| 3 | End-to-end smoke test | Prove full pipeline: write → search → fork → replay → diff → score | Planned |
| 4 | README quickstart | Install, configure, first conversation in 5 minutes | Planned |
| 5 | API key auth | Simple bearer token auth for API + MCP | Planned |
| 6 | CORS + rate limiting | Basic security for exposed API | Planned |

### Launch Differentiators (What We Demo)

```
1. Capture: Hook into Claude Code → every message auto-captured
2. Branch:  Fork a conversation at any message
3. Replay:  Re-run with different model/prompt/tools
4. Diff:    3-layer semantic diff (actions / reasoning / outcomes)
5. Score:   LLM-as-judge on any dimension
6. Analyze: Dashboard with trends, per-session/agent metrics
7. Search:  Hybrid BM25 + vector search across all conversations
```

No competitor has items 2-4 as first-class primitives.

### Post-Launch (v0.2+)

| Feature | Priority | Description |
|---------|----------|-------------|
| OTel ingest | High | Accept OpenTelemetry traces → auto-convert to Day1 conversations |
| Multi-tenancy | High | Org-level isolation via MO DATA BRANCH |
| Public sharing | Medium | Share conversations like GitHub gists |
| CLI tool | Medium | `day1 push/pull/fork` from terminal |
| CI/CD eval gates | Medium | Gate PRs on score thresholds in GitHub Actions |
| Webhooks | Low | Push notifications on conversation events |

---

## Inventory (as of Feb 2026)

| Category | Count |
|----------|-------|
| Core engines | 19 |
| DB models | 15 classes |
| API endpoints | 65 |
| MCP tools | 37 |
| Hooks | 10 |
| Dashboard components | 10 |
| Dashboard stores | 2 (Zustand) |
| Tests | 93 functions across 10 files |
| Python LOC | ~9.3k |
| TypeScript LOC | ~1.8k |

---

## Key Files

### Backend (Python)

| File | Purpose |
|------|---------|
| `src/branchedmind/db/models.py` | All ORM models (15 classes) |
| `src/branchedmind/db/engine.py` | DB engine + fulltext indexes |
| `src/branchedmind/core/replay_engine.py` | Replay: fork + re-execute |
| `src/branchedmind/core/semantic_diff.py` | 3-layer agent conversation diff |
| `src/branchedmind/core/analytics_engine.py` | Aggregate metrics + trends |
| `src/branchedmind/core/scoring_engine.py` | LLM-as-judge scoring |
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
| `src/branchedmind/api/routes/scores.py` | Scoring REST endpoints |
| `src/branchedmind/api/routes/conversations.py` | Conversation REST endpoints |
| `src/branchedmind/api/routes/messages.py` | Message REST endpoints |
| `src/branchedmind/mcp/tools.py` | 37 MCP tool definitions + handlers |
| `src/branchedmind/hooks/` | 10 Claude Code lifecycle hooks |

### Frontend (React + TypeScript)

| File | Purpose |
|------|---------|
| `dashboard/src/App.tsx` | Main app with tab navigation |
| `dashboard/src/types/schema.ts` | All TypeScript interfaces |
| `dashboard/src/api/client.ts` | API client (30+ methods) |
| `dashboard/src/stores/branchStore.ts` | Branch/memory state |
| `dashboard/src/stores/conversationStore.ts` | Conversation/replay/analytics state |
| `dashboard/src/components/BranchTree.tsx` | Branch DAG visualization |
| `dashboard/src/components/ConversationList.tsx` | Conversation browser |
| `dashboard/src/components/ConversationThread.tsx` | Message thread + LLM eval |
| `dashboard/src/components/SemanticDiffView.tsx` | 3-layer diff visualization |
| `dashboard/src/components/AnalyticsDashboard.tsx` | Charts + trends |
| `dashboard/src/components/ReplayList.tsx` | Replay entries |
| `dashboard/src/components/Timeline.tsx` | Chronological view |
| `dashboard/src/components/MergePanel.tsx` | Merge conflict resolution |

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
| `BM_LLM_API_KEY` | API key for LLM-as-judge scoring | For scoring |
| `BM_LLM_MODEL` | Model for LLM-as-judge (e.g. gpt-4o) | For scoring |
| `BM_LLM_BASE_URL` | Custom LLM endpoint (OpenAI-compatible) | Optional |
| `BM_TASK_ID` | Active task ID (multi-agent) | Optional |
| `BM_AGENT_ID` | Agent identifier | Optional |
| `BM_PARENT_SESSION` | Parent session for context handoff | Optional |
