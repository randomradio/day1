# Task Engines

> TaskEngine, ConsolidationEngine — multi-agent coordination and memory distillation.

## Design Rationale

Tasks represent **long-running, multi-agent work** — the kind of work where an agent swarm collaborates. A task creates a branch hierarchy, assigns agents to sub-branches, tracks objectives, and eventually consolidates knowledge back to the parent branch.

This is where **individual memory meets collective memory**:
- Each agent operates in individual memory mode (precise, session-scoped, low-latency)
- The task consolidation process produces collective memory (curated, verified, merged to main)

```
┌──────────────────────────────────────────────────────────┐
│                  TASK LIFECYCLE                            │
│                                                            │
│  create_task("fix-auth", parent="main")                   │
│       │                                                    │
│       ├──→ Creates branch: task/fix-auth                  │
│       │                                                    │
│       ├──→ assign_agent("agent_1", role="implementer")    │
│       │       └──→ Creates branch: task/fix-auth/agent_1  │
│       │                                                    │
│       ├──→ assign_agent("agent_2", role="reviewer")       │
│       │       └──→ Creates branch: task/fix-auth/agent_2  │
│       │                                                    │
│       │    [Agents work independently on their branches]   │
│       │                                                    │
│       ├──→ complete_agent("agent_1")                       │
│       │       └──→ Session consolidation                   │
│       │       └──→ Agent consolidation (cross-session dedup)│
│       │                                                    │
│       ├──→ complete_agent("agent_2")                       │
│       │       └──→ Session consolidation                   │
│       │       └──→ Agent consolidation                     │
│       │                                                    │
│       ├──→ complete_task()                                  │
│       │       └──→ Task consolidation (classify durable vs │
│       │            ephemeral facts)                         │
│       │       └──→ Optional: merge durable facts to main  │
│       │                                                    │
│       └──→ Branches archived or kept for reference         │
└──────────────────────────────────────────────────────────┘
```

---

## TaskEngine

**Source**: `src/day1/core/task_engine.py`

### Purpose
Manages the lifecycle of multi-agent tasks: creation, agent assignment, objective tracking, completion, and reporting.

### Core Operations

| Method | Purpose |
|---|---|
| `create_task()` | Create task with name, description, objectives, parent branch |
| `get_task()` | Retrieve task metadata |
| `list_tasks()` | List tasks with filters |
| `assign_agent()` | Agent joins task with role (creates agent sub-branch) |
| `complete_agent()` | Agent finishes work (triggers agent consolidation) |
| `update_objective()` | Update objective status (todo → active → done) |
| `complete_task()` | Mark task complete, trigger task consolidation |
| `get_task_context()` | Assemble full task context (objectives, agent summaries, key facts) |

### Objective Tracking

Tasks have structured objectives with status tracking:

```json
{
  "objectives": [
    { "description": "Fix auth middleware", "status": "done", "agent_id": "agent_1" },
    { "description": "Add test coverage", "status": "active", "agent_id": "agent_2" },
    { "description": "Update documentation", "status": "todo" }
  ]
}
```

Status progression: `todo → active → done | blocked`

### Task Context Assembly

`get_task_context()` assembles everything a new agent needs to understand a task:
- Task metadata (name, description, type)
- Objectives with status
- Agent summaries (what each agent did)
- Key facts from the task branch
- Progress metrics (done/active/todo counts)

This is injected by the `SessionStart` hook when `BM_TASK_ID` is set.

### Entry Points

| Surface | Trigger | Method |
|---|---|---|
| **API** | `POST /tasks` | `create_task()` |
| **API** | `POST /tasks/{id}/join` | `assign_agent()` |
| **API** | `POST /tasks/{id}/agents/{agent_id}/complete` | `complete_agent()` |
| **API** | `PATCH /tasks/{id}/objectives/{obj_id}` | `update_objective()` |
| **API** | `POST /tasks/{id}/complete` | `complete_task()` |
| **Hook** | SessionStart (with BM_TASK_ID) | `get_task_context()` |

---

## ConsolidationEngine

**Source**: `src/day1/core/consolidation_engine.py`

### Purpose
The core mechanism for **memory formation** — distilling raw observations into structured facts, deduplicating across sessions, and classifying knowledge as durable or ephemeral.

This engine implements the transition from sensory/working memory to short-term and long-term memory.

### Three-Level Consolidation

```
┌──────────────────────────────────────────────────────┐
│              THREE-LEVEL CONSOLIDATION                 │
│                                                        │
│  Level 1: Session                                      │
│  ┌────────────────────────────────────────────┐       │
│  │ Observations (insight/decision/discovery)   │       │
│  │     │                                       │       │
│  │     ▼                                       │       │
│  │ Jaccard similarity > 0.85 against existing  │       │
│  │     │                    │                  │       │
│  │     ▼                    ▼                  │       │
│  │ Existing fact:       New fact:              │       │
│  │ boost confidence     create with 0.7 conf   │       │
│  └────────────────────────────────────────────┘       │
│                                                        │
│  Level 2: Agent                                        │
│  ┌────────────────────────────────────────────┐       │
│  │ All facts on agent's branch                 │       │
│  │     │                                       │       │
│  │     ▼                                       │       │
│  │ Cross-session deduplication (Union-Find)    │       │
│  │     │                                       │       │
│  │     ▼                                       │       │
│  │ Generate agent summary fact                 │       │
│  └────────────────────────────────────────────┘       │
│                                                        │
│  Level 3: Task                                         │
│  ┌────────────────────────────────────────────┐       │
│  │ All facts on task branch                    │       │
│  │     │                                       │       │
│  │     ▼                                       │       │
│  │ Classify: durable vs ephemeral              │       │
│  │  durable = confidence ≥ 0.8                 │       │
│  │         AND category ∈ {bug_fix, arch,      │       │
│  │              pattern, decision, security,    │       │
│  │              performance}                    │       │
│  │     │                                       │       │
│  │     ▼                                       │       │
│  │ Durable facts → candidates for merge to main│       │
│  │ Ephemeral facts → stay on task branch       │       │
│  └────────────────────────────────────────────┘       │
└──────────────────────────────────────────────────────┘
```

### Deduplication Algorithm

Text-based deduplication using Jaccard similarity (no embedding dependency):

```python
def _jaccard_similarity(text_a, text_b):
    tokens_a = set(tokenize(text_a))  # lowercase, split on non-alphanumeric
    tokens_b = set(tokenize(text_b))
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
```

Threshold: 0.85 (high overlap = duplicate). Uses Union-Find for efficient grouping.

### Category Inference

For observations becoming facts, category is inferred from content:
- "bug", "fix", "error", "issue" → `bug_fix`
- "architect", "design", "structure" → `architecture`
- "security", "vulnerability", "auth" → `security`
- Decision observations → `decision`
- Discovery observations → `discovery`
- Default → `insight`

### Entry Points

| Surface | Trigger | Level |
|---|---|---|
| **Hook** | SessionEnd | Session consolidation |
| **API** | `POST /tasks/{id}/consolidate` | Session, Agent, or Task level |
| **TaskEngine** | `complete_agent()` | Agent consolidation |
| **TaskEngine** | `complete_task()` | Task consolidation |

### Consolidation Audit Trail

Every consolidation run creates a `ConsolidationHistory` record:
- Type (session_end, agent_complete, task_checkpoint)
- Source/target branches
- Facts created, updated, deduplicated
- Observations processed
- Summary text

---

## Discussion

1. **Consolidation timing**: Currently triggered at session end and task milestones. Should we consolidate more frequently (e.g., every N observations)?
2. **Deduplication quality**: Jaccard similarity is simple but may miss semantic duplicates with different wording. Should we use embedding similarity for dedup?
3. **Durable category set**: The fixed set of "durable" categories may not fit all domains. Should this be configurable?
4. **Cross-task consolidation**: Currently consolidation is within a task. Should we consolidate across tasks on the same project?
5. **Agent competition**: Two agents may produce contradictory facts. How to resolve conflicts during consolidation?
