# Query Engines

> SearchEngine, AnalyticsEngine, SessionManager — read-path engines for retrieval and analysis.

## SearchEngine

**Source**: `src/day1/core/search_engine.py`

### Design Rationale

Search is the most critical read-path operation in Day1. When an agent starts a new session, the quality of its work depends on how effectively it can recall relevant prior knowledge. The SearchEngine implements hybrid search combining:

1. **BM25 keyword matching** (via MatrixOne FULLTEXT INDEX) — good for exact terms, function names, error messages
2. **Vector semantic similarity** (via cosine_similarity on vecf32 embeddings) — good for conceptual similarity, paraphrased knowledge
3. **Temporal decay** — recent memories score higher, reflecting the individual memory regime

```
┌────────────────────────────────────────────────────────┐
│                    SEARCH PIPELINE                       │
│                                                          │
│  Query: "how to handle auth in FastAPI"                 │
│       │                                                  │
│       ├──────────────────┬───────────────────┐          │
│       ▼                  ▼                   ▼          │
│  ┌──────────┐    ┌───────────┐    ┌──────────────┐     │
│  │  BM25    │    │  Vector   │    │  Temporal    │     │
│  │  MATCH   │    │  cosine_  │    │  Decay       │     │
│  │  AGAINST │    │  similarity│   │  exp(-age/λ) │     │
│  │  w=0.3   │    │  w=0.7    │    │  multiplier  │     │
│  └────┬─────┘    └─────┬─────┘    └──────┬───────┘     │
│       │                │                  │             │
│       └────────────────┼──────────────────┘             │
│                        ▼                                │
│               ┌────────────────┐                        │
│               │  Score Fusion  │                        │
│               │  rank + dedup  │                        │
│               └───────┬────────┘                        │
│                       ▼                                 │
│              Ranked Results (top K)                      │
└────────────────────────────────────────────────────────┘
```

### Core Operations

| Method | Purpose | Parameters |
|---|---|---|
| `search()` | Hybrid search over facts | query, branch_name, category, limit, search_type (hybrid/keyword/vector) |
| `search_cross_branch()` | Search across multiple branches | query, branch_names, limit |
| `search_observations()` | Search observations | query, session_id, branch_name, limit |

### Fallback Chain

```
1. Try MATCH AGAINST (BM25)
   ├── Success → use BM25 scores
   └── Failure (no FULLTEXT index, syntax error)
        └── Fall back to LIKE with word tokenization

2. Try cosine_similarity (Vector)
   ├── Embedding exists → compute similarity
   └── No embedding → skip vector score

3. Combine scores: final = 0.3 * bm25 + 0.7 * vector + temporal_bonus
```

### Entry Points

| Surface | Trigger | Method |
|---|---|---|
| **MCP** | `memory_search` tool | `MemoryEngine.search()` / `SearchEngine.search()` |
| **API** | `GET /facts/search` | `SearchEngine.search()` |
| **API** | `POST /facts/search` (with time_range) | `SearchEngine.search()` |
| **Hook** | SessionStart (inject context) | `SearchEngine.search()` or `FactEngine.list_facts()` |
| **CLI** | `search <query>` | `SearchEngine.search()` |

---

## AnalyticsEngine

**Source**: `src/day1/core/analytics_engine.py`

### Design Rationale

Analytics answers "how is the memory system being used?" — critical for understanding agent behavior, memory quality, and system health. It provides aggregate metrics without exposing individual memory contents.

### Core Operations

| Method | Purpose | Returns |
|---|---|---|
| `overview()` | Dashboard top-level metrics | Counts, token stats, recent activity, consolidation yield |
| `session_analytics()` | Per-session breakdown | Messages, facts, observations, tool breakdown |
| `agent_analytics()` | Per-agent performance | Sessions, conversations, facts by category, tool usage |
| `trends()` | Time-series metrics | Messages/facts/conversations over time |
| `conversation_analytics()` | Single conversation stats | Role distribution, token usage, fork count |

### Key Metric: Consolidation Yield Rate

```
yield_rate = facts_created / observations_processed
```

This metric measures how effectively the system converts raw observations into durable knowledge. A healthy yield rate is 5-15% — most observations are routine, but a meaningful fraction produces lasting insights.

### Entry Points

| Surface | Method |
|---|---|
| **API** | `GET /analytics/overview` |
| **API** | `GET /analytics/sessions/{session_id}` |
| **API** | `GET /analytics/agents/{agent_id}` |
| **API** | `GET /analytics/trends` |
| **API** | `GET /analytics/conversations/{conversation_id}` |
| **Dashboard** | AnalyticsDashboard component |

---

## SessionManager

**Source**: `src/day1/core/session_manager.py`

### Design Rationale

Sessions are the atomic unit of agent work. Each Claude Code session, each Agent SDK invocation, each Cursor session creates a Day1 session. The SessionManager tracks these sessions and their relationships (parent-child for forks).

### Core Operations

| Method | Purpose | Parameters |
|---|---|---|
| `create_session()` | Register new session | session_id, branch_name, project_path, parent_session, task_id, agent_id |
| `get_session()` | Retrieve session metadata | session_id |
| `get_session_context()` | Full context package for handoff | session_id, message_limit, fact_limit |
| `get_recent_sessions()` | List recent sessions | limit |
| `end_session()` | Mark session complete with summary | session_id, summary |

### Session Context Package

`get_session_context()` assembles a complete context package for agent handoff:

```
{
  "session": { id, branch, status, summary, started_at, ended_at },
  "conversations": [
    { id, title, messages: [...] }
  ],
  "facts": [
    { id, fact_text, category, confidence }
  ],
  "observations_summary": {
    total: N,
    tools_used: ["Bash", "Read", "Edit", ...]
  }
}
```

This is used by:
- `SessionStart` hook (inject parent session context into new session)
- `HandoffEngine` (assemble handoff packets)
- `GET /sessions/{id}/context` API endpoint

### Entry Points

| Surface | Trigger | Method |
|---|---|---|
| **Hook** | SessionStart | `create_session()` |
| **Hook** | SessionEnd | `end_session()` |
| **API** | `GET /sessions` | `get_recent_sessions()` |
| **API** | `GET /sessions/{id}/context` | `get_session_context()` |

---

## Discussion

1. **Search quality**: How to measure and improve search relevance? A/B testing different BM25/vector weight ratios?
2. **Cross-branch search performance**: Searching N branches means N table scans. At what branch count does this become a bottleneck?
3. **Analytics privacy**: In multi-tenant scenarios, analytics should be scoped. How to enforce this?
4. **Session lifecycle**: What happens to orphaned sessions (never ended)? Automatic timeout?
