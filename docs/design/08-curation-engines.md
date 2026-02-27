# Curation Engines

> TemplateEngine, VerificationEngine, HandoffEngine, KnowledgeBundleEngine — the knowledge quality and reuse pipeline.

## Design Rationale

Curation is what transforms raw agent output into **organizational knowledge**. Without curation, agent memory is just a log. With curation, it becomes a reusable asset.

The curation pipeline has four stages:

```
┌─────────────────────────────────────────────────────────┐
│                  CURATION PIPELINE                        │
│                                                           │
│  ┌─────────────┐     ┌──────────────┐                   │
│  │ Verification │────→│   Handoff    │                   │
│  │ (quality     │     │ (agent →     │                   │
│  │  gate)       │     │  agent)      │                   │
│  └──────┬──────┘     └──────────────┘                   │
│         │                                                │
│         ├──────────────────────────────┐                 │
│         ▼                              ▼                 │
│  ┌─────────────┐              ┌──────────────┐          │
│  │  Template   │              │  Knowledge   │          │
│  │ (reusable   │              │  Bundle      │          │
│  │  branch     │              │ (portable    │          │
│  │  patterns)  │              │  package)    │          │
│  └─────────────┘              └──────────────┘          │
└─────────────────────────────────────────────────────────┘
```

---

## VerificationEngine

**Source**: `src/day1/core/verification_engine.py`

### Purpose
Quality gate for facts. Uses LLM-as-judge to evaluate accuracy, relevance, and specificity. **This is one of only two engines that call LLM** — and it gracefully degrades to heuristic scoring when LLM is unavailable.

### Verification Flow

```
Fact submitted for verification
       │
       ├──→ LLM available?
       │       │
       │       ├──→ Yes: Call LLM with structured prompt
       │       │       │
       │       │       └──→ Get scores for each dimension:
       │       │            accuracy (0.0-1.0)
       │       │            relevance (0.0-1.0)
       │       │            specificity (0.0-1.0)
       │       │
       │       └──→ No: Heuristic fallback
       │               │
       │               └──→ accuracy = existing confidence
       │                    relevance = category-based (0.7 for bug_fix/architecture)
       │                    specificity = text_length / 20 (capped at 1.0)
       │
       ▼
  Compute average score
       │
       ├──→ avg ≥ 0.6  → verdict: "verified"
       ├──→ avg < 0.3  → verdict: "invalidated"
       └──→ otherwise  → verdict: "unverified"
       │
       ▼
  Update fact metadata: verification_status, verified_at
  Persist scores in scores table
```

### Merge Gate

The merge gate ensures knowledge quality when merging to parent branches:

```python
async def check_merge_gate(source_branch, require_verified=True):
    """
    Returns: can_merge (bool), verified/unverified/invalidated counts

    Rules:
    - If require_verified=True: all facts must be verified
    - If any fact is invalidated: can_merge = False
    """
```

This is invoked before merging to main, ensuring only quality-checked knowledge enters long-term memory.

### Entry Points

| Surface | Method |
|---|---|
| **API** | `POST /facts/{id}/verify` → single fact verification |
| **API** | `POST /verification/batch` → batch verify branch |
| **API** | `POST /verification/merge-gate` → check merge readiness |
| **API** | `GET /facts/{id}/verification` → get verification status |
| **API** | `GET /verification/summary/{branch}` → branch summary |

---

## HandoffEngine

**Source**: `src/day1/core/handoff_engine.py`

### Purpose
Structured protocol for passing task context between agents or sessions. Ensures the receiving agent gets verified facts, relevant conversations, and a context summary.

### Handoff Types

| Type | Use Case |
|---|---|
| `task_continuation` | Same task, new agent picks up where old left off |
| `agent_switch` | Different agent takes over (e.g., implementer → reviewer) |
| `session_handoff` | Same agent, new session (context window exhausted) |
| `escalation` | Problem too complex, escalated to more capable agent |

### Handoff Packet

```json
{
  "handoff_id": "uuid",
  "source_branch": "task/fix-auth/agent_1",
  "target_branch": "task/fix-auth/agent_2",
  "handoff_type": "agent_switch",
  "verification_status": "verified",
  "context_summary": "Agent_1 identified the root cause...",
  "facts": [
    { "fact_text": "...", "category": "bug_fix", "confidence": 0.9 }
  ],
  "conversations": [
    { "title": "Debug session", "messages": [...] }
  ]
}
```

By default, only **verified facts** are included in handoffs. Unverified facts are excluded unless explicitly opted in via `include_unverified=True`.

### Entry Points

| Surface | Method |
|---|---|
| **API** | `POST /handoffs` → create handoff |
| **API** | `GET /handoffs/{id}` → retrieve packet |
| **API** | `GET /handoffs` → list handoffs |

---

## TemplateEngine

**Source**: `src/day1/core/template_engine.py`

### Purpose
Create, version, and instantiate reusable knowledge templates. Templates are **procedural memory** — learned patterns that new agents can start from.

### Template Lifecycle

```
┌──────────────────────────────────────────────────────┐
│                TEMPLATE LIFECYCLE                      │
│                                                        │
│  Branch with good knowledge                           │
│       │                                                │
│       ▼                                                │
│  create_template("bug-fix-template")                  │
│       │                                                │
│       └──→ Records: name, source_branch, task_type,   │
│            description, version=1                      │
│                                                        │
│  New task needs bug-fix expertise                      │
│       │                                                │
│       ▼                                                │
│  find_template(task_type="bug_fix")                   │
│       │                                                │
│       ▼                                                │
│  instantiate_template("bug-fix-template")             │
│       │                                                │
│       └──→ DATA BRANCH CREATE TABLE from template     │
│            branch → new working branch                 │
│                                                        │
│  Template knowledge evolves                            │
│       │                                                │
│       ▼                                                │
│  update_template("bug-fix-template", new_source)      │
│       │                                                │
│       └──→ version++ , new source branch               │
│                                                        │
│  Template no longer relevant                           │
│       │                                                │
│       ▼                                                │
│  deprecate_template("bug-fix-template")                │
└──────────────────────────────────────────────────────┘
```

### Task Type Matching

Templates declare which task types they are applicable for. When a new task is created, the system can automatically suggest the best template:

```python
find_template(task_type="bug_fix")
# Returns the best matching template based on task_type and recency
```

### Entry Points

| Surface | Method |
|---|---|
| **API** | `POST /templates` → create |
| **API** | `GET /templates` → list |
| **API** | `GET /templates/find` → find best match |
| **API** | `POST /templates/{name}/instantiate` → fork to working branch |
| **API** | `POST /templates/{name}/update` → new version |
| **API** | `POST /templates/{name}/deprecate` → mark deprecated |

---

## KnowledgeBundleEngine

**Source**: `src/day1/core/knowledge_bundle_engine.py`

### Purpose
Portable, serialized knowledge packages that can be exported and imported across projects and Day1 instances. Unlike templates (live branch forks), bundles are JSON packages.

### Bundle Contents

A bundle packages:
- **Facts** (with text, category, confidence, metadata)
- **Conversations** (with full message history)
- **Relations** (entity graph edges)

All serialized as JSON in the `bundle_data` column.

### Export vs Import

```
EXPORT: Branch → Serialize → Bundle (stored in knowledge_bundles table)
IMPORT: Bundle → Deserialize → Create new facts/conversations/relations on target branch
```

By default, only **verified facts** are included in bundles (configurable via `only_verified=True`).

### Entry Points

| Surface | Method |
|---|---|
| **API** | `POST /bundles` → create bundle from branch |
| **API** | `GET /bundles/{id}/export` → export full data |
| **API** | `POST /bundles/{id}/import` → import to target branch |
| **API** | `GET /bundles` → list bundles |

---

## Discussion

1. **Verification calibration**: Different LLMs have different scoring tendencies. How to calibrate across models?
2. **Template evolution**: When to update a template? Automatically after N successful task completions?
3. **Bundle versioning**: Bundles are immutable once created. Should we support bundle updates?
4. **Cross-project bundles**: Importing bundles from external sources — trust and provenance concerns?
5. **Handoff completeness**: How to ensure the handoff packet contains enough context? Minimum fact count?
6. **Verification cost**: LLM calls for verification are expensive. Should we batch? Rate-limit?
