# Day1 System Overview

> **Day1** — A Git-like memory layer for AI agents. Manages writes, retrieval, branching, merging, snapshots, and time-travel.

## Why Day1 Exists

AI agents today operate in a peculiar cognitive state: they are extraordinarily capable within a single session, yet suffer complete amnesia between sessions. Every new conversation starts from scratch. Every hard-won insight, every debugged pattern, every architectural decision — lost the moment the context window closes.

Existing solutions (claude-mem, mem0, etc.) address this partially but miss critical capabilities:

| Capability | claude-mem | mem0 | **Day1** |
|---|---|---|---|
| Auto-capture | Yes | Yes | **Yes** |
| Branching | No | No | **Yes (MatrixOne DATA BRANCH)** |
| Time-travel / PITR | No | No | **Yes** |
| Multi-agent isolation | No | Partial | **Yes (branch per agent)** |
| Knowledge graph | SQLite | Vector only | **Yes (relations table)** |
| Vector + BM25 hybrid search | Chroma | Yes | **Yes (MatrixOne native)** |
| Verification / quality gates | No | No | **Yes (LLM-as-judge)** |
| Task handoff protocol | No | No | **Yes** |
| Template system | No | No | **Yes** |
| Zero-copy branches | No | No | **Yes** |

Day1 fills this gap: it is a **pure memory layer** — not an orchestration platform, not an agent framework. It does not decide what agents do. It manages what they remember.

---

## The Fundamental Insight: Individual Memory is Finite, Collective Memory is a Corpus

A critical design principle underlies everything in Day1: **even the most prolific individual produces finite output**. Tolkien spent a lifetime creating Middle-earth — and his total written output is roughly 10 million words. A single AI agent completing even an extraordinary task produces perhaps thousands of meaningful facts, not millions.

This insight drives two fundamentally different memory regimes that Day1 must serve:

### Individual Memory (Single Agent / Person)

- Memory should be **precise and effective** — not a data lake
- Strong **temporal layering** is essential (recent context first, older context by relevance)
- The system should surface the *right* memory at the *right* time
- Even for an extraordinary task, useful facts number in the hundreds
- **Design goal: instant recall** of highly relevant, recent context

### Collective Memory (Organization / Agent Swarm)

- Large-scale memory only emerges when a **collective** operates: a corporation, a 50-agent swarm
- This is fundamentally a **knowledge corpus** requiring retrieval + deep understanding
- Getting the right answer may take time — this is acceptable and expected
- **Design goal: efficient retrieval** with deep understanding, not instant recall
- Opportunity: shorten retrieval time through better indexing, curation, and pre-distillation

```
┌───────────────────────────────────────────────────────────┐
│                   MEMORY SCALE SPECTRUM                     │
│                                                             │
│   Individual Agent           │        Collective / Swarm    │
│   ──────────────────────────┼───────────────────────────── │
│   10s–100s of facts         │   10K–1M+ facts              │
│   Precise, temporally layered│   Corpus, retrieval-based    │
│   Instant recall             │   Search + understanding     │
│   Session → Branch → Main   │   Cross-branch knowledge     │
│   Consolidation matters      │   Curation matters more      │
│   Temporal hierarchy key     │   Semantic clustering key    │
│   Low latency required       │   Acceptable latency         │
│                              │                              │
│   ← Day1 optimizes here first                              │
│                then scales here →                           │
└───────────────────────────────────────────────────────────┘
```

Day1 is **optimized for individual/small-team use first** (precise temporal layering, session-scoped consolidation, verification gates), with **architectural hooks for collective scale** (branches, templates, bundles, cross-branch search). The knowledge evolution pipeline acts as a **natural compression function** — keeping individual memory small and precise, while allowing collective knowledge to accumulate.

---

## Design Philosophy

### Pure Memory Layer

Day1 is a **pure memory layer**, independent of the upper application:

- Works with **any MCP-compatible client**: Claude Code, Agent SDK, Cursor, Copilot
- **No agent orchestration** — Day1 doesn't decide what agents do, only what they remember
- **Limited LLM dependency** — Only 2 of 26 engines call LLM directly (ScoringEngine and VerificationEngine)
- Both LLM-dependent engines **degrade gracefully** to heuristic scoring when LLM is unavailable
- **Embedding is non-blocking** — all writes succeed even if embedding fails; embeddings are best-effort enrichment

### Transport Agnostic

Day1 exposes the same capabilities through four integration surfaces:

| Surface | Protocol | Primary Use |
|---|---|---|
| **Claude Code Hooks** | Shell subprocess | Automatic capture (zero-config) |
| **MCP Server** | HTTP streamable_http | Agent-initiated operations |
| **REST API** | HTTP/JSON | Dashboard, external integrations |
| **CLI** | Shell commands | Developer workflow, scripting |

All four surfaces call the same 26 core engines. No business logic lives in the integration layer.

---

## Human-Like Multi-Layer Memory

Day1's architecture is deliberately inspired by human cognitive memory systems. This is not a metaphor — it is a design principle that shapes data flow, retention policies, and consolidation logic.

```
┌────────────────────────────────────────────────────────────┐
│                     MEMORY HIERARCHY                        │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Sensory Memory (milliseconds → seconds)              │  │
│  │  ├── observations: raw tool calls, file reads          │  │
│  │  ├── Captured by: PostToolUse hook (automatic)         │  │
│  │  └── Retention: all kept, low-priority for recall      │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         ▼ attention filter                    │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Working Memory (seconds → minutes)                    │  │
│  │  ├── messages: active conversation thread               │  │
│  │  ├── Captured by: UserPrompt + AssistantResponse hooks  │  │
│  │  └── Retention: current session, context window         │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         ▼ rehearsal / consolidation           │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Short-Term Memory (minutes → hours)                   │  │
│  │  ├── facts (session-scoped): insights from this work    │  │
│  │  ├── Captured by: PreCompact hook + session-end consol  │  │
│  │  └── Retention: session branch, confidence 0.5–0.7      │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         ▼ verification + merge                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Long-Term Memory (hours → permanent)                  │  │
│  │  ├── facts (verified, main branch): durable knowledge   │  │
│  │  ├── relations: entity graph connections                 │  │
│  │  ├── Captured by: merge to main with verification gate  │  │
│  │  └── Retention: permanent, high confidence (≥ 0.8)      │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         ▼ crystallization                     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Procedural Memory (permanent, reusable patterns)      │  │
│  │  ├── template_branches: learned procedures              │  │
│  │  ├── knowledge_bundles: portable knowledge packages     │  │
│  │  ├── Captured by: TemplateEngine + BundleEngine         │  │
│  │  └── Retention: versioned, evolving, shareable          │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

| Human Memory | Day1 Equivalent | Mechanism |
|---|---|---|
| **Sensory Memory** (raw input, ~seconds) | `observations` — raw tool call captures | PostToolUse hook captures every action |
| **Working Memory** (active processing) | `messages` + `conversations` — active session | SessionStart injects, PreCompact extracts |
| **Short-Term Memory** (session context) | `facts` with session scope | Session-end consolidation |
| **Long-Term Memory** (durable knowledge) | Verified `facts` on `main` branch | Verification + merge to main |
| **Procedural Memory** (how to do things) | `template_branches` + `knowledge_bundles` | Templates = learned procedures |
| **Episodic Memory** (what happened when) | `conversations` + `messages` timeline | Full chat history with timestamps |
| **Semantic Memory** (general knowledge) | `facts` + `relations` knowledge graph | Extracted, verified, graph-connected |

The consolidation pipeline mirrors human memory formation:
- **Repetition strengthens**: when an observation matches an existing fact, confidence increases
- **Irrelevant details fade**: ephemeral facts (low confidence, non-durable category) stay on task branches
- **Important patterns crystallize**: durable facts (high confidence, architectural/pattern/decision) merge to main and eventually become templates

---

## Key Moment Recording

The system captures at **critical decision points** through automatic and explicit mechanisms:

```
Session Start ──→ SessionStart Hook ──→ Inject prior context
       │
       ▼
User Input ──→ UserPrompt Hook ──→ Record in conversation
       │
       ▼
Agent Thinks ──→ (internal, not captured directly)
       │
       ▼
Tool Call ──→ PreToolUse Hook ──→ Pre-context capture
       │
       ▼
Tool Result ──→ PostToolUse Hook ──→ Observation + Message
       │
       ▼
Agent Response ──→ AssistantResponse Hook ──→ Record in conversation
       │
       ├──→ [If important insight] ──→ memory_write (explicit)
       │
       ├──→ [If risky change] ──→ memory_snapshot (explicit)
       │
       ├──→ [If context window full] ──→ PreCompact Hook ──→ Extract facts
       │
       ▼
Session End ──→ SessionEnd Hook ──→ Consolidate observations → facts
       │
       ▼
Task Complete ──→ TaskEngine.complete() ──→ Agent consolidation
       │                                      + optional merge to main
       ▼
Knowledge Matures ──→ VerificationEngine ──→ Merge Gate → main branch
```

| Critical Moment | Capture Mechanism | Storage Layer |
|---|---|---|
| Session starts | `SessionStart` hook | Session record + context injection |
| Every tool call | `PostToolUse` hook | Observation + message |
| User input | `UserPrompt` hook | Conversation message |
| Agent response | `AssistantResponse` hook | Conversation message |
| Context window full | `PreCompact` hook | Extract facts before losing context |
| Explicit insight | `memory_write` MCP tool | Fact with high confidence |
| Session ends | `SessionEnd` hook | Consolidation: observations → facts |
| Task completes | `TaskEngine.complete()` | Consolidation + optional merge |
| Before risky changes | `memory_snapshot` MCP tool | PITR snapshot |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                 Upper Layer (NOT our concern)                     │
│    Claude Code │ Agent SDK │ Cursor │ Copilot │ Any MCP Client  │
└──────────┬────────────────────────────────┬─────────────────────┘
           │                                │
           ▼                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Integration Layer                             │
│                                                                   │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────┐  │
│  │ Claude Code │  │ MCP Server │  │  REST API  │  │   CLI    │  │
│  │  Hooks (11) │  │ (8 tools)  │  │ (85+ eps)  │  │ (20+ cmd)│  │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘  └────┬─────┘  │
│        └────────────────┼───────────────┼──────────────┘         │
│                         ▼               ▼                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Core Engine Layer (26 engines)                │   │
│  │                                                            │   │
│  │  Write    [Fact │ Message │ Observation │ Relation]        │   │
│  │  Query    [Search │ Analytics │ SessionManager]            │   │
│  │  Branch   [BranchMgr │ Merge │ Snapshot │ Topology]       │   │
│  │  Conv     [Conversation │ CherryPick │ Replay]            │   │
│  │  Task     [TaskEngine │ Consolidation]                     │   │
│  │  Curation [Template │ Verification* │ Handoff │ Bundle]   │   │
│  │  Analysis [SemanticDiff │ Scoring*]                        │   │
│  │  Infra    [EmbeddingProvider │ LLMClient]                  │   │
│  │                                    * = LLM-dependent       │   │
│  └────────────────────────┬─────────────────────────────────┘   │
│                           ▼                                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                MatrixOne Database                          │   │
│  │                                                            │   │
│  │  DATA BRANCH │ vecf32 │ FULLTEXT │ PITR │ Snapshot        │   │
│  │                                                            │   │
│  │  Layer 2 (Memory):  facts, relations, observations        │   │
│  │  Layer 1 (History): conversations, messages                │   │
│  │  Metadata:          branches, merge_history                │   │
│  │  Coordination:      sessions, tasks, task_agents           │   │
│  │  Templates:         template_branches                      │   │
│  │  Curation:          handoff_records, knowledge_bundles     │   │
│  │  Evaluation:        scores, consolidation_history          │   │
│  │  Time Travel:       snapshots                              │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 26 Engine Catalog

| # | Engine | Category | LLM | Purpose |
|---|---|---|---|---|
| 1 | FactEngine | Write | No | CRUD for structured facts with embeddings |
| 2 | MessageEngine | Write | No | Conversation messages with hybrid search |
| 3 | ObservationEngine | Write | No | Tool call observation capture |
| 4 | RelationEngine | Write | No | Entity relationship graph operations |
| 5 | SearchEngine | Query | No | Hybrid BM25 + vector search over facts |
| 6 | AnalyticsEngine | Query | No | Aggregate metrics across sessions, agents |
| 7 | SessionManager | Query | No | Session lifecycle, context packaging |
| 8 | BranchManager | Branch | No | Git-like branch ops via DATA BRANCH |
| 9 | MergeEngine | Branch | No | Four merge strategies with conflict detection |
| 10 | SnapshotManager | Branch | No | Point-in-time recovery snapshots |
| 11 | BranchTopologyEngine | Branch | No | Hierarchical tree, auto-archive, TTL |
| 12 | ConversationEngine | Conv | No | Thread management, session linking |
| 13 | CherryPick | Conv | No | Selective message extraction |
| 14 | ReplayEngine | Conv | No | Fork-at-message for re-execution |
| 15 | TaskEngine | Task | No | Multi-agent task lifecycle |
| 16 | ConsolidationEngine | Task | No | Observation → fact distillation |
| 17 | TemplateEngine | Curation | No | Reusable knowledge templates |
| 18 | VerificationEngine | Curation | **Yes** | LLM-as-judge fact verification |
| 19 | HandoffEngine | Curation | No | Structured task handoff protocol |
| 20 | KnowledgeBundleEngine | Curation | No | Portable knowledge packages |
| 21 | SemanticDiffEngine | Analysis | No | Three-layer conversation diff |
| 22 | ScoringEngine | Analysis | **Yes** | LLM-as-judge quality scoring |
| 23 | EmbeddingProvider | Infra | — | Vector embedding (OpenAI/Doubao/Mock) |
| 24 | LLMClient | Infra | — | OpenAI-compatible LLM access |
| 25 | MemoryEngine | Legacy | No | Simplified write + search facade |
| 26 | Exceptions | Infra | — | Custom exception hierarchy |

**Key principle**: Only 2 of 26 engines (8%) require LLM. The remaining 24 engines operate with zero LLM calls, making the system fully functional even without an LLM API key.

---

## Document Index

| File | Focus |
|---|---|
| [01 — MatrixOne Foundation](01-matrixone-foundation.md) | Database capabilities and how we leverage them |
| [02 — Data Model](02-data-model.md) | Complete schema with entry points per table |
| [03 — Write Engines](03-write-engines.md) | Fact, Message, Observation, Relation engines |
| [04 — Query Engines](04-query-engines.md) | Search, Analytics, Session Manager |
| [05 — Branch Engines](05-branch-engines.md) | Branch, Merge, Snapshot, Topology |
| [06 — Conversation Engines](06-conversation-engines.md) | Conversation, CherryPick, Replay |
| [07 — Task Engines](07-task-engines.md) | Task, Consolidation |
| [08 — Curation Engines](08-curation-engines.md) | Template, Verification, Handoff, Bundle |
| [09 — Analysis Engines](09-analysis-engines.md) | SemanticDiff, Scoring |
| [10 — Infrastructure](10-infrastructure.md) | Embedding, LLM, DB, Config |
| [11 — Integration Layer](11-integration-layer.md) | MCP, REST API, Hooks, CLI |
| [12 — Auth & Security](12-auth-security.md) | Authentication, isolation, security model |
| [13 — Knowledge Evolution](13-knowledge-evolution.md) | Full pipeline from observation to reuse |
| [14 — Dashboard](14-dashboard.md) | Frontend architecture |
| [15 — Testing Strategy](15-testing-strategy.md) | E2E, acceptance, unit testing |
| [16 — Open Questions](16-open-questions.md) | Discussion topics and future directions |
