# Open Questions & Future Directions

> Unconsidered areas, design tensions, and future possibilities — organized for structured discussion and iterative design evolution.

This document captures the questions we have not yet answered, the tensions we have not yet resolved, and the directions we have not yet explored. Each section is designed for focused discussion — pick a topic, debate it, and evolve the design.

---

## 1. Individual vs Collective Memory Scale

The fundamental architectural tension: Day1 is currently optimized for **individual agent memory** (precise, layered, instant recall). How do we evolve toward **collective memory** (corpus-scale, retrieval-based, acceptable latency) without compromising individual performance?

### 1.1 Memory Budget & Capacity Planning

**Question**: Should we enforce fact count limits per branch?

An individual agent's useful memory is bounded — even the most prolific producer creates finite output. But without limits, a runaway consolidation loop or misconfigured hook could flood a branch with thousands of low-value facts.

| Approach | Pros | Cons |
|---|---|---|
| No limit (current) | Simple, no configuration | Unbounded growth risk |
| Soft limit with warnings | Non-disruptive, observable | Easy to ignore |
| Hard limit with oldest-eviction | Bounded, automatic | May lose important old facts |
| Tiered limits (session < agent < task < main) | Matches memory hierarchy | Complex configuration |

**Related**: How do we measure "memory pressure" on a branch? Fact count? Total embedding storage? Query latency degradation?

### 1.2 Automatic Memory Compression

**Question**: When individual memory exceeds a threshold, should we automatically compress oldest facts?

Human memory naturally compresses over time — specific details fade while patterns persist. Can we implement something similar?

```
Possible compression strategies:

1. Summarization
   10 related facts → 1 summary fact (LLM-generated)
   Preserves semantic content, loses specificity

2. Decay + Eviction
   Facts below confidence threshold after N days → archived
   Simple, but may lose still-relevant knowledge

3. Hierarchical Abstraction
   Specific facts → general patterns → principles
   "auth bug in login.py line 42" → "auth bugs in login flow" → "auth is fragile"

4. Clustering + Representative Selection
   Embed all facts → cluster → keep cluster centroids
   Mathematically principled, but centroid may not be a real fact
```

### 1.3 Collective Memory Indexing

**Question**: What specialized search strategies are needed for a 100K+ fact corpus across hundreds of branches?

Current hybrid search (BM25 × 0.3 + Vector × 0.7 + temporal decay) works well for hundreds of facts. At corpus scale, we need:

- **Faceted search**: Filter by category, confidence range, source branch, time window before vector search
- **Semantic clustering**: Pre-compute fact clusters for browsable topic navigation
- **Cross-branch search**: Currently search is branch-scoped. Should we enable cross-branch search with branch-weight scoring?
- **Index partitioning**: Separate indexes per branch? Per time window? Per confidence tier?

### 1.4 Knowledge Distillation at Scale

**Question**: How do agent swarms merge knowledge without combinatorial explosion?

With N agents each producing M facts, naive merging creates N × M facts on main. We need:

- **Incremental deduplication**: As each agent merges, dedup against existing main facts
- **Conflict detection**: When two agents produce contradictory facts, which wins?
- **Provenance tracking**: After mass merge, which agent contributed which knowledge?
- **Distillation checkpoints**: Periodically summarize main branch facts into a condensed form

### 1.5 Attention Mechanism

**Question**: How to prioritize which memories surface for a given context?

Currently, search returns the top-K most similar facts. But relevance depends on more than similarity:

```
Factors that should influence memory surfacing:

1. Semantic similarity (current: vector cosine)
2. Temporal recency (current: decay factor)
3. Confidence level (not yet used in ranking)
4. Access frequency (not tracked)
5. Task relevance (not implemented)
6. Agent role / specialization (not implemented)
7. Emotional salience analog (critical bugs > minor style notes)
```

**Design question**: Should we build a learned ranking model, or keep it as a tunable weighted sum?

---

## 2. Architecture & Operations

### 2.1 Multi-Tenancy Isolation

**Question**: What isolation level is right for multi-tenant deployments?

| Level | Mechanism | Isolation | Cost | Complexity |
|---|---|---|---|---|
| Database-level | Separate MatrixOne databases | Strongest | Highest | Connection pooling per tenant |
| Schema-level | Table name prefixes per tenant | Strong | Moderate | Prefix management, migrations per tenant |
| Row-level | `tenant_id` on every table | Weakest | Lowest | Every query needs tenant filter |
| Branch-level (current) | DATA BRANCH per agent | Agent-level | Low | No tenant concept |

**Recommendation**: Row-level for SaaS MVP, database-level for enterprise. But this requires:
- Tenant context propagation through all 26 engines
- Tenant-scoped rate limiting (currently per-IP)
- Tenant-scoped API keys (currently single shared key)
- Tenant data export/deletion for compliance

### 2.2 Branch Permissions & RBAC

**Question**: Who can merge to main? Who can create branches? Who can delete?

Currently, all operations are open (anyone with the API key can do anything). For multi-agent and multi-team scenarios, we need:

```
Potential role hierarchy:

Admin
├── Create/delete any branch
├── Merge anything to main
├── Manage templates
├── Access analytics for all branches
└── Manage API keys and roles

Agent (per-branch)
├── Read/write on assigned branches
├── Create child branches
├── Cannot merge to main (requires verification)
├── Cannot delete other agents' branches
└── Cannot access other agents' branch data

Viewer (per-branch or global)
├── Read-only access
├── Search across permitted branches
├── View analytics
└── Cannot write or modify

Verifier (special role)
├── Run verification on any branch
├── Approve/reject merge gates
└── Cannot directly write facts
```

**Question**: How to assign roles? Per API key? Per MCP session? Per branch?

### 2.3 Knowledge Aging & TTL

**Question**: Should facts have a time-to-live? Should old knowledge automatically decay?

Some knowledge is permanently relevant (architectural decisions, security policies). Other knowledge has a shelf life (current API endpoints, dependency versions, team member roles).

```
Possible aging strategies:

1. Category-based TTL
   bug_fix: 90 days (bugs get fixed and forgotten)
   architecture: permanent (decisions are durable)
   performance: 180 days (metrics change)
   pattern: permanent (patterns are reusable)

2. Access-based freshness
   Fact accessed within 30 days → fresh
   Fact not accessed for 90 days → stale (reduce confidence)
   Fact not accessed for 365 days → archive candidate

3. Verification refresh
   Verified facts require re-verification after N days
   Failed re-verification → confidence decay → eventual archive

4. Explicit expiry
   Facts can optionally have an expires_at timestamp
   Auto-archive on expiry
```

### 2.4 Cross-Project Sharing

**Question**: How do knowledge bundles work across separate Day1 instances?

Currently, bundles are created and imported within a single Day1 instance. For cross-project knowledge sharing:

- **Bundle format**: JSON serialization is simple but loses embeddings. Re-embed on import?
- **Bundle registry**: Central registry for discovering available bundles across projects?
- **Version compatibility**: What happens when the importing project has a different schema version?
- **Trust model**: Should imported bundles be verified on import? Start at lower confidence?

### 2.5 Offline Mode

**Question**: Can Day1 work with SQLite when MatrixOne is unavailable?

For local development, disconnected agents, or edge deployments:

- **What we lose**: DATA BRANCH, FULLTEXT INDEX, vecf32, AS OF TIMESTAMP, PITR
- **What we keep**: Basic CRUD, conversation history, fact storage
- **Sync model**: When MatrixOne becomes available, sync local SQLite → MatrixOne
- **Conflict resolution**: Local writes during offline period vs remote writes — who wins?

This is a significant architectural decision that affects the storage layer abstraction.

---

## 3. Integration & Ecosystem

### 3.1 Agent SDK Deep Integration

**Question**: Should memory primitives be native to agent code, not just MCP tools?

Currently, agents interact with Day1 via MCP tools (8 NL-first tools) or REST API (85+ endpoints). For deeper integration:

```python
# Current: MCP tool call (external)
await mcp_call("memory_write", text="Auth needs both headers", context="debugging")

# Proposed: Native SDK integration
from day1.sdk import Memory

memory = Memory(branch="task/fix-auth")
memory.learn("Auth needs both headers", context="debugging")  # → fact
results = memory.recall("authentication")                       # → search
memory.checkpoint("before risky change")                        # → snapshot

# Even deeper: decorator-based
@memory.track_function
async def fix_auth():
    # All tool calls automatically observed
    # Function outcome automatically captured
    pass
```

**Question**: How much Day1 awareness should be baked into the agent SDK vs kept external?

### 3.2 Batch Replay & Evaluation Pipeline

**Question**: How to systematically re-execute and score conversations for quality assurance?

The ReplayEngine supports individual conversation replay. For batch evaluation:

- **Corpus selection**: Which conversations to replay? All? Filtered by score? By task type?
- **Parameterized replay**: Same conversation with different models, temperatures, system prompts
- **Scoring aggregation**: Per-task, per-agent, per-model scoring dashboards
- **Regression detection**: Alert when a conversation that previously scored high now scores low
- **A/B testing**: Compare two agent configurations on the same conversation corpus

### 3.3 Embedding Provider Migration

**Question**: How to switch embedding providers without re-embedding everything?

Current state: All facts are embedded using the configured provider (OpenAI `text-embedding-3-small` by default). Switching providers means:

- Old embeddings are incompatible with new provider's vector space
- Re-embedding all facts is expensive (API calls) and slow
- During migration, search quality degrades (mixed embedding spaces)

Possible approaches:

| Approach | Pros | Cons |
|---|---|---|
| Big-bang re-embed | Clean, consistent | Expensive, downtime |
| Dual-embed during transition | No downtime | 2x storage, complex queries |
| Adapter/projection layer | Keep old embeddings | Lossy transformation |
| Lazy re-embed on access | Gradual, no batch cost | Inconsistent results during migration |

### 3.4 Real-Time Sync

**Question**: Should agents get live updates when shared knowledge changes?

Currently, agents poll for context at session start (SessionStart hook) and search on demand. For multi-agent collaboration:

- **WebSocket/SSE**: Push notifications when facts are written, merged, or verified on a branch
- **Subscription model**: Agent subscribes to branches or topics of interest
- **Conflict notification**: Alert when another agent writes a contradictory fact
- **Merge notification**: Alert when main branch gets new verified knowledge

**Design tension**: Real-time sync adds complexity and infrastructure cost. Is it worth it for the typical use case (agents working on separate branches)?

---

## 4. Quality & Governance

### 4.1 Verification Quality Calibration

**Question**: How consistent are LLM-as-judge scores across different models and prompts?

VerificationEngine uses Claude to evaluate fact accuracy, relevance, and specificity. Concerns:

- **Model sensitivity**: Different Claude models may score the same fact differently
- **Prompt sensitivity**: Small prompt changes may shift score distributions
- **Calibration**: Is a score of 0.7 from one model comparable to 0.7 from another?
- **Adversarial facts**: Can a fact be crafted to always pass verification despite being wrong?

**Needed**: A calibration dataset of facts with known-correct verification scores, tested across multiple models and prompt variations.

### 4.2 GDPR & Compliance

**Question**: How to implement right-to-forget in a memory system designed to remember?

The fundamental tension: Day1's purpose is durable knowledge retention. GDPR's purpose is enabling data deletion. Specific challenges:

```
Deletion cascade complexity:

User requests deletion of session S
├── Delete messages in session S conversations ✓ (direct)
├── Delete observations from session S ✓ (direct)
├── Delete facts created in session S ... ⚠
│   ├── Fact was merged to main → now on a different branch
│   ├── Fact was deduplicated → merged with another fact
│   ├── Fact was used in template → template references it
│   └── Fact was exported in bundle → bundle contains serialized copy
├── Delete relations involving those facts ⚠
│   └── Other facts may reference these relations
└── Delete consolidated history ✓ (audit trail concern)
```

**Questions**:
- Should merged facts retain session attribution (enabling deletion) or lose it (enabling privacy)?
- Should bundles be invalidated if any constituent fact is deleted?
- Should templates be versioned with deletion events?
- How to handle the right to explanation when verified facts are deleted?

### 4.3 Observability

**Question**: How to monitor Day1's health and performance in production?

Currently, Day1 uses Python logging. For production observability:

- **Metrics** (Prometheus/OpenTelemetry):
  - Write latency (per engine, per operation)
  - Search latency (BM25, vector, hybrid)
  - Consolidation throughput (observations processed/minute)
  - Branch operation latency (create, merge, diff)
  - Embedding API latency and error rate
  - Fact count per branch (growth rate)
  - Memory pressure indicators

- **Traces** (distributed tracing):
  - Full request path: client → middleware → engine → DB → response
  - Cross-engine traces (consolidation touches multiple engines)
  - Hook execution timing

- **Alerts**:
  - Consolidation backlog growing (observations not being processed)
  - Verification failure rate spike
  - Branch count explosion (orphaned branches not being archived)
  - Search latency exceeding threshold

### 4.4 Conflict Resolution UI

**Question**: How should the dashboard visualize and resolve merge conflicts?

When merging branches with conflicting facts, the current MergeEngine uses automatic strategies (skip or accept). But some conflicts need human judgment:

```
Conflict visualization concept:

┌─────────────────────────────────────────────────────────┐
│  MERGE: task/fix-auth → main                             │
│                                                           │
│  ⚠ 3 conflicts detected                                 │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐│
│  │ Conflict 1: Contradictory facts                      ││
│  │                                                       ││
│  │  SOURCE (task/fix-auth):                             ││
│  │  "Auth middleware checks Bearer token first"          ││
│  │  confidence: 0.85, verified: ✓                       ││
│  │                                                       ││
│  │  TARGET (main):                                       ││
│  │  "Auth middleware checks API key first"               ││
│  │  confidence: 0.90, verified: ✓                       ││
│  │                                                       ││
│  │  [Accept Source] [Accept Target] [Keep Both] [Skip]  ││
│  └─────────────────────────────────────────────────────┘│
│                                                           │
│  ┌─────────────────────────────────────────────────────┐│
│  │ Conflict 2: Duplicate with different confidence      ││
│  │  ... (auto-resolvable: keep higher confidence)       ││
│  │  [Auto-resolved ✓]                                   ││
│  └─────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
```

---

## 5. Future Directions

### 5.1 Plugin System

**Question**: Should Day1 support custom engines, scorers, and embedding providers as plugins?

A plugin architecture would enable:
- Custom scoring dimensions (domain-specific quality metrics)
- Custom embedding providers (private models, specialized embeddings)
- Custom consolidation strategies (domain-specific fact extraction)
- Custom verification rules (compliance-specific checks)
- Custom hook processors (additional capture logic)

**Design question**: Plugin as Python packages installed via pip? Or plugin as MCP tools that Day1 calls?

### 5.2 Cross-Agent Learning Signals

**Question**: How can one agent's experience help another agent work better?

Currently, agents share knowledge only through explicit mechanisms (merge to main, templates, bundles). Implicit learning signals could include:

- **Tool call patterns**: Agent A found a more efficient tool sequence for task type X → suggest to Agent B
- **Failure avoidance**: Agent A encountered a dead-end approach → warn Agent B before they try
- **Confidence calibration**: Facts that are frequently re-discovered by multiple agents → boost confidence
- **Specialization signals**: Agent A is consistently better at security tasks → route security tasks to A

### 5.3 Memory Marketplace

**Question**: Could organizations share verified templates and bundles?

An internal or external marketplace for knowledge packages:

- **Template marketplace**: Pre-built templates for common task types (debugging, code review, migration)
- **Bundle marketplace**: Curated knowledge packages for specific domains (security best practices, API design patterns)
- **Quality signals**: Download count, success rate when used, user ratings
- **Versioning**: Templates and bundles evolve — how to notify users of updates?
- **Trust model**: Who verifies marketplace content? Community ratings? Centralized curation?

### 5.4 Hierarchical Collective Memory

**Question**: Should collective memory have layers matching organizational hierarchy?

```
Possible hierarchy:

┌────────────────────────────────────────────────┐
│  Organization Memory (company-wide)             │
│  ├── Security policies, compliance rules        │
│  ├── Architectural principles                   │
│  └── Cross-team patterns                        │
│                                                  │
│  ┌────────────────────────────────────────────┐ │
│  │  Department Memory (team-level)             │ │
│  │  ├── Team conventions, code style           │ │
│  │  ├── Service-specific knowledge             │ │
│  │  └── Team-specific templates                │ │
│  │                                              │ │
│  │  ┌────────────────────────────────────────┐ │ │
│  │  │  Project Memory (repo-level)           │ │ │
│  │  │  ├── Architecture decisions             │ │ │
│  │  │  ├── Bug patterns, known issues         │ │ │
│  │  │  └── Project-specific facts             │ │ │
│  │  │                                          │ │ │
│  │  │  ┌────────────────────────────────────┐ │ │ │
│  │  │  │  Agent Memory (individual)         │ │ │ │
│  │  │  │  ├── Session context                │ │ │ │
│  │  │  │  ├── Task-specific knowledge        │ │ │ │
│  │  │  │  └── Working memory (ephemeral)     │ │ │ │
│  │  │  └────────────────────────────────────┘ │ │ │
│  │  └────────────────────────────────────────┘ │ │
│  └────────────────────────────────────────────┘ │
└────────────────────────────────────────────────┘
```

**Questions**:
- How does knowledge propagate upward (agent → project → department → org)?
- How does knowledge propagate downward (org policies → agent context)?
- Who governs the merge gates at each level?
- How does search work across levels? (Agent searches local first, then project, then department, then org?)

### 5.5 Adaptive Consolidation

**Question**: Should consolidation parameters adapt based on task type and agent performance?

Currently, consolidation uses fixed parameters (Jaccard > 0.85 for dedup, confidence 0.7 for new facts, durable threshold 0.8). These could be adaptive:

- **Task type awareness**: Security tasks may need lower thresholds (capture more potential issues)
- **Agent track record**: High-performing agents get higher initial confidence for their facts
- **Domain density**: In a well-explored domain (many existing facts), be more aggressive with dedup
- **Time pressure**: Under tight deadlines, be more lenient with verification gates

### 5.6 Memory-Aware Agent Orchestration

**Question**: Should agent task assignment consider memory state?

Day1 is designed as a pure memory layer, not an orchestrator. But memory state contains valuable signals for orchestration:

- **Agent expertise matching**: Agent A has high-confidence facts about auth → assign auth tasks to A
- **Knowledge gap detection**: No facts about database migrations → flag as risk area
- **Diminishing returns detection**: Agent has been producing low-confidence facts → suggest task switch
- **Load balancing by memory**: Agent with full working memory (many active facts) may be overloaded

**Design tension**: Adding orchestration awareness violates the "pure memory layer" principle. Should this be a separate layer that reads Day1 state?

---

## 6. Technical Debt & Known Limitations

### 6.1 Raw SQL in Analytics

`AnalyticsEngine` uses `text()` for time-series queries with format-string table name construction. While parameters are bound safely, the table name insertion should be audited and potentially refactored to use the ORM.

### 6.2 CORS Configuration

Currently allows all origins (`*`). Needs to be configurable per deployment environment.

### 6.3 Single API Key

Single shared Bearer token for all users. Needs per-user or per-agent key management for production.

### 6.4 In-Memory Rate Limiting

Rate limit counters are in-memory per-process. Won't work correctly behind a load balancer (multiple API processes). Needs Redis or database-backed rate limiting.

### 6.5 Hook Subprocess Overhead

Each hook invocation spawns a new Python process. For high-frequency hooks (PostToolUse on every tool call), this adds latency. Consider:
- Long-running hook daemon with IPC
- Async hook execution within the Claude Code process
- Batch hook processing (buffer observations, flush periodically)

### 6.6 Embedding Dimension Coupling

The data model uses `vecf32` columns with a fixed dimension (1536 for OpenAI). Switching to an embedding provider with different dimensions requires schema migration.

### 6.7 JsonText Workaround

The `JsonText` custom SQLAlchemy type (stores JSON as TEXT) exists to work around a MatrixOne DATA BRANCH DIFF limitation with type 245. This should be revisited as MatrixOne evolves.

---

## Priority Matrix

For discussion: which open questions should be addressed first?

```
                     HIGH IMPACT
                        │
    ┌───────────────────┼───────────────────┐
    │                   │                   │
    │  2.1 Multi-tenancy│  1.5 Attention    │
    │  2.2 RBAC         │  mechanism        │
    │  4.2 GDPR         │  5.2 Cross-agent  │
    │                   │  learning         │
    │                   │                   │
LOW ├───────────────────┼───────────────────┤ HIGH
EFFORT│                  │                   │ EFFORT
    │                   │                   │
    │  2.3 Knowledge    │  1.2 Auto-compress│
    │  aging/TTL        │  5.4 Hierarchical │
    │  4.3 Observability│  memory           │
    │  6.1-6.7 Tech debt│  3.3 Embedding    │
    │                   │  migration        │
    │                   │                   │
    └───────────────────┼───────────────────┘
                        │
                     LOW IMPACT
```

**Recommended priority order**:
1. **Quick wins** (low effort, high impact): RBAC basics, knowledge aging, observability
2. **Critical foundations** (high effort, high impact): Multi-tenancy, GDPR compliance, attention mechanism
3. **Incremental improvements** (low effort, low impact): Tech debt items, TTL
4. **Strategic investments** (high effort, high impact): Cross-agent learning, hierarchical memory, auto-compression
