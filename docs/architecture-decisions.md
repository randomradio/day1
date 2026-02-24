# Architecture Decisions & Discussion Log

This document captures key architecture discussions, decisions, and evolution plans for Day1.
Entries are timestamped and ordered chronologically.

---

## 2026-02-24: Agent Management Scenarios — Architecture Review

### Context

With the core memory layer stable (21 engines, 29 MCP tools, 55+ API endpoints), the focus shifts to **agent management at scale** — what happens when an organization runs 50-100+ agents producing thousands of branches, facts, and conversations?

### Scenarios Evaluated

Seven agent management scenarios were evaluated:

| # | Scenario | Value | Complexity | Decision |
|---|----------|-------|------------|----------|
| 1 | Agent Knowledge Graph Evolution | High | Medium | Deferred (Phase 2) |
| 2 | Cross-Agent Learning / Knowledge Transfer | High | Medium | Deferred (Phase 2) |
| 3 | **Branch Topology Management** | High | Low | **Selected for Phase 1** |
| 4 | **Template Branches** | High | Low-Medium | **Selected for Phase 1** |
| 5 | Memory-Driven Agent Routing | Medium | Medium | Deferred (Phase 3) |
| 6 | Batch Replay + Eval Pipeline | High | High (uncertain) | **Deferred — see below** |
| 7 | Automated Knowledge Curation | High (long-term) | High | Deferred (Phase 3) |

### Decision: Phase 1 Scope

**Implement Branch Topology Management + Template Branches first.**

Rationale:
- Both are pure data-layer operations, no LLM dependency
- Branch Topology is infrastructure that all other scenarios need
- Template Branches close the curation → reuse loop
- Both have clear, well-defined APIs and test strategies

### Decision: Defer Batch Replay + Eval Pipeline

**Deferred due to high uncertainty in LLM execution layer design.**

The core question: who owns the LLM execution in a batch replay pipeline?

Three approaches were evaluated:

| Approach | Description | Pros | Cons |
|----------|-------------|------|------|
| A: Pure data layer | Engine only forks conversations, caller handles LLM | Consistent with ReplayEngine | Batch value diminished |
| B: End-to-end execution | Engine takes configurable LLM client, handles fork + execute + score | True pipeline | Engine calls LLM |
| C: Hybrid | Optional LLM client — full auto with client, prep-only without | Flexible | API surface complexity |

**Preliminary direction: Approach B** (engine with configurable LLM client), following the precedent set by `ScoringEngine._call_llm_judge()`. However, the execution model depends on how upstream systems (MCP clients, CI pipelines, orchestrators) integrate with Day1.

Current single-replay infrastructure (`ReplayEngine` + `ScoringEngine` + `SemanticDiffEngine`) is complete and sufficient. Batch is an orchestration wrapper that can be added once integration patterns are clear.

### Key Insight: The Knowledge Evolution Chain

```
Repeated Task Execution
    → Raw observations accumulate across agent branches
    → Consolidation extracts candidate facts (ConsolidationEngine)
    → Curation distills and deduplicates across branches (future CurationEngine)
    → High-value patterns crystallize into Templates (TemplateEngine)
    → New agents fork from Templates, starting with accumulated knowledge
    → Agents execute tasks, producing new observations
    → Cycle continues
```

**Automated Knowledge Curation is not an independent feature** — it's the bridge between raw accumulated experience and reusable Templates. Its value emerges only when enough agents have performed enough similar tasks to provide meaningful signal for distillation.

This means: Template Branches (the consumer of curation output) should be built first, so the curation → template path has a destination when curation is implemented.

---

## 2026-02-24: System Architecture Review — Current State

### Product Value Proposition

Day1 is a **pure memory layer** for AI agents. Three levels of value:

1. **Single Agent**: Persistent memory across sessions (zero config via Hooks)
2. **Multi-Agent**: Isolated branches + intelligent merge (curated knowledge sharing)
3. **Knowledge Teams**: Template-based knowledge reuse + time-travel + semantic analysis

Key differentiator vs alternatives (e.g., claude-mem):

| Feature | claude-mem | Day1 |
|---------|-----------|------|
| Auto-capture | Yes | Yes |
| Branching | No | Yes (MatrixOne DATA BRANCH) |
| PITR / Time-travel | No | Yes |
| Multi-agent isolation | No | Yes |
| Knowledge graph | SQLite | MatrixOne relations |
| Vector + BM25 hybrid | Chroma | MatrixOne native |
| Curation / verification | No | Yes (Phase 5) |
| Task handoff | No | Yes |

### Pure Memory Layer Principle

"Pure memory layer" means:
- **No agent orchestration** — Day1 doesn't decide what agents do, only what they remember
- **No LLM in core path** — Only ScoringEngine calls LLM (1 of 21 engines), and it gracefully degrades
- **Standard interfaces** — MCP + REST + Hooks, agnostic to what's above
- **Works with anything** — Claude Code, Cursor, Copilot, custom multi-agent frameworks

### Engine Architecture Summary

| Layer | Count | LLM Dependency |
|-------|-------|----------------|
| Write Engines | 4 (Fact, Message, Observation, Relation) | None (embedding only) |
| Query Engines | 3 (Search, Analytics, SessionManager) | None |
| Branch Engines | 3 (BranchManager, MergeEngine, SnapshotManager) | None |
| Conversation Engines | 3 (Conversation, CherryPick, Replay) | None |
| Task Engines | 2 (Task, Consolidation) | None |
| Analysis Engines | 2 (SemanticDiff, Scoring) | Scoring only |
| Infrastructure | 2 (Embedding, LLM) | By design |

**Embedding** is separate from LLM — it's a utility used by 6 engines for vector operations but doesn't require an LLM client. Embedding failures are non-blocking (Phase 0 resilience).

### Identified Architecture Gaps

1. **Embedding resilience**: Phase 0 in `docs/plan.md` designed the fix but it's not reflected in `docs/architecture.md`
2. **Phase 5 status**: Designed in `branched-memory-v2-pure-memory-layer.md` but not yet implemented
3. **No documented roadmap** beyond Phase 5 features
4. **Cost model**: No analysis of MatrixOne storage, OpenAI embedding, or Claude API costs
5. **Branch scaling**: No policies for lifecycle management when branches exceed 100+
6. **Template system**: No way to package and reuse curated knowledge

Gaps 5 and 6 are addressed by the Phase 1 implementation plan (Branch Topology + Templates).

---

## 2026-02-24: Implementation Plan — Branch Topology + Template Branches

### Branch Topology Management

**Problem**: Branches accumulate indefinitely. At 100+ branches, the flat list is unmanageable. No lifecycle policies, no metadata enrichment, no hierarchical visualization.

**Solution**: `BranchTopologyEngine` — extends existing `BranchManager` with:
- Hierarchical topology tree (built from `parent_branch` in `BranchRegistry`)
- Auto-archive policies (inactive N days, after merge, TTL expiry)
- Branch metadata enrichment (purpose, owner, TTL, tags)
- Naming convention validation (task/, template/, team/ hierarchies)
- Per-branch stats (fact/conversation/observation counts, last activity)

**Key design**: Policy enforcement is **explicit, not background**. `apply_auto_archive()` is called by API/MCP/cron — Day1 doesn't run its own scheduler (pure memory layer principle).

**Files**: Engine + API routes + 2 MCP tools + Dashboard enhancement + Tests

### Template Branches

**Problem**: Curated knowledge can't be packaged for reuse. Each new agent/task starts from scratch or inherits only the raw main branch.

**Solution**: `TemplateEngine` — registry and lifecycle for reusable branch templates:
- Create template from any branch (snapshots content via DATA BRANCH fork)
- Version management (v1, v2, ... — old versions deprecated, not deleted)
- Instantiate: fork template → working branch (zero-copy via DATA BRANCH)
- Find applicable template by task type or semantic description match
- Evolution path: curation output → template creation → template update

**Key design**: `TemplateBranch` is a **metadata/registry table**, not a branch-participating table. Uses native `JSON`, not `JsonText`. Template content lives in actual branches managed by `BranchManager`.

**Integration with TaskEngine**: `create_task_from_template()` — create a task that forks from a template instead of main, inheriting pre-loaded facts and conversations.

**Files**: New model + Engine + API routes + 3 MCP tools + Dashboard (list + create wizard) + Tests

### Full implementation details: see plan file in `.claude/plans/`

---

## Decision Log Format

Future entries should follow this format:

```markdown
## YYYY-MM-DD: [Topic]

### Context
[What prompted this discussion]

### Options Considered
[Alternatives evaluated]

### Decision
[What was decided and why]

### Consequences
[What this means for the architecture]
```
