# Branch Engines

> BranchManager, MergeEngine, SnapshotManager, BranchTopologyEngine — Git-like version control for agent memory.

## Design Rationale

Branching is what distinguishes Day1 from simpler memory systems. Just as Git enables developers to experiment safely on feature branches, Day1 enables agents to explore different approaches without contaminating the shared knowledge base.

```
┌────────────────────────────────────────────────────────┐
│                  BRANCH LIFECYCLE                        │
│                                                          │
│  main ────────────────────────────────────────────────  │
│    │                               ▲                     │
│    ├──→ task/fix-auth ──→ merge ──┘                     │
│    │         │                                           │
│    │         ├──→ task/fix-auth/agent_1 ──→ merge ──┐   │
│    │         │                                      │   │
│    │         └──→ task/fix-auth/agent_2 ──→ merge ──┤   │
│    │                                                │   │
│    │         task/fix-auth ◄────────────────────────┘   │
│    │                                                     │
│    └──→ experiment/new-approach (may be archived)        │
│                                                          │
└────────────────────────────────────────────────────────┘
```

---

## BranchManager

**Source**: `src/day1/core/branch_manager.py`

### Purpose
Git-like branch operations using MatrixOne DATA BRANCH. Creates, lists, and manages branches with zero-copy table forking.

### Core Operations

| Method | Purpose | SQL Generated |
|---|---|---|
| `create_branch()` | Create new branch from parent | `DATA BRANCH CREATE TABLE facts_{name} FROM facts_{parent}` × 5 tables |
| `list_branches()` | List branches with status filter | `SELECT * FROM branch_registry` |
| `get_branch()` | Get branch metadata | `SELECT * FROM branch_registry WHERE branch_name = ?` |
| `archive_branch()` | Soft-delete branch | `UPDATE branch_registry SET status = 'archived'` |
| `diff_branch_native()` | Row-level diff | `DATA BRANCH DIFF facts_{source} AGAINST facts_{target}` |

### Branch Table Creation Flow

```
create_branch("feature_x", parent="main")
    │
    ├──→ Validate branch name (BranchTopologyEngine.validate_name())
    │
    ├──→ Register in branch_registry table
    │
    ├──→ For each of 5 BRANCH_TABLES:
    │       │
    │       └──→ AUTOCOMMIT connection
    │            │
    │            └──→ DATA BRANCH CREATE TABLE facts_feature_x FROM facts
    │                 DATA BRANCH CREATE TABLE relations_feature_x FROM relations
    │                 DATA BRANCH CREATE TABLE observations_feature_x FROM observations
    │                 DATA BRANCH CREATE TABLE conversations_feature_x FROM conversations
    │                 DATA BRANCH CREATE TABLE messages_feature_x FROM messages
    │
    └──→ Return branch metadata
```

### AUTOCOMMIT Pattern
DATA BRANCH operations are DDL and cannot run inside transactions:

```python
@asynccontextmanager
async def _get_autocommit_conn(self):
    raw_conn = await self._session.connection()
    conn = await raw_conn.execution_options(isolation_level="AUTOCOMMIT")
    yield conn
```

### Entry Points

| Surface | Trigger | Method |
|---|---|---|
| **MCP** | `memory_branch_create` | `create_branch()` |
| **MCP** | `memory_branch_list` | `list_branches()` |
| **API** | `POST /branches` | `create_branch()` |
| **API** | `GET /branches` | `list_branches()` |
| **API** | `DELETE /branches/{name}` | `archive_branch()` |
| **CLI** | `branch create <name>` | `create_branch()` |
| **TaskEngine** | `create_task()` | Creates task branch automatically |

---

## MergeEngine

**Source**: `src/day1/core/merge_engine.py`

### Purpose
Merges knowledge from one branch to another using four strategies, with conflict detection and audit trail.

### Four Merge Strategies

```
┌───────────────────────────────────────────────────────┐
│                  MERGE STRATEGIES                       │
│                                                         │
│  ┌─────────┐  Use when: simple merge, trust source     │
│  │ native  │  SQL: DATA BRANCH MERGE ... WHEN CONFLICT │
│  │         │  Speed: fastest (single SQL statement)     │
│  └─────────┘  Conflict: SKIP or ACCEPT (configurable)  │
│                                                         │
│  ┌─────────┐  Use when: smart dedup needed              │
│  │  auto   │  Algorithm: cosine_similarity > 0.85       │
│  │         │  = conflict (skip). Otherwise merge.        │
│  └─────────┘  Speed: moderate (N² similarity check)     │
│                                                         │
│  ┌─────────┐  Use when: only specific items wanted      │
│  │cherry_  │  Algorithm: copy by ID with remapping       │
│  │pick     │  Speed: fast (targeted copies)              │
│  └─────────┘  Result: selected items only                │
│                                                         │
│  ┌─────────┐  Use when: clean up experimental branch    │
│  │ squash  │  Algorithm: summarize all facts into one    │
│  │         │  Speed: fast (aggregation + single write)   │
│  └─────────┘  Result: single consolidated fact           │
└───────────────────────────────────────────────────────┘
```

### Conflict Detection (Auto Strategy)

For the `auto` strategy, conflicts are detected using embedding similarity:

```
For each fact in source_branch:
    For each fact in target_branch:
        similarity = cosine_similarity(source.embedding, target.embedding)
        if similarity > 0.85:
            CONFLICT → skip (existing fact covers this)
        else:
            NO CONFLICT → merge (copy to target)
```

### Merge Audit Trail

Every merge creates a `MergeHistory` record:
- Source/target branches
- Strategy used
- Facts merged, skipped, conflicted
- Timestamp

### Entry Points

| Surface | Method |
|---|---|
| **API** | `POST /branches/{name}/merge` with strategy parameter |
| **CLI** | `branch merge <source> --strategy auto` |
| **TaskEngine** | `complete_task()` → optional merge to parent |

---

## SnapshotManager

**Source**: `src/day1/core/snapshot_manager.py`

### Purpose
Point-in-time recovery — create snapshots before risky operations, restore to any snapshot.

### Snapshot Types

| Type | Mechanism | Use Case |
|---|---|---|
| **Application** | JSON serialization of memory state → `snapshots` table | Portable, always available |
| **Native MO** | `CREATE SNAPSHOT sp FOR DATABASE day1` | Database-level, fastest restore |

### Core Operations

| Method | Purpose |
|---|---|
| `create_snapshot()` | Record snapshot metadata, optionally create MO native snapshot |
| `list_snapshots()` | List snapshots for a branch |
| `restore_snapshot()` | Restore memory state to snapshot point (using AS OF TIMESTAMP or JSON) |
| `time_travel()` | Query state at any timestamp without restoring |

### Entry Points

| Surface | Trigger | Method |
|---|---|---|
| **MCP** | `memory_snapshot` | `create_snapshot()` |
| **MCP** | `memory_snapshot_list` | `list_snapshots()` |
| **MCP** | `memory_restore` | `restore_snapshot()` |
| **API** | `POST /snapshots` | `create_snapshot()` |
| **API** | `GET /time-travel` | `time_travel()` |

---

## BranchTopologyEngine

**Source**: `src/day1/core/branch_topology_engine.py`

### Purpose
Manages the hierarchical branch tree, lifecycle policies, and naming conventions.

### Core Operations

| Method | Purpose |
|---|---|
| `get_topology()` | Hierarchical tree from root (main) |
| `get_branch_stats()` | Content statistics per branch |
| `enrich_branch()` | Add metadata (purpose, owner, TTL, tags) |
| `auto_archive()` | Apply expiry/merge archive policies |
| `get_expired_branches()` | List branches exceeding TTL |
| `validate_name()` | Validate branch naming conventions |

### Branch Naming Convention

```
task/{slug}                    — task root branch
task/{slug}/{agent_id}         — agent sub-branch
experiment/{description}       — experimental branch
template/{name}                — template source branch
```

### Auto-Archive Policies

Two archive triggers:
1. **Merged branches**: After successful merge to parent, source branch can be archived
2. **TTL expiry**: Branches with TTL metadata that exceed their lifetime are flagged for archival

### Entry Points

| Surface | Method |
|---|---|
| **API** | `GET /branches/topology` |
| **API** | `POST /branches/{name}/enrich` |
| **API** | `POST /branches/auto-archive` |
| **API** | `GET /branches/expired` |
| **Dashboard** | BranchTopologyPanel component (React Flow tree visualization) |

---

## Discussion

1. **Branch count limits**: Each branch creates 5 tables. At 1000 branches = 5000 tables. What's the practical limit?
2. **Orphan table cleanup**: If branch creation fails midway (3 of 5 tables created), how to clean up?
3. **Concurrent merges**: Two agents merging to main simultaneously — how to handle race conditions?
4. **Branch-aware queries**: Currently each engine needs to know which branch table to query. Can this be abstracted better?
5. **Snapshot storage**: Application-layer JSON snapshots can be large. Should we compress? Store externally?
