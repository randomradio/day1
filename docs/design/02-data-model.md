# Data Model

> Complete schema definition with write/read/modify/delete entry points for every table.

## Overview

Day1's data model is organized into functional groups:

```
┌──────────────────────────────────────────────────────────────┐
│                       DATA MODEL                              │
│                                                                │
│  Layer 2 (Memory)          Layer 1 (History)                  │
│  ┌──────────┐              ┌──────────────┐                   │
│  │  facts   │◄────────────►│conversations │                   │
│  └────┬─────┘              └──────┬───────┘                   │
│       │                           │                            │
│  ┌────▼─────┐              ┌──────▼───────┐                   │
│  │relations │              │  messages    │                   │
│  └──────────┘              └──────────────┘                   │
│  ┌──────────────┐                                             │
│  │ observations  │                                             │
│  └──────────────┘                                             │
│                                                                │
│  Metadata           Coordination        Curation              │
│  ┌───────────┐     ┌──────────┐        ┌───────────────┐     │
│  │ branches  │     │  tasks   │        │handoff_records│     │
│  └───────────┘     └────┬─────┘        └───────────────┘     │
│  ┌───────────┐     ┌────▼─────┐        ┌───────────────┐     │
│  │merge_hist │     │task_agents│       │knowledge_     │     │
│  └───────────┘     └──────────┘        │bundles        │     │
│                    ┌──────────┐         └───────────────┘     │
│  Evaluation        │ sessions │                               │
│  ┌──────────┐      └──────────┘        Templates              │
│  │  scores  │                          ┌───────────────┐     │
│  └──────────┘      Time Travel         │template_      │     │
│  ┌──────────────┐  ┌──────────┐        │branches       │     │
│  │consolidation │  │snapshots │        └───────────────┘     │
│  │_history      │  └──────────┘                               │
│  └──────────────┘                                             │
└──────────────────────────────────────────────────────────────┘
```

### Branch Participation

Five tables participate in MatrixOne DATA BRANCH operations (table-level branching):

| Table | Branch Method | Main Table | Feature Branch Table |
|---|---|---|---|
| facts | DATA BRANCH | `facts` | `facts_feature_x` |
| relations | DATA BRANCH | `relations` | `relations_feature_x` |
| observations | DATA BRANCH | `observations` | `observations_feature_x` |
| conversations | DATA BRANCH | `conversations` | `conversations_feature_x` |
| messages | DATA BRANCH | `messages` | `messages_feature_x` |

All other tables use `branch_name` column filtering or are branch-independent.

---

## Table: `memories` (Simplified V2 Schema)

The current simplified schema consolidates the multi-table model into a single NL-first memory table.

**Schema**:
| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated unique identifier |
| `text` | TEXT | What happened (natural language) — the core memory |
| `context` | TEXT (nullable) | Why / how / outcome (freeform NL) |
| `file_context` | VARCHAR(500) (nullable) | Relevant file path |
| `session_id` | VARCHAR(100) (nullable) | WHO — session or agent identifier |
| `branch_name` | VARCHAR(100) | WHERE — branch (default: "main") |
| `embedding` | TEXT (nullable) | vecf32 format vector |
| `created_at` | DATETIME | WHEN — auto-populated |

**Indexes**: branch_name, session_id, file_context, created_at, FULLTEXT(text, context)

**Entry Points**:

| Operation | Entry Point | Source |
|---|---|---|
| **Write** | `MemoryEngine.write()` | MCP `memory_write` tool |
| **Write** | `PostToolUse` hook | Automatic tool observation |
| **Write** | `POST /ingest/mcp` | REST API |
| **Search** | `MemoryEngine.search()` | MCP `memory_search` tool |
| **Search** | `GET /facts/search` | REST API |
| **List** | `MemoryEngine.list()` | Implicit in search |
| **Delete** | (not implemented) | — |

---

## Table: `facts` (Layer 2 — Structured Knowledge)

The primary knowledge store. Each fact represents a discrete, verifiable piece of information.

**Schema**:
| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `fact_text` | TEXT | The knowledge statement |
| `category` | VARCHAR(50) | bug_fix, architecture, pattern, decision, security, etc. |
| `confidence` | FLOAT | 0.0–1.0 belief strength |
| `source_type` | VARCHAR(50) | manual, consolidation, bundle_import, etc. |
| `source_id` | VARCHAR(100) | ID of source (observation, bundle, etc.) |
| `session_id` | VARCHAR(100) | Session that created this fact |
| `task_id` | VARCHAR(100) | Associated task |
| `agent_id` | VARCHAR(100) | Agent that created this fact |
| `branch_name` | VARCHAR(100) | Branch where this fact lives |
| `status` | VARCHAR(20) | active, superseded, archived |
| `parent_id` | UUID | Previous version (for supersede chain) |
| `embedding` | TEXT | vecf32 format vector |
| `metadata_json` | JSON/TEXT | Verification status, tags, etc. |
| `created_at` | DATETIME | Creation timestamp |
| `updated_at` | DATETIME | Last modification |

**Entry Points**:

| Operation | Entry Point | Source |
|---|---|---|
| **Write** | `FactEngine.write_fact()` | API `POST /facts`, Hook: PreCompact |
| **Write** | `ConsolidationEngine.consolidate_session()` | Hook: SessionEnd |
| **Write** | `KnowledgeBundleEngine.import_bundle()` | API `POST /bundles/{id}/import` |
| **Read** | `FactEngine.get_fact()` | API `GET /facts/{id}` |
| **Search** | `SearchEngine.search()` | MCP `memory_search`, API `GET /facts/search` |
| **List** | `FactEngine.list_facts()` | API `GET /facts`, Hook: SessionStart |
| **Update** | `FactEngine.update_fact()` | API `PATCH /facts/{id}` |
| **Supersede** | `FactEngine.supersede_fact()` | ConsolidationEngine dedup |
| **Verify** | `VerificationEngine.verify_fact()` | API `POST /facts/{id}/verify` |
| **Archive** | Status → "archived" | BranchTopologyEngine auto-archive |

---

## Table: `relations` (Layer 2 — Entity Graph)

Knowledge graph edges connecting entities.

**Schema**:
| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `source_entity` | VARCHAR(200) | Source node |
| `target_entity` | VARCHAR(200) | Target node |
| `relation_type` | VARCHAR(100) | depends_on, causes, fixes, uses, etc. |
| `properties` | JSON/TEXT | Edge attributes |
| `confidence` | FLOAT | Edge confidence |
| `branch_name` | VARCHAR(100) | Branch |
| `valid_from` | DATETIME | Temporal validity start |
| `valid_to` | DATETIME | Temporal validity end |

**Entry Points**:

| Operation | Entry Point | Source |
|---|---|---|
| **Write** | `RelationEngine.write_relation()` | API `POST /relations`, CLI |
| **Query** | `RelationEngine.graph_query()` | API `GET /relations/graph`, MCP |
| **List** | `RelationEngine.list_relations()` | API `GET /relations` |

---

## Table: `observations` (Layer 2 — Tool Call Captures)

Raw observations from agent tool usage — the "sensory memory" layer.

**Schema**:
| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `session_id` | VARCHAR(100) | Session context |
| `observation_type` | VARCHAR(50) | tool_use, discovery, decision, error, insight |
| `tool_name` | VARCHAR(100) | Which tool was used |
| `summary` | TEXT | Compressed observation |
| `raw_input` | TEXT | Original tool input (truncated) |
| `raw_output` | TEXT | Original tool output (truncated) |
| `outcome` | VARCHAR(20) | success, error, timeout |
| `branch_name` | VARCHAR(100) | Branch |
| `task_id` | VARCHAR(100) | Associated task |
| `agent_id` | VARCHAR(100) | Agent |
| `embedding` | TEXT | vecf32 format |
| `created_at` | DATETIME | Timestamp |

**Entry Points**:

| Operation | Entry Point | Source |
|---|---|---|
| **Write** | `ObservationEngine.write_observation()` | Hook: PostToolUse (automatic) |
| **Write** | `POST /observations` | REST API |
| **List** | `ObservationEngine.list_observations()` | API, Dashboard timeline |
| **Search** | `SearchEngine.search_observations()` | API `GET /observations/search` |
| **Consolidate** | `ConsolidationEngine.consolidate_session()` | observations → facts |

---

## Table: `conversations` (Layer 1 — Chat Threads)

Thread-level chat history tracking.

**Schema**:
| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `session_id` | VARCHAR(100) | Owning session |
| `agent_id` | VARCHAR(100) | Owning agent |
| `task_id` | VARCHAR(100) | Associated task |
| `branch_name` | VARCHAR(100) | Branch |
| `title` | VARCHAR(500) | Conversation title |
| `status` | VARCHAR(20) | active, completed, archived |
| `model` | VARCHAR(100) | LLM model used |
| `message_count` | INT | Total messages |
| `total_tokens` | INT | Total token usage |
| `parent_conversation_id` | UUID | Parent (for forks) |
| `fork_point_message_id` | UUID | Where fork happened |
| `metadata_json` | JSON/TEXT | Extra metadata |
| `created_at` | DATETIME | Creation time |

**Entry Points**:

| Operation | Entry Point | Source |
|---|---|---|
| **Create** | `ConversationEngine.create_conversation()` | Hook: SessionStart |
| **Create** | `POST /conversations` | REST API |
| **Fork** | `ConversationEngine.fork_conversation()` | API, ReplayEngine |
| **Complete** | `ConversationEngine.close_conversation()` | Hook: SessionEnd |
| **List** | `ConversationEngine.list_conversations()` | API, Dashboard |
| **Diff** | `SemanticDiffEngine.semantic_diff()` | API `GET /conversations/{a}/semantic-diff/{b}` |

---

## Table: `messages` (Layer 1 — Individual Messages)

Individual messages within conversations.

**Schema**:
| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `conversation_id` | UUID (FK) | Parent conversation |
| `role` | VARCHAR(20) | user, assistant, tool_call, tool_result |
| `content` | TEXT | Message content |
| `thinking` | TEXT | Agent thinking (if captured) |
| `tool_calls_json` | JSON/TEXT | Tool call details |
| `model` | VARCHAR(100) | Model that generated |
| `sequence_num` | INT | Order within conversation |
| `token_count` | INT | Token usage |
| `session_id` | VARCHAR(100) | Session |
| `agent_id` | VARCHAR(100) | Agent |
| `branch_name` | VARCHAR(100) | Branch |
| `embedding` | TEXT | vecf32 format |
| `created_at` | DATETIME | Timestamp |

**Entry Points**:

| Operation | Entry Point | Source |
|---|---|---|
| **Write** | `MessageEngine.write_message()` | Hook: UserPrompt, AssistantResponse, PostToolUse |
| **Write** | `POST /conversations/{id}/messages` | REST API |
| **Batch** | `POST /conversations/{id}/messages/batch` | REST API |
| **Read** | `MessageEngine.get_message()` | API `GET /messages/{id}` |
| **List** | `MessageEngine.list_messages()` | API `GET /conversations/{id}/messages` |
| **Search** | `MessageEngine.search_messages()` | API `GET /messages/search` |

---

## Metadata & Coordination Tables

### `branches` / `branch_registry`
Tracks branch lifecycle. **Write**: BranchManager.create_branch(). **Read**: BranchManager.list_branches().

### `merge_history`
Audit trail of all merges. **Write**: MergeEngine.merge(). **Read**: API, Dashboard.

### `sessions`
Session tracking with parent-child relationships. **Write**: SessionManager.create_session() (Hook: SessionStart). **Read**: SessionManager.get_session(), AnalyticsEngine.

### `tasks` + `task_agents`
Multi-agent task coordination. **Write**: TaskEngine.create_task(), TaskEngine.assign_agent(). **Read**: TaskEngine.get_task(), AnalyticsEngine.

### `template_branches`
Reusable knowledge templates. **Write**: TemplateEngine.create_template(). **Read**: TemplateEngine.list_templates().

### `snapshots`
Point-in-time recovery metadata. **Write**: SnapshotManager.create_snapshot(). **Read**: SnapshotManager.list_snapshots().

### `handoff_records`
Structured task handoff audit trail. **Write**: HandoffEngine.create_handoff(). **Read**: HandoffEngine.get_handoff_packet().

### `knowledge_bundles`
Portable knowledge packages. **Write**: KnowledgeBundleEngine.create_bundle(). **Read**: KnowledgeBundleEngine.list_bundles().

### `scores`
Quality evaluation scores. **Write**: ScoringEngine.score_conversation(), VerificationEngine.verify_fact(). **Read**: ScoringEngine.list_scores().

### `consolidation_history`
Observation → fact distillation audit. **Write**: ConsolidationEngine (all levels). **Read**: AnalyticsEngine.

---

## JsonText Custom Type

Branch-participating tables use a custom `JsonText` SQLAlchemy type that stores JSON as TEXT:

```python
class JsonText(TypeDecorator):
    """Store JSON as TEXT for MatrixOne DATA BRANCH compatibility."""
    impl = Text
    # Avoids MySQL type 245 issue with DATA BRANCH DIFF
```

This is necessary because MatrixOne's DATA BRANCH DIFF does not correctly handle native JSON columns — it reports spurious type 245 errors. Storing as TEXT avoids this while maintaining transparent JSON serialization/deserialization in Python.

---

## Discussion: Data Model Considerations

1. **Schema evolution**: How to handle adding columns to branch-participating tables (all branch copies need ALTER TABLE)
2. **Soft delete vs hard delete**: Currently all deletes are soft (status change). Should we support hard delete for GDPR?
3. **Embedding backfill**: Memories created without embeddings (mock provider) — how to backfill when a real provider is configured
4. **Index optimization**: Which columns need additional indexes for collective-scale (100K+ rows) performance
5. **JsonText limitation**: Trading off JSON query capabilities for DATA BRANCH compatibility — acceptable trade-off?
