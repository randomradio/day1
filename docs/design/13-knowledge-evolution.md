# Knowledge Evolution Pipeline

> From raw observation to reusable template — how Day1 transforms agent experience into organizational knowledge.

## The Core Pipeline

This is the most critical design in Day1. It implements the transition from **sensory input** to **durable organizational knowledge**, mirroring how humans form memories through experience, consolidation, and crystallization.

```
┌──────────────────────────────────────────────────────────────┐
│            KNOWLEDGE EVOLUTION PIPELINE                        │
│                                                                │
│  Stage 0: Raw Execution (Sensory Memory)                      │
│  ┌──────────────────────────────────────────────────────┐     │
│  │  Agent uses tools → PostToolUse hook captures         │     │
│  │  Every action recorded as observation                  │     │
│  │  Volume: 100s per session, low signal-to-noise        │     │
│  │  Storage: observations table                           │     │
│  └──────────────────────────┬───────────────────────────┘     │
│                              │                                 │
│                    attention filter                             │
│                    (only insight/decision/discovery)            │
│                              │                                 │
│                              ▼                                 │
│  Stage 1: Session Consolidation (Short-Term Memory)            │
│  ┌──────────────────────────────────────────────────────┐     │
│  │  SessionEnd hook → ConsolidationEngine.consolidate_   │     │
│  │  session()                                             │     │
│  │                                                        │     │
│  │  For each meaningful observation:                      │     │
│  │    Jaccard similarity > 0.85 against existing facts?   │     │
│  │    ├── Yes → boost existing fact confidence (+0.1)     │     │
│  │    └── No  → create new fact (confidence: 0.7)        │     │
│  │                                                        │     │
│  │  Volume: 5-20 facts per session                        │     │
│  │  Storage: facts table (session branch)                 │     │
│  └──────────────────────────┬───────────────────────────┘     │
│                              │                                 │
│                    cross-session deduplication                  │
│                              │                                 │
│                              ▼                                 │
│  Stage 2: Agent Consolidation (Working → Short-Term)           │
│  ┌──────────────────────────────────────────────────────┐     │
│  │  Agent completes → ConsolidationEngine.consolidate_   │     │
│  │  agent()                                               │     │
│  │                                                        │     │
│  │  Deduplicate across all agent sessions (Union-Find)   │     │
│  │  Keep highest-confidence version of duplicates         │     │
│  │  Generate agent summary fact                           │     │
│  │                                                        │     │
│  │  Volume: 10-50 facts per agent assignment              │     │
│  │  Storage: facts table (agent branch)                   │     │
│  └──────────────────────────┬───────────────────────────┘     │
│                              │                                 │
│                    durable vs ephemeral classification          │
│                              │                                 │
│                              ▼                                 │
│  Stage 3: Task Consolidation (Short-Term → Long-Term gate)     │
│  ┌──────────────────────────────────────────────────────┐     │
│  │  Task completes → ConsolidationEngine.consolidate_    │     │
│  │  task()                                                │     │
│  │                                                        │     │
│  │  Classify each fact:                                   │     │
│  │    Durable = confidence ≥ 0.8                          │     │
│  │           AND category ∈ {bug_fix, architecture,       │     │
│  │                pattern, decision, security, performance}│    │
│  │    Ephemeral = everything else                          │     │
│  │                                                        │     │
│  │  Durable facts → candidates for merge to main          │     │
│  │  Ephemeral facts → stay on task branch                 │     │
│  └──────────────────────────┬───────────────────────────┘     │
│                              │                                 │
│                    verification gate                            │
│                              │                                 │
│                              ▼                                 │
│  Stage 4: Verification (Quality Gate)                          │
│  ┌──────────────────────────────────────────────────────┐     │
│  │  VerificationEngine.batch_verify(branch)               │     │
│  │                                                        │     │
│  │  For each durable fact:                                │     │
│  │    LLM-as-judge evaluates:                             │     │
│  │      accuracy (0.0-1.0)                                │     │
│  │      relevance (0.0-1.0)                               │     │
│  │      specificity (0.0-1.0)                             │     │
│  │                                                        │     │
│  │    avg ≥ 0.6 → verified (passes merge gate)           │     │
│  │    avg < 0.3 → invalidated (blocked from merge)       │     │
│  │    otherwise → unverified (needs review)               │     │
│  │                                                        │     │
│  │  Merge Gate: only verified facts can merge to main    │     │
│  └──────────────────────────┬───────────────────────────┘     │
│                              │                                 │
│                    merge to main                               │
│                              │                                 │
│                              ▼                                 │
│  Stage 5: Long-Term Storage (Durable Knowledge)                │
│  ┌──────────────────────────────────────────────────────┐     │
│  │  MergeEngine.merge(task_branch → main)                 │     │
│  │                                                        │     │
│  │  Verified facts now on main branch                     │     │
│  │  Accessible to all future sessions                     │     │
│  │  High confidence (≥ 0.8), verified status              │     │
│  │  Connected via relations (knowledge graph)             │     │
│  │                                                        │     │
│  │  Volume: 5-15 durable facts per completed task         │     │
│  └──────────────────────────┬───────────────────────────┘     │
│                              │                                 │
│                    crystallization                              │
│                              │                                 │
│                              ▼                                 │
│  Stage 6: Template/Bundle (Procedural Memory)                  │
│  ┌──────────────────────────────────────────────────────┐     │
│  │  TemplateEngine.create_template() — from successful   │     │
│  │  task branches, create reusable templates              │     │
│  │                                                        │     │
│  │  KnowledgeBundleEngine.create_bundle() — package      │     │
│  │  verified knowledge for cross-project sharing          │     │
│  │                                                        │     │
│  │  New agents: instantiate_template() → start with       │     │
│  │  accumulated knowledge from past successes             │     │
│  └──────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────┘
```

---

## Confidence Evolution

Confidence is the numeric signal that drives memory promotion:

```
                    Confidence Trajectory
    1.0 ┤
        │                                    ●──── Verified, on main
    0.9 ┤                              ●────┘
        │                         ●───┘  (verification boost)
    0.8 ┤                    ●──┘
        │               ●──┘  (consolidation dedup boost: +0.1)
    0.7 ┤          ●──┘
        │     ●──┘  (initial from consolidation)
    0.6 ┤●──┘
        │  (initial from explicit write)
    0.5 ┤
        │
    0.0 ┼──────────────────────────────────────────→ Time
        Session  Agent   Task    Verify  Merge
        Consol.  Consol. Consol. Gate    to Main
```

| Stage | Confidence Range | Mechanism |
|---|---|---|
| Explicit write (`memory_write`) | 0.5–0.9 (user-specified) | Manual |
| Session consolidation (obs → fact) | 0.7 (fixed) | Automatic |
| Dedup confidence boost | +0.1 per duplicate (max 1.0) | Jaccard > 0.85 |
| Durable threshold | ≥ 0.8 required | Category + confidence |
| Verification | Preserved or adjusted | LLM-as-judge |

---

## The Compression Function

The pipeline acts as a **natural compression function** — critical for keeping individual agent memory small and precise:

```
Stage          Volume         Ratio
────────────   ─────────      ─────
Observations   200/session     –
     ↓
Session facts  10-20/session   ~10:1 compression
     ↓
Agent facts    10-50/agent     ~2:1 dedup
     ↓
Task durable   5-15/task       ~3:1 classification
     ↓
Verified       3-10/task       ~2:1 quality gate
     ↓
On main        3-10/task       1:1 (verified = merged)

Overall: ~200 observations → ~5 durable facts on main
         = ~40:1 compression ratio
```

This ensures that even after thousands of sessions, the main branch contains only high-quality, verified, deduplicated knowledge — not an ever-growing log.

---

## Human Memory Analogy at Each Stage

| Pipeline Stage | Human Memory Analogy | Key Mechanism |
|---|---|---|
| Observations | Sensory memory | Automatic capture, unfiltered |
| Session consolidation | Working → short-term | Attention filter, rehearsal |
| Agent consolidation | Short-term consolidation | Sleep/rest consolidation, dedup |
| Task consolidation | Short-term → long-term gate | Significance assessment |
| Verification | Long-term encoding | Quality check, confidence threshold |
| Templates/Bundles | Procedural memory | Pattern crystallization |

Just as human memory:
- **Forgetting is a feature**: Ephemeral facts are deliberately not promoted
- **Repetition strengthens**: Duplicate observations boost fact confidence
- **Sleep consolidates**: Session-end consolidation processes accumulated experience
- **Important things stick**: Durable categories (decisions, patterns) are preferentially retained
- **Expertise develops**: Templates represent crystallized expertise from repeated task success

---

## Triggers and Automation

| Stage | Trigger | Automatic? |
|---|---|---|
| Observation capture | Every tool call | Yes (PostToolUse hook) |
| Session consolidation | Session end | Yes (SessionEnd hook) |
| Agent consolidation | Agent completes task | Semi-auto (TaskEngine.complete_agent) |
| Task consolidation | Task completes | Semi-auto (TaskEngine.complete_task) |
| Verification | Explicit API call | Manual (could be automated) |
| Merge to main | Explicit API call | Manual (deliberate action) |
| Template creation | Explicit API call | Manual (requires judgment) |

---

## Discussion

1. **Automated verification**: Should verification run automatically after task consolidation?
2. **Confidence calibration**: Is the +0.1 boost for dedup too aggressive? Too conservative?
3. **Durable category set**: Should categories be project-configurable?
4. **Cross-task learning**: Currently each task consolidates independently. Should we detect patterns across tasks?
5. **Feedback loops**: When a template fails (agents using it don't succeed), should the template be downranked?
6. **Memory pressure**: For collective memory at scale, should we automatically compress/summarize old facts?
7. **Real-time consolidation**: Instead of batch at session-end, could we consolidate incrementally?
