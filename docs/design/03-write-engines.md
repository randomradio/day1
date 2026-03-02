# Write Engines

> FactEngine, MessageEngine, ObservationEngine, RelationEngine — the four engines that capture knowledge into Day1.

## Design Rationale

Why four separate write engines instead of one unified writer?

Each data type has different:
- **Capture triggers**: Facts are explicit or consolidated; observations are automatic; messages follow conversation flow
- **Embedding needs**: Facts always embed; observations sometimes; messages selectively
- **Lifecycle patterns**: Facts supersede; observations are immutable; messages are append-only
- **Quality signals**: Facts have confidence and verification; observations have outcomes; relations have temporal validity

Separating them allows each engine to optimize for its data type's specific patterns.

```
┌────────────────────────────────────────────────────┐
│                   WRITE PATH                        │
│                                                      │
│  Hook/MCP/API                                        │
│       │                                              │
│       ▼                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────┐  ┌────────┐ │
│  │  Fact    │  │ Message  │  │ Obs  │  │Relation│ │
│  │  Engine  │  │ Engine   │  │Engine│  │ Engine │ │
│  └────┬─────┘  └────┬─────┘  └──┬───┘  └───┬────┘ │
│       │              │           │           │      │
│       ▼              ▼           ▼           ▼      │
│  ┌──────────────────────────────────────────────┐  │
│  │         EmbeddingProvider                     │  │
│  │  (non-blocking: write succeeds even if       │  │
│  │   embedding fails)                            │  │
│  └──────────────────────┬───────────────────────┘  │
│                         ▼                           │
│  ┌──────────────────────────────────────────────┐  │
│  │         MatrixOne (INSERT)                    │  │
│  └──────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────┘
```

---

## FactEngine

**Source**: `src/day1/core/fact_engine.py`

### Purpose
CRUD operations for structured facts — the primary knowledge unit in Day1. Facts are discrete, verifiable statements with category, confidence, and optional embedding.

### Core Operations

| Method | Purpose | Parameters |
|---|---|---|
| `write_fact()` | Create a new fact | fact_text, category, confidence, source_type, session_id, branch_name, task_id, agent_id |
| `get_fact()` | Retrieve by ID | fact_id |
| `update_fact()` | Modify text/confidence/status | fact_id, updates dict |
| `list_facts()` | List with filters | branch_name, category, limit |
| `supersede_fact()` | Create new version | old_fact_id, new_fact_text |

### Entry Points

| Surface | Trigger | Method Called |
|---|---|---|
| **MCP** | `memory_write` tool | `MemoryEngine.write()` → fact creation |
| **Hook** | PreCompact (context window full) | `FactEngine.write_fact()` |
| **Hook** | SessionEnd (consolidation) | `ConsolidationEngine` → `FactEngine.write_fact()` |
| **API** | `POST /facts` | `FactEngine.write_fact()` |
| **CLI** | `write-fact <text>` | `FactEngine.write_fact()` |
| **Import** | `KnowledgeBundleEngine.import_bundle()` | `FactEngine.write_fact()` |

### Embedding Strategy
- Call `EmbeddingProvider.embed()` with fact_text
- If embedding succeeds → store as vecf32
- If embedding fails → log warning, save fact without embedding
- **Principle**: Writes always succeed. Embeddings are enrichment, not requirements.

### Lifecycle

```
Created (active, confidence 0.5-0.7)
    │
    ├──→ Confidence boost (consolidation finds duplicate) → stays active
    │
    ├──→ Superseded (new version created) → status = "superseded", parent_id set
    │
    ├──→ Verified (VerificationEngine) → metadata.verification_status = "verified"
    │
    ├──→ Invalidated (VerificationEngine) → metadata.verification_status = "invalidated"
    │
    └──→ Archived (branch archive) → status = "archived"
```

---

## MessageEngine

**Source**: `src/day1/core/message_engine.py`

### Purpose
Manages individual messages within conversations. Supports all roles (user, assistant, tool_call, tool_result) with optional embedding for semantic search.

### Core Operations

| Method | Purpose | Parameters |
|---|---|---|
| `write_message()` | Add message to conversation | conversation_id, role, content, thinking, tool_calls, sequence_num, token_count, session_id, agent_id, branch_name, embed |
| `get_message()` | Retrieve by ID | message_id |
| `list_messages()` | List for conversation | conversation_id, limit |
| `search_messages()` | Hybrid search | query, branch_name, limit |

### Entry Points

| Surface | Trigger | Method Called |
|---|---|---|
| **Hook** | UserPrompt | `MessageEngine.write_message(role="user")` |
| **Hook** | AssistantResponse | `MessageEngine.write_message(role="assistant")` |
| **Hook** | PostToolUse | `MessageEngine.write_message(role="tool_result")` |
| **API** | `POST /conversations/{id}/messages` | `MessageEngine.write_message()` |
| **API** | `POST /conversations/{id}/messages/batch` | Batch write |

### Embedding Strategy
- `embed=True` by default for user and assistant messages
- `embed=False` for tool_result messages (too noisy for semantic search)
- Configurable per write call

---

## ObservationEngine

**Source**: `src/day1/core/observation_engine.py`

### Purpose
Captures raw tool call observations — the "sensory memory" of the system. Every tool invocation is recorded with compressed summary, raw input/output, and outcome status.

### Core Operations

| Method | Purpose | Parameters |
|---|---|---|
| `write_observation()` | Record tool observation | session_id, observation_type, tool_name, summary, raw_input, raw_output, branch_name, task_id, agent_id |
| `get_observation()` | Retrieve by ID | observation_id |
| `list_observations()` | List with filters | session_id, observation_type, branch_name, limit |

### Entry Points

| Surface | Trigger | Method Called |
|---|---|---|
| **Hook** | PostToolUse (automatic, every tool call) | `ObservationEngine.write_observation()` |
| **API** | `POST /observations` | `ObservationEngine.write_observation()` |

### Compression
The PostToolUse hook compresses observations using `_compress_observation()`:
- `Bash` → "Executed command: {input}. Result: {output}"
- `Read` → "Read file: {path}"
- `Edit/Write` → "Modified file: {path}"
- `Grep` → "Searched for: {pattern}. Found: {results}"
- Other → "Used {tool}: {input}. Result: {output}"

All fields are truncated to 2000 characters to prevent storage bloat.

### Role in Memory Hierarchy
Observations are the **raw sensory input**. They are:
- Captured automatically (zero user action required)
- Not directly surfaced in search results (low signal-to-noise ratio)
- The raw material for consolidation (observations → facts)
- Valuable for analytics and timeline visualization

---

## RelationEngine

**Source**: `src/day1/core/relation_engine.py`

### Purpose
Manages the knowledge graph — entity-to-entity relationships with typed edges, confidence, and temporal validity.

### Core Operations

| Method | Purpose | Parameters |
|---|---|---|
| `write_relation()` | Create graph edge | source_entity, target_entity, relation_type, properties, confidence, branch_name |
| `graph_query()` | BFS traversal | entity, relation_type, depth, branch_name |
| `list_relations()` | List with filters | source, target, type, branch_name |

### Entry Points

| Surface | Trigger | Method Called |
|---|---|---|
| **API** | `POST /relations` | `RelationEngine.write_relation()` |
| **CLI** | `write-relation <source> <type> <target>` | `RelationEngine.write_relation()` |
| **MCP** | `memory_graph_query` (read only) | `RelationEngine.graph_query()` |

### Graph Query Algorithm
BFS traversal with configurable depth:
1. Start from entity node
2. Find all edges where entity is source or target
3. Follow edges up to specified depth
4. Return nodes and edges with properties

---

## Cross-Cutting Concerns

### Authentication
All write operations go through the same auth middleware:
1. **API**: Bearer token validation in FastAPI dependency
2. **MCP**: Session-based (MCP session ID in header)
3. **Hooks**: No auth (local subprocess, trusted)
4. **CLI**: No auth (local process, trusted)

### Error Handling
All write engines follow the same pattern:
```
try:
    embedding = await embedder.embed(text)
except Exception:
    embedding = None  # Non-fatal
    logger.warning("Embedding failed, saving without embedding")

# Write always succeeds
session.add(record)
await session.commit()
```

### Discussion
1. **Write amplification**: PostToolUse writes both an observation AND a message. Is this necessary? Could we deduplicate?
2. **Embedding cost**: Every write triggers an embedding API call. Should we batch? Queue?
3. **Write conflicts**: What happens if two agents write to the same branch simultaneously?
4. **Observation volume**: High-activity sessions may produce hundreds of observations. Should we sample?
