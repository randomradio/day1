# MatrixOne Foundation

> How Day1 leverages MatrixOne's native capabilities to build a Git-like memory layer in a single database.

## Why MatrixOne

The typical architecture for an AI memory system requires 3-4 separate databases:
- **PostgreSQL** for relational data (facts, sessions, tasks)
- **Pinecone/Chroma/Weaviate** for vector search
- **Elasticsearch** for fulltext keyword search
- **Custom application logic** for branching, versioning, time-travel

MatrixOne eliminates this complexity. It is a single database that natively provides:

```
┌──────────────────────────────────────────────────────────┐
│                   MatrixOne Native Stack                   │
│                                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Relational   │  │   Vector     │  │   Fulltext    │  │
│  │  SQL (MySQL   │  │  vecf32 +    │  │  FULLTEXT     │  │
│  │  compatible)  │  │  cosine_sim  │  │  INDEX +      │  │
│  │              │  │              │  │  MATCH AGAINST │  │
│  └──────────────┘  └──────────────┘  └───────────────┘  │
│                                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Git4Data     │  │  Time Travel │  │  Snapshot     │  │
│  │  DATA BRANCH  │  │  AS OF       │  │  CREATE       │  │
│  │  CREATE/DIFF  │  │  TIMESTAMP   │  │  SNAPSHOT /   │  │
│  │  /MERGE       │  │              │  │  PITR         │  │
│  └──────────────┘  └──────────────┘  └───────────────┘  │
└──────────────────────────────────────────────────────────┘
```

**Result**: Day1's entire persistence layer is a single MatrixOne database with zero external dependencies for storage.

---

## DATA BRANCH — Zero-Copy Table-Level Branching

MatrixOne's `DATA BRANCH` is the foundation of Day1's Git-like branching model. It provides Copy-on-Write (CoW) table-level branching where creating a branch is nearly instant regardless of table size.

### How It Works

```sql
-- Create a branch table from an existing table (zero-copy, CoW)
DATA BRANCH CREATE TABLE `facts_feature_x` FROM `facts`

-- The new table starts as a virtual copy of the original
-- Writes to either table are independent (Copy-on-Write)
```

### Day1's Branch Table Convention

Day1 uses a naming convention to map branches to tables:

```
Branch "main"      → facts, relations, observations, conversations, messages
Branch "feature_x" → facts_feature_x, relations_feature_x, observations_feature_x,
                      conversations_feature_x, messages_feature_x
```

**Implementation**: `BranchManager._branch_table(table_name, branch_name)` in `src/day1/core/branch_manager.py`

The five **branch-participating tables** are defined in `BRANCH_TABLES`:
```python
BRANCH_TABLES = ["facts", "relations", "observations", "conversations", "messages"]
```

### Why Table-Level, Not Row-Level

We chose table-level branching over row-level (branch_name column filtering) because:

1. **Zero-copy**: Creating a branch doesn't copy any data — MatrixOne handles CoW internally
2. **Native diff**: `DATA BRANCH DIFF` provides row-level change detection without application logic
3. **Native merge**: `DATA BRANCH MERGE` handles merging without application-layer SQL
4. **Query isolation**: Queries on a branch table automatically see only that branch's data
5. **No WHERE clause pollution**: Every query on every table doesn't need `WHERE branch_name = ?`

**Trade-off**: Branch operations require DDL (CREATE TABLE), which needs AUTOCOMMIT connections. We handle this with a dedicated `_get_autocommit_conn()` context manager.

---

## DATA BRANCH DIFF — Row-Level Change Detection

```sql
-- Get all changes (INSERT, UPDATE, DELETE) between two branch tables
DATA BRANCH DIFF `facts_feature_x` AGAINST `facts`
-- Returns: operation (INSERT/UPDATE/DELETE) + row data

-- Count-only variant for quick summary
DATA BRANCH DIFF `facts_feature_x` AGAINST `facts` OUTPUT COUNT
-- Returns: table_name, insert_count, update_count, delete_count
```

**Usage in Day1**: `BranchManager.diff_branch_native()` and `MergeEngine.diff()`

The diff result feeds into:
- Dashboard diff view (showing what changed on a branch)
- Merge preview (what will be merged)
- Analytics (branch activity metrics)

---

## DATA BRANCH MERGE — Native Merge with Conflict Strategies

```sql
-- Merge with conflict skip (keep target's version on conflict)
DATA BRANCH MERGE `facts_feature_x` INTO `facts` WHEN CONFLICT SKIP

-- Merge with conflict accept (overwrite target with source)
DATA BRANCH MERGE `facts_feature_x` INTO `facts` WHEN CONFLICT ACCEPT
```

Day1 supports four merge strategies:

| Strategy | Implementation | Use Case |
|---|---|---|
| **native** | MatrixOne `DATA BRANCH MERGE` | Simple merges, no custom logic |
| **auto** | Application layer, cosine similarity > 0.85 = conflict | Smart dedup during merge |
| **cherry_pick** | Copy specific items by ID with remapping | Selective adoption |
| **squash** | Summarize branch into single fact | Clean up experimental branches |

**Implementation**: `MergeEngine.merge()` in `src/day1/core/merge_engine.py`

---

## FULLTEXT INDEX + MATCH AGAINST — BM25 Keyword Search

MatrixOne supports native fulltext indexing with BM25 scoring:

```sql
-- Create fulltext index on memory text columns
CREATE FULLTEXT INDEX ft_memories ON memories(text, context)

-- Search using BM25 scoring
SELECT *, MATCH(text, context) AGAINST('authentication pattern' IN NATURAL LANGUAGE MODE) AS relevance
FROM memories
WHERE MATCH(text, context) AGAINST('authentication pattern' IN NATURAL LANGUAGE MODE)
ORDER BY relevance DESC
```

**Fallback chain**: When FULLTEXT index is not available or query fails, Day1 falls back to `LIKE` pattern matching with word-level tokenization.

**Implementation**: `SearchEngine.search()` and `MemoryEngine.search()` both implement this fallback.

---

## vecf32 + cosine_similarity() — Native Vector Search

MatrixOne provides native vector storage and similarity computation:

```sql
-- Store embedding as vecf32 (stored as TEXT in practice)
INSERT INTO memories (text, embedding) VALUES ('fact text', '[0.1, 0.2, ...]')

-- Compute cosine similarity
SELECT *, cosine_similarity(embedding, '[0.1, 0.2, ...]') AS sim
FROM memories
WHERE embedding IS NOT NULL
ORDER BY sim DESC
LIMIT 10
```

**Embedding format conversion** (`src/day1/core/embedding.py`):
```python
def embedding_to_vecf32(vec: list[float]) -> str:
    """Convert Python list to MatrixOne vecf32 string format."""
    return "[" + ",".join(str(v) for v in vec) + "]"

def vecf32_to_embedding(vec_str: str) -> list[float]:
    """Convert vecf32 string back to Python list."""
    return [float(v) for v in vec_str.strip("[]").split(",")]
```

---

## Hybrid Search Design

Day1 combines BM25 keyword search and vector semantic search for optimal retrieval:

```
┌────────────────────────────────────────────────────┐
│                  HYBRID SEARCH                      │
│                                                      │
│   Query: "authentication pattern for FastAPI"        │
│                                                      │
│   ┌──────────────────┐   ┌──────────────────────┐  │
│   │  BM25 (Keyword)  │   │  Vector (Semantic)   │  │
│   │  MATCH AGAINST   │   │  cosine_similarity   │  │
│   │  Weight: 0.3     │   │  Weight: 0.7         │  │
│   └────────┬─────────┘   └──────────┬───────────┘  │
│            │                         │               │
│            └──────────┬──────────────┘               │
│                       ▼                              │
│            ┌──────────────────┐                      │
│            │  Score Fusion    │                      │
│            │  final = 0.3*bm25 + 0.7*cosine         │
│            │  + temporal_decay                        │
│            └────────┬─────────┘                      │
│                     ▼                                │
│            ┌──────────────────┐                      │
│            │  Ranked Results  │                      │
│            └──────────────────┘                      │
└────────────────────────────────────────────────────┘
```

**Temporal decay**: Recent memories score higher. The decay function applies an exponential weight based on how recently the memory was created, reflecting the individual memory regime where recent context is most important.

**Fallback strategy**:
1. Try MATCH AGAINST (native BM25) → if fails, fall back to LIKE
2. Try cosine_similarity (native vector) → if no embedding, skip vector score
3. If both fail, return results ordered by recency

---

## AS OF TIMESTAMP — Time-Travel Queries

MatrixOne supports querying historical state:

```sql
-- Query facts as they existed at a specific point in time
SELECT * FROM facts {AS OF TIMESTAMP '2026-02-20 14:30:00'}
```

**Usage in Day1**: `SnapshotManager.time_travel()` uses this to reconstruct branch state at any point. This is the database-native equivalent of Git's `git checkout <commit-hash>`.

---

## CREATE SNAPSHOT / CREATE PITR — Point-in-Time Recovery

```sql
-- Create a database-level snapshot
CREATE SNAPSHOT sp_before_merge FOR DATABASE day1

-- Create a PITR policy (continuous recovery window)
CREATE PITR pitr_day1 FOR DATABASE day1 RANGE 1 "d"
```

Day1 uses both application-layer snapshots (JSON serialization of memory state stored in the `snapshots` table) and MatrixOne native snapshots. The `SnapshotManager` (`src/day1/core/snapshot_manager.py`) coordinates between them.

---

## AUTOCOMMIT for DDL Operations

MatrixOne's DATA BRANCH operations (CREATE, DIFF, MERGE) and CREATE SNAPSHOT are DDL statements that cannot run inside uncommitted transactions. Day1 handles this with a dedicated autocommit connection:

```python
# In BranchManager
@asynccontextmanager
async def _get_autocommit_conn(self):
    """Get a raw connection with AUTOCOMMIT for DDL operations."""
    async with self._session.bind.connect() as raw_conn:
        conn = await raw_conn.execution_options(isolation_level="AUTOCOMMIT")
        yield conn
```

This pattern is used consistently across `BranchManager`, `MergeEngine`, and `SnapshotManager` whenever DATA BRANCH or SNAPSHOT operations are needed.

---

## Discussion: MatrixOne Considerations

### Performance at Scale
- **Branch count**: Each branch creates 5 tables. At 100 branches = 500 tables. What are MatrixOne's limits?
- **Vector search**: cosine_similarity() performance at 100K+ rows with 1536-dimensional embeddings
- **FULLTEXT index**: BM25 quality and relevance compared to dedicated search engines

### Compatibility
- **SQL dialect**: MatrixOne is MySQL-compatible but not identical. Some features (JSON functions, window functions) may behave differently
- **DATA BRANCH syntax**: This is MatrixOne-specific. No other database supports this exact syntax
- **vecf32 format**: Specific to MatrixOne's vector implementation

### Alternatives Considered
- **PostgreSQL + pgvector**: More mature, but no native branching or fulltext
- **SQLite + FTS5**: Simpler, but no vector support or branching
- **DuckDB**: Fast analytics, but no server mode for multi-agent access
