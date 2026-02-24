# Unified Conversation + Memory Branching

## Context

Day1 is a git-like memory layer for AI agents. It has two data layers:

- **Layer 2 (Memory)**: facts, relations, observations — structured knowledge with vector embeddings, branched via MatrixOne DATA BRANCH
- **Layer 1 (History)**: conversations, messages — raw chat history with sequence ordering and optional embeddings

Both layers have `branch_name` columns. But only Layer 2 participates in the branch infrastructure (`BRANCH_TABLES = ["facts", "relations", "observations"]`). Layer 1 is stored but not branched, not merged, not cherry-picked.

**Two problems to solve**:

1. **Capture resilience** — embedding failures currently prevent content from being saved across all three engines (fact, observation, message). This blocks all capture paths: hooks, REST API, and MCP tools. Content capture must always succeed regardless of embedding provider status.
2. **Unified branching** — conversations must become first-class citizens in the branch/merge/cherry-pick lifecycle. When we branch, everything follows. When we merge, we selectively promote what matters (git model).

---

## Phase 0: Capture-First — Embedding Must Never Block Content Saves

### Problem

All three write engines call `self._embedder.embed()` **before** the database write. If the embedding provider (OpenAI/Doubao) is down, rate-limited, or misconfigured, the exception propagates and **the content is never saved**.

There are three capture paths today:

| Capture path | Source | Uses embed? | Currently safe? |
|---|---|---|---|
| **Claude Code hooks** (user_prompt.py, assistant_response.py, pre_tool_use.py, post_tool_use.py) | Hook scripts via `run_hook()` | `embed=False` | Yes — hooks already disable embedding |
| **REST API** (`POST /conversations/{id}/messages`, `/messages/batch`, etc.) | Any HTTP client — other agent frameworks, SDKs, curl | `embed=True` (default) | **No** — embedding failure kills the write |
| **MCP tools** (`memory_log_message`, `memory_write_fact`, `memory_write_observation`) | Any MCP-compatible client (Claude Code, Cursor, custom agents) | `embed=True` (default) | **No** — embedding failure kills the write |

The hooks work around this by setting `embed=False`. But the REST API and MCP tools — the paths **any external agent framework** would use — call with `embed=True` (the default), meaning every non-hook caller is vulnerable.

### Affected code

| Engine | Method | File:Line | Vulnerable call |
|--------|--------|-----------|-----------------|
| `FactEngine` | `write_fact()` | `src/day1/core/fact_engine.py:58` | `vec = await self._embedder.embed(fact_text)` |
| `FactEngine` | `update_fact()` | `src/day1/core/fact_engine.py:114` | `vec = await self._embedder.embed(fact_text)` |
| `ObservationEngine` | `write_observation()` | `src/day1/core/observation_engine.py:57` | `vec = await self._embedder.embed(summary)` |
| `MessageEngine` | `write_message()` | `src/day1/core/message_engine.py:78` | `vec = await self._embedder.embed(embed_text)` |

### Fix

Wrap each embedding call in try/except. On failure, log a warning and save with `embedding=None`. Content capture always succeeds. Each file also needs `import logging` and `logger = logging.getLogger(__name__)` at module level.

#### `src/day1/core/fact_engine.py` — `write_fact()` (line 58)

```python
# BEFORE:
vec = await self._embedder.embed(fact_text)
fact = Fact(fact_text=fact_text, embedding=embedding_to_vecf32(vec), ...)

# AFTER:
embedding_str = None
try:
    vec = await self._embedder.embed(fact_text)
    embedding_str = embedding_to_vecf32(vec)
except Exception as e:
    logger.warning("Embedding failed for fact, saving without: %s", e)
fact = Fact(fact_text=fact_text, embedding=embedding_str, ...)
```

#### `src/day1/core/fact_engine.py` — `update_fact()` (line 114)

```python
# BEFORE:
vec = await self._embedder.embed(fact_text)
values["fact_text"] = fact_text
values["embedding"] = embedding_to_vecf32(vec)

# AFTER:
values["fact_text"] = fact_text
try:
    vec = await self._embedder.embed(fact_text)
    values["embedding"] = embedding_to_vecf32(vec)
except Exception as e:
    logger.warning("Embedding failed for fact update, keeping old: %s", e)
```

#### `src/day1/core/observation_engine.py` — `write_observation()` (line 57)

```python
# BEFORE:
vec = await self._embedder.embed(summary)
obs = Observation(summary=summary, embedding=embedding_to_vecf32(vec), ...)

# AFTER:
embedding_str = None
try:
    vec = await self._embedder.embed(summary)
    embedding_str = embedding_to_vecf32(vec)
except Exception as e:
    logger.warning("Embedding failed for observation, saving without: %s", e)
obs = Observation(summary=summary, embedding=embedding_str, ...)
```

#### `src/day1/core/message_engine.py` — `write_message()` (line 78)

```python
# BEFORE:
if embed and content:
    embed_text = content[:2000]
    vec = await self._embedder.embed(embed_text)
    embedding_str = embedding_to_vecf32(vec)

# AFTER:
embedding_str = None
if embed and content:
    try:
        embed_text = content[:2000]
        vec = await self._embedder.embed(embed_text)
        embedding_str = embedding_to_vecf32(vec)
    except Exception as e:
        logger.warning("Embedding failed for message, saving without: %s", e)
```

### After this fix, every capture path is resilient

Any caller — hooks, REST API, MCP, or a future Python SDK — will always succeed in capturing content. Embedding becomes a best-effort enrichment, not a gate. Records saved without embeddings can be backfilled later (a batch job that queries `WHERE embedding IS NULL` and retries).

### Verification

- Unit test: mock embedder that raises `EmbeddingError` → verify fact/observation/message still saved with `embedding=None`
- Integration test: REST API `POST /conversations/{id}/messages` with embedding provider down → 200 OK, message saved
- Verify existing tests still pass (MockEmbedding doesn't raise, so behavior unchanged)

---

## Phase 1: Add Conversations/Messages to Branch Infrastructure

### 1.1 Extend BRANCH_TABLES

**File**: `src/day1/core/branch_manager.py:20`

```python
# Current:
BRANCH_TABLES = ["facts", "relations", "observations"]

# Change to:
BRANCH_TABLES = ["facts", "relations", "observations", "conversations", "messages"]
```

This single change means:
- `create_branch()` runs `DATA BRANCH CREATE TABLE` for all 5 tables (zero-copy, CoW — no performance cost)
- `diff_branch()` and `diff_branch_count()` diff all 5 tables
- `merge_branch_native()` merges all 5 tables
- `archive_branch()` drops all 5 suffixed tables

### 1.2 Fix Conversation.metadata_json for DATA BRANCH DIFF compatibility

**File**: `src/day1/db/models.py:289`

MatrixOne's `DATA BRANCH DIFF` cannot handle MySQL type 245 (JSON). The `JsonText` type decorator (`models.py:27-49`) was created specifically for this — it stores JSON as TEXT. `Message` already uses `JsonText` for `tool_calls_json` (line 317) and `metadata_json` (line 328). But `Conversation.metadata_json` still uses native `JSON`:

```python
# Current (Conversation model, line 289):
metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

# Change to:
metadata_json: Mapped[dict | None] = mapped_column("metadata", JsonText, nullable=True)
```

**Migration note**: If there's existing data, run DDL: `ALTER TABLE conversations MODIFY COLUMN metadata TEXT`. JsonText stores the same data (JSON string) as TEXT column type, so existing values remain valid.

### 1.3 Add optional `tables` parameter to `create_branch()`

**File**: `src/day1/core/branch_manager.py:68`

For Phase 3 (curated branches), we need to selectively branch only certain tables:

```python
async def create_branch(
    self,
    branch_name: str,
    parent_branch: str = "main",
    description: str | None = None,
    tables: list[str] | None = None,  # NEW: override which tables to branch
) -> BranchRegistry:
```

When `tables` is None (default), use `BRANCH_TABLES` (all 5). When provided, branch only those tables. This enables:
- **Full branch**: `create_branch("feature-x")` — branches everything
- **Memory-only branch**: `create_branch("mem-only", tables=["facts", "relations", "observations"])`
- **Curated branch**: `create_branch("curated", tables=[])` — empty start, cherry-pick items in

Inside the method, replace:
```python
for table in BRANCH_TABLES:
```
with:
```python
for table in (tables if tables is not None else BRANCH_TABLES):
```

### 1.4 Scores table — JsonText compatibility

**File**: `src/day1/db/models.py:377`

The `Score` model also uses `JsonText` for `metadata_json` (line 377) — this is already correct. No changes needed. But note: `Score` has `branch_name` and could potentially participate in branching too. For now, we leave it out of `BRANCH_TABLES` since scores are more of an evaluation artifact than core memory.

### 1.5 Verification

- Create a branch → verify 5 suffixed tables exist
- Run `DATA BRANCH DIFF` on conversations/messages tables → no errors
- Write conversation + messages on the branch → diff shows them
- Archive → all 5 suffixed tables dropped
- Existing tests pass

---

## Phase 2: Conversation-Aware Merge Engine

### 2.1 Extend BranchDiff

**File**: `src/day1/core/merge_engine.py`

Currently `BranchDiff` tracks `new_facts`, `new_relations`, `new_observations`, `conflicts`. Add:

```python
class BranchDiff:
    def __init__(
        self,
        new_facts: list[Fact],
        new_relations: list[Relation],
        new_observations: list[Observation],
        new_conversations: list[Conversation],   # NEW
        new_messages: list[Message],              # NEW
        conflicts: list[dict],
    ) -> None:
        ...
```

Import `Conversation`, `Message` from `day1.db.models`.

### 2.2 Extend `diff()` method

After existing fact/relation/observation diffing, add:

```python
# Conversations: new = in source but not in target (by ID)
source_convs = await self._get_conversations(source_branch)
target_convs = await self._get_conversations(target_branch)
target_conv_ids = {c.id for c in target_convs}
new_conversations = [c for c in source_convs if c.id not in target_conv_ids]

# Messages from new conversations
new_messages = []
for conv in new_conversations:
    msgs = await self._get_conversation_messages(conv.id)
    new_messages.extend(msgs)
```

Add two helper methods:
```python
async def _get_conversations(self, branch_name: str) -> list[Conversation]:
    result = await self._session.execute(
        select(Conversation).where(Conversation.branch_name == branch_name)
    )
    return list(result.scalars().all())

async def _get_conversation_messages(self, conversation_id: str) -> list[Message]:
    result = await self._session.execute(
        select(Message).where(Message.conversation_id == conversation_id)
            .order_by(Message.sequence_num.asc())
    )
    return list(result.scalars().all())
```

### 2.3 Extend merge strategies

**`_auto_merge()`**: After merging facts/relations/observations, merge conversations + messages. Need to handle ID mapping — when a conversation is copied to the target branch, its messages need the new conversation ID:

```python
# Merge conversations
conv_id_map = {}  # old_id → new_id
for conv in diff.new_conversations:
    new_conv = Conversation(
        session_id=conv.session_id, agent_id=conv.agent_id,
        task_id=conv.task_id, branch_name=target,
        title=conv.title, parent_conversation_id=conv.parent_conversation_id,
        status=conv.status, message_count=conv.message_count,
        total_tokens=conv.total_tokens, model=conv.model,
        metadata_json=conv.metadata_json,
    )
    self._session.add(new_conv)
    await self._session.flush()  # get new_conv.id
    conv_id_map[conv.id] = new_conv.id
    merged_ids.append(conv.id)

# Merge messages (update conversation_id to new ID)
for msg in diff.new_messages:
    new_conv_id = conv_id_map.get(msg.conversation_id, msg.conversation_id)
    new_msg = Message(
        conversation_id=new_conv_id,
        session_id=msg.session_id, agent_id=msg.agent_id,
        role=msg.role, content=msg.content, thinking=msg.thinking,
        tool_calls_json=msg.tool_calls_json, token_count=msg.token_count,
        model=msg.model, sequence_num=msg.sequence_num,
        embedding=msg.embedding, branch_name=target,
        metadata_json=msg.metadata_json,
    )
    self._session.add(new_msg)
    merged_ids.append(msg.id)
```

**`_cherry_pick()`**: Extend the lookup chain. After trying facts and observations, try conversations:

```python
# Try conversations
result = await self._session.execute(
    select(Conversation).where(Conversation.id == item_id, Conversation.branch_name == source)
)
conv = result.scalar_one_or_none()
if conv:
    # Copy conversation + all its messages to target
    ...
    merged_count += 1
    continue
```

**`_squash_merge()`**: Copy all conversations + messages (same as auto, but without conflict filtering since there are no fact-level conflicts to handle).

**`_native_merge()`**: Already works — it iterates `BRANCH_TABLES` and runs `DATA BRANCH MERGE` for each. Since Phase 1 adds conversations/messages to `BRANCH_TABLES`, native merge automatically includes them.

### 2.4 Update `to_dict()` on BranchDiff

```python
def to_dict(self) -> dict:
    return {
        ...,
        "new_conversations": [
            {"id": c.id, "title": c.title, "message_count": c.message_count}
            for c in self.new_conversations
        ],
        "new_messages_count": len(self.new_messages),
    }
```

### 2.5 Verification

- Create branch → write conversation + messages → `diff()` returns them in `new_conversations`/`new_messages`
- `_auto_merge()` → conversations + messages appear on target with correct ID mapping
- `_cherry_pick()` with a conversation ID → conversation + all messages copied
- Native merge → conversations merged via DATA BRANCH MERGE
- Existing merge tests pass

---

## Phase 3: Conversation Cherry-Pick Engine

### 3.1 New file: `src/day1/core/conversation_cherry_pick.py`

Reuses patterns from:
- `ConversationEngine.fork_conversation()` (`conversation_engine.py:101-201`) — copying messages with sequence renumbering
- `MergeEngine._cherry_pick()` (`merge_engine.py:184-247`) — selective item copy by ID

```python
class ConversationCherryPick:
    """Cherry-pick conversations or message ranges between branches."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def cherry_pick_conversation(
        self,
        conversation_id: str,
        target_branch: str,
        include_messages: bool = True,
    ) -> dict:
        """Copy an entire conversation + its messages to target branch.

        Steps:
        1. Read source conversation
        2. Create a copy on target_branch with new ID
        3. Copy all messages (if include_messages), updating branch_name + conversation_id
        4. Return {"conversation_id": new_id, "messages_copied": N}
        """

    async def cherry_pick_message_range(
        self,
        conversation_id: str,
        from_sequence: int,
        to_sequence: int,
        target_branch: str,
        title: str | None = None,
    ) -> dict:
        """Extract a contiguous message range into a new conversation on target branch.

        Steps:
        1. Read source conversation
        2. Read messages where from_sequence <= sequence_num <= to_sequence
        3. Create new conversation on target_branch
        4. Copy selected messages, renumbering sequences from 1
        5. Return {"conversation_id": new_id, "messages_copied": N}

        This is the core "pick the important parts" operation — extract a
        debugging chain, a decision sequence, or a fix workflow.
        """

    async def cherry_pick_to_curated_branch(
        self,
        branch_name: str,
        parent_branch: str,
        conversation_ids: list[str] | None = None,
        fact_ids: list[str] | None = None,
        description: str | None = None,
    ) -> dict:
        """Create a new branch containing only selected conversations + facts.

        Steps:
        1. Create branch via BranchManager with tables=[] (no DATA BRANCH copy)
        2. Register in branch_registry
        3. Cherry-pick each selected conversation (with messages) into it
        4. Cherry-pick each selected fact (copy row with new branch_name)
        5. Return {"branch_name": ..., "conversations": N, "facts": N}

        This creates a "starter kit" branch for future agents — curated
        context to build on without noise from the full history.
        """
```

### 3.2 Verification

- Cherry-pick conversation → exists on target branch with all messages
- Cherry-pick message range (seq 5-10 of a 20-message conversation) → new conversation with 6 messages on target
- Create curated branch from 3 conversations + 5 facts → only those items present
- Source data unchanged (cherry-pick is copy, not move)

---

## Phase 4: MCP Tools & API Endpoints

### 4.1 New MCP tools

**File**: `src/day1/mcp/tools.py`

```python
Tool(
    name="memory_cherry_pick_conversation",
    description="Cherry-pick a conversation or message range to another branch.",
    inputSchema={
        "type": "object",
        "properties": {
            "conversation_id": {"type": "string", "description": "Source conversation"},
            "target_branch": {"type": "string", "description": "Target branch"},
            "from_sequence": {"type": "integer", "description": "Start of message range (optional)"},
            "to_sequence": {"type": "integer", "description": "End of message range (optional)"},
        },
        "required": ["conversation_id", "target_branch"],
    },
),
Tool(
    name="memory_branch_create_curated",
    description="Create a branch from selected conversations and facts. Builds a curated starter for future agents.",
    inputSchema={
        "type": "object",
        "properties": {
            "branch_name": {"type": "string"},
            "parent_branch": {"type": "string", "description": "Default: main"},
            "conversation_ids": {"type": "array", "items": {"type": "string"}},
            "fact_ids": {"type": "array", "items": {"type": "string"}},
            "description": {"type": "string"},
        },
        "required": ["branch_name"],
    },
),
```

Add handlers in `handle_tool_call()` that call `ConversationCherryPick` methods.

### 4.2 New API endpoints

**File**: `src/day1/api/routes/conversations.py` (extend existing)

```python
@router.post("/conversations/{conversation_id}/cherry-pick")
async def cherry_pick_conversation(conversation_id, body: CherryPickRequest, ...):
    # body: { target_branch: str, from_sequence?: int, to_sequence?: int }
```

**File**: `src/day1/api/routes/branches.py` (extend existing)

```python
@router.post("/branches/curated")
async def create_curated_branch(body: CuratedBranchRequest, ...):
    # body: { branch_name, parent_branch?, conversation_ids?, fact_ids?, description? }
```

### 4.3 Verification

- MCP: `memory_cherry_pick_conversation` → conversation copied
- MCP: `memory_branch_create_curated` → curated branch created
- API: `POST /conversations/{id}/cherry-pick` → 200 OK
- API: `POST /branches/curated` → 201 Created

---

## Phase 5: Hook & Session Integration

### 5.1 Branch-aware conversation creation

**Files**: `src/day1/hooks/user_prompt.py`, `src/day1/hooks/assistant_response.py`, `src/day1/hooks/pre_tool_use.py`, `src/day1/hooks/post_tool_use.py`

Currently, hooks create conversations with default `branch_name="main"`. When a session is associated with a task/agent, the conversation should use the task/agent branch:

```python
# In all hooks that create conversations:
branch = os.environ.get("BM_BRANCH") or "main"
conv = await conv_engine.create_conversation(
    session_id=sid,
    agent_id=agent_id,
    task_id=os.environ.get("BM_TASK_ID"),
    branch_name=branch,
    ...
)
```

### 5.2 Branch-aware context injection at session start

**File**: `src/day1/hooks/session_start.py`

When injecting context, include recent conversations from the active branch:

```python
active_branch = os.environ.get("BM_BRANCH") or "main"
convs = await conv_engine.list_conversations(branch_name=active_branch, limit=3)
if convs:
    context_parts.append("\n## Recent Conversations on Branch")
    for c in convs:
        title = c.title or "Untitled"
        context_parts.append(f"- {title} ({c.message_count} messages)")
```

### 5.3 Verification

- `BM_BRANCH=task/fix-bug` → user prompt → conversation created on `task/fix-bug` branch
- Session start with conversations on branch → they appear in injected context
- Without `BM_BRANCH` → conversations default to "main"

---

## Phase 6: Dashboard UI — Branch-Conversation Integration

### Current state of the dashboard

The dashboard (`dashboard/src/`) is a React + Vite + Tailwind app using:
- **React Flow** (`@xyflow/react`) for interactive branch graph (`BranchTree.tsx`)
- **D3.js** for timeline scatter plots and trend charts
- **Zustand** for state (two stores: `branchStore.ts` + `conversationStore.ts`)
- **3-tab layout** in `App.tsx`: Memory | Conversations | Analytics

The critical gap: **`Conversation.branch_name` and `Message.branch_name` exist in the TypeScript schema (`types/schema.ts`) and come from the API, but the frontend never shows or filters by them.** The two stores are completely disconnected — selecting a branch in BranchTree has no effect on the Conversations tab.

### 6.1 BranchTree: Show conversation counts per branch

**File**: `dashboard/src/components/BranchTree.tsx`

Each branch node currently shows the branch name and status. Add a conversation count badge:

```
┌─────────────────┐
│  feature-x       │
│  active • 3 convs│
└─────────────────┘
```

**Implementation**:
- Backend: Extend `GET /api/v1/branches` response to include `conversation_count` per branch (or add a separate lightweight endpoint)
- Frontend: Add the count to the React Flow node label
- `schema.ts`: Add `conversation_count?: number` to `Branch` interface

### 6.2 ConversationList: Add branch filter

**File**: `dashboard/src/components/ConversationList.tsx`

Currently shows all conversations (up to 50) with no branch awareness. Add:

1. **Branch filter dropdown** at the top of the conversation list — populated from `branchStore.branches`
2. **Branch badge** on each conversation item — small tag showing which branch it belongs to
3. **"Show all" / "This branch"** toggle

**Implementation**:
- `api/client.ts`: The `listConversations()` function already accepts a `params` object but doesn't pass `branch` to the API. Fix: add `branch` param. The backend `GET /api/v1/conversations?branch=feature-x` already supports this.
- `conversationStore.ts`: Add `branchFilter: string | null` state and pass it to `fetchConversations()`

### 6.3 Cross-store linking: Branch selection filters conversations

**Files**: `dashboard/src/stores/branchStore.ts`, `dashboard/src/stores/conversationStore.ts`

When the user clicks a branch in BranchTree, the conversation list should filter to that branch. Two approaches:

- **Option A**: Zustand `subscribe` — branchStore subscribes to conversationStore's branch filter
- **Option B (simpler)**: In `App.tsx`, when switching to Conversations tab, auto-set the branch filter to `branchStore.activeBranch`

Recommend **Option B** — less coupling, explicit behavior.

### 6.4 Cherry-pick UI in ConversationThread

**File**: `dashboard/src/components/ConversationThread.tsx` (extend)

Add cherry-pick controls to the conversation thread view:

1. **"Cherry-pick to branch" button** on the conversation header — copies entire conversation to a target branch
2. **Message range selection** — checkboxes or shift-click to select a range of messages
3. **"Cherry-pick selected" button** — appears when messages are selected, opens a modal to choose target branch

```
┌─────────────────────────────────────────────┐
│ Conversation: "Debug OAuth flow"             │
│ Branch: task/fix-auth  [Cherry-pick ▾]       │
├─────────────────────────────────────────────┤
│ ☐ #1 [user] "The OAuth callback is failing" │
│ ☑ #2 [assistant] "I found the issue..."     │
│ ☑ #3 [tool_call] Edit auth_handler.py       │
│ ☑ #4 [tool_result] File modified             │
│ ☐ #5 [assistant] "The fix is deployed..."    │
├─────────────────────────────────────────────┤
│ [Cherry-pick selected (3 messages) →]        │
└─────────────────────────────────────────────┘
```

**Implementation**:
- Add `selectedMessageIds: Set<string>` to `conversationStore`
- Cherry-pick button calls `POST /api/v1/conversations/{id}/cherry-pick` (Phase 4 endpoint)
- Target branch selector: dropdown from `branchStore.branches`

### 6.5 Curated Branch Wizard

**File**: `dashboard/src/components/CuratedBranchWizard.tsx` (**NEW**)

A multi-step modal for creating a curated branch:

```
Step 1: Name & parent
  ┌─────────────────────────────────────┐
  │ Branch name: [________________]      │
  │ Parent:      [main ▾]               │
  │ Description: [________________]      │
  └─────────────────────────────────────┘

Step 2: Select conversations
  ┌─────────────────────────────────────┐
  │ ☑ "Debug OAuth flow" (12 msgs)      │
  │ ☐ "Setup CI pipeline" (8 msgs)      │
  │ ☑ "Architecture decision" (5 msgs)  │
  │ ☐ "Test exploration" (20 msgs)      │
  └─────────────────────────────────────┘

Step 3: Select facts
  ┌─────────────────────────────────────┐
  │ ☑ "OAuth requires PKCE flow" (0.95) │
  │ ☑ "DB uses connection pool=10" (0.9)│
  │ ☐ "Temp debug flag added" (0.5)     │
  └─────────────────────────────────────┘

Step 4: Review & create
  ┌─────────────────────────────────────┐
  │ Branch: curated/auth-context         │
  │ Parent: main                         │
  │ 2 conversations, 3 facts            │
  │ [Create Curated Branch]             │
  └─────────────────────────────────────┘
```

**Implementation**:
- API call: `POST /api/v1/branches/curated` (Phase 4 endpoint)
- Can be opened from BranchTree (right-click or toolbar button) or from the Conversations tab
- After creation, refresh branch tree and optionally switch to the new branch

### 6.6 MergePanel: Show conversations in diff preview

**File**: `dashboard/src/components/MergePanel.tsx`

Currently shows fact/relation/observation diffs for merge. Extend to show conversations:

```
Merge feature-x → main
────────────────────────
New facts: 5
New relations: 3
New observations: 12
New conversations: 2        ← NEW
  - "Debug OAuth flow" (12 messages)
  - "Architecture review" (5 messages)
────────────────────────
[Merge] [Cherry-pick] [Cancel]
```

**Implementation**:
- Backend diff response (Phase 2) already includes `new_conversations` and `new_messages_count`
- Frontend: render the new fields in MergePanel's diff display

### 6.7 Files to modify/create (dashboard)

| File | Changes |
|------|---------|
| `dashboard/src/types/schema.ts` | Add `conversation_count` to `Branch`, add cherry-pick types |
| `dashboard/src/api/client.ts` | Pass `branch` param to `listConversations()`, add `cherryPickConversation()`, add `createCuratedBranch()` |
| `dashboard/src/stores/branchStore.ts` | No changes (or add conversation_count caching) |
| `dashboard/src/stores/conversationStore.ts` | Add `branchFilter`, `selectedMessageIds`, cherry-pick actions |
| `dashboard/src/components/BranchTree.tsx` | Show conversation count badge per branch node |
| `dashboard/src/components/ConversationList.tsx` | Add branch filter dropdown, branch badge per item |
| `dashboard/src/components/ConversationThread.tsx` | Add message selection checkboxes, cherry-pick button |
| `dashboard/src/components/MergePanel.tsx` | Show conversations in diff preview |
| `dashboard/src/components/CuratedBranchWizard.tsx` | **NEW**: Multi-step curated branch creation modal |
| `dashboard/src/App.tsx` | Wire cross-store branch→conversation filter, add wizard trigger |

### 6.8 Verification

- BranchTree shows conversation counts per branch
- Clicking a branch filters the conversation list to that branch
- Cherry-pick button on conversation → copies to target branch, appears in target's list
- Message range selection → cherry-pick creates new conversation on target
- Curated branch wizard → creates branch with only selected items
- MergePanel diff preview includes conversation summary

---

## Key Files Summary

| File | Phase | Changes |
|------|-------|---------|
| `src/day1/core/fact_engine.py` | 0 | Try/except around embedding in `write_fact()` and `update_fact()`, add logger |
| `src/day1/core/observation_engine.py` | 0 | Try/except around embedding in `write_observation()`, add logger |
| `src/day1/core/message_engine.py` | 0 | Try/except around embedding in `write_message()`, add logger |
| `src/day1/core/branch_manager.py` | 1 | Add conversations/messages to `BRANCH_TABLES`, add `tables` param to `create_branch()` |
| `src/day1/db/models.py` | 1 | Change `Conversation.metadata_json` from `JSON` to `JsonText` |
| `src/day1/core/merge_engine.py` | 2 | Extend `BranchDiff`, `diff()`, all merge strategies for conversations |
| `src/day1/core/conversation_cherry_pick.py` | 3 | **NEW**: Cherry-pick engine (full, range, curated branch) |
| `src/day1/mcp/tools.py` | 4 | Add `memory_cherry_pick_conversation` + `memory_branch_create_curated` tools |
| `src/day1/api/routes/conversations.py` | 4 | Add cherry-pick endpoint |
| `src/day1/api/routes/branches.py` | 4 | Add curated branch creation endpoint |
| `src/day1/hooks/user_prompt.py` | 5 | Branch-aware conversation creation via `BM_BRANCH` |
| `src/day1/hooks/assistant_response.py` | 5 | Branch-aware conversation creation via `BM_BRANCH` |
| `src/day1/hooks/pre_tool_use.py` | 5 | Branch-aware conversation creation via `BM_BRANCH` |
| `src/day1/hooks/post_tool_use.py` | 5 | Branch-aware conversation creation via `BM_BRANCH` |
| `src/day1/hooks/session_start.py` | 5 | Branch-aware context injection |
| `dashboard/src/types/schema.ts` | 6 | Add `conversation_count` to Branch, cherry-pick types |
| `dashboard/src/api/client.ts` | 6 | Pass `branch` to listConversations, add cherry-pick + curated API calls |
| `dashboard/src/stores/conversationStore.ts` | 6 | Add `branchFilter`, `selectedMessageIds`, cherry-pick actions |
| `dashboard/src/components/BranchTree.tsx` | 6 | Conversation count badge per branch node |
| `dashboard/src/components/ConversationList.tsx` | 6 | Branch filter dropdown + branch badge per item |
| `dashboard/src/components/ConversationThread.tsx` | 6 | Message selection checkboxes + cherry-pick button |
| `dashboard/src/components/MergePanel.tsx` | 6 | Show conversations in merge diff preview |
| `dashboard/src/components/CuratedBranchWizard.tsx` | 6 | **NEW**: Multi-step curated branch wizard |
| `dashboard/src/App.tsx` | 6 | Cross-store wiring, wizard trigger |

## Existing Code to Reuse

| Existing Code | Reuse For |
|---|---|
| `ConversationEngine.fork_conversation()` (`conversation_engine.py:101`) | Pattern for copying conversations + messages between branches |
| `MergeEngine._cherry_pick()` (`merge_engine.py:184`) | Pattern for cherry-picking items by ID |
| `_branch_table()` helper (`branch_manager.py:23`) | Table name resolution for branch-suffixed tables |
| `JsonText` type decorator (`models.py:27`) | Already used by Message; extend to Conversation |
| `MessageEngine.write_message()` (`message_engine.py:28`) | Creating messages in cherry-picked conversations |
| `ConsolidationEngine._deduplicate_facts()` (`consolidation_engine.py:241`) | Pattern for Jaccard-based text dedup without embedding dependency |
| `MergePanel.tsx` diff display pattern | Pattern for showing conversations in diff preview |
| `ConversationThread.tsx` message rendering | Pattern for cherry-pick message selection UI |
| `useVisiblePolling()` hook (`hooks/usePolling.ts`) | Polling pattern for new branch-filtered conversation fetches |

## Implementation Order

```
Phase 0  (Capture resilience — embedding never blocks saves)
   │
   ▼
Phase 1  (Branch infrastructure — conversations in BRANCH_TABLES)
   │
   ▼
Phase 2  (Merge engine — conversation-aware diff/merge)
   │
   ▼
Phase 3  (Cherry-pick engine — full, range, curated branch)
   │
   ▼
Phase 4  (MCP tools & API — expose new capabilities)
   │
   ├───────────────────┐
   ▼                   ▼
Phase 5              Phase 6
(Hook integration)   (Dashboard UI)
```

Phases 0→4 are sequential (each builds on the previous). Phases 5 and 6 can be done in parallel — hooks and UI are independent consumers of the same backend APIs.

## End-to-End Verification

1. **Capture resilience**: Disconnect embedding provider → write fact, observation, message via API and MCP → all save with `embedding=None`
2. **Branch lifecycle**: Create branch → verify 5 tables branched → write conversation on branch → diff shows it → merge → verify conversation on target → archive → verify tables dropped
3. **Cherry-pick conversation**: Write 5 conversations on branch-A → cherry-pick 2 to branch-B → verify only 2 on branch-B, source unchanged
4. **Cherry-pick message range**: 20-message conversation → cherry-pick messages 5-10 → new 6-message conversation on target
5. **Curated branch**: 10 conversations + 20 facts on main → curated branch with 3 conversations + 5 facts → verify only selected items
6. **Hooks**: `BM_BRANCH=task/fix-bug` → user prompt → assistant response → conversation on correct branch
7. **Dashboard — branch filter**: Select branch in BranchTree → Conversations tab filters to that branch
8. **Dashboard — cherry-pick**: Select messages in ConversationThread → cherry-pick to another branch → appears in target branch's conversation list
9. **Dashboard — curated wizard**: Open wizard → select 2 conversations + 3 facts → create curated branch → branch appears in tree with correct counts
10. **Dashboard — merge preview**: Open MergePanel → diff shows new conversations → merge → conversations appear on target
11. **Existing tests**: `pytest tests/` — all pass (no breaking changes)
