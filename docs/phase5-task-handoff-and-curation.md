# Phase 5: Task Handoff, Knowledge Curation & Sharing

**Status**: Design
**Dependencies**: Phase 1-4 Complete
**Goal**: 让 Day1 成为 agent 记忆的 "GitHub" — 任务可传递、对话可 cherry-pick、正确知识可 replay & 分享。

---

## 0. 需求分析

用户原话：
> 任务可以被传递，可以有分支，正确的对话和判断可以被 cherry pick，
> 所有合并的正确记忆以及对话，可以被 replay 以及分享。

拆解为四个核心能力：

| # | 能力 | 现状 | 缺口 |
|---|------|------|------|
| 1 | **Task Handoff** — 任务可被传递 | `get_task_context()` 返回 objectives + agents + facts | 无 resume 语义，无对话历史传递，无 stall detection |
| 2 | **Task Branching** — 任务可有分支 | Branch + Task 模型已存在 | 无 "sub-task" 层级，无 conversation-level branching on task |
| 3 | **Conversation Cherry-Pick** — 正确对话可 cherry-pick | fact/obs 级 cherry_pick 已有 | 无 conversation/message 级 cherry-pick，无 "verified" 质量门 |
| 4 | **Replay & Share** — 合并的知识可 replay 和分享 | 单对话级 replay 已有 | 无 task-level replay，无导出/分享包，无 "curated bundle" |

---

## 1. 设计哲学

### 1.1 Git 类比的延伸

```
Git 概念              Day1 类比                    Phase 5 新增
──────────           ──────────                   ────────────
repository        →  project (main branch)
branch            →  memory branch                sub-task branches
commit            →  fact / observation / message
cherry-pick       →  fact cherry-pick              + conversation cherry-pick
pull request      →  merge request                 + review gate (curation)
release tag       →  snapshot                      + curated bundle (share)
git clone         →  —                             + knowledge export/import
git log           →  timeline                      + task-level replay
CODEOWNERS        →  —                             + verification policy
```

### 1.2 核心原则

1. **Handoff 是 first-class primitive** — 不是 "读上一次的 context"，而是一个完整的交接协议
2. **Curation 发生在 merge 时** — cherry-pick + LLM 验证 = 只有正确的知识进入 main
3. **Replay 覆盖完整 task 生命周期** — 不仅重放单个对话，还能重放整个任务的工作流
4. **Share 是 curated knowledge 的自然产物** — 导出的是经过验证的知识包，不是原始数据

---

## 2. 数据模型扩展

### 2.1 新增：Knowledge Bundle（知识包）

```sql
-- 一个 curated knowledge bundle，可被分享和导入
CREATE TABLE knowledge_bundles (
    id            VARCHAR(36) PRIMARY KEY,
    name          VARCHAR(200) NOT NULL,
    description   TEXT,
    bundle_type   VARCHAR(30) NOT NULL,       -- 'task_export' | 'curated' | 'template'
    source_task_id  VARCHAR(36),              -- 来源 task（如果是 task export）
    source_branch VARCHAR(100),               -- 来源分支

    -- 内容统计
    fact_count    INT DEFAULT 0,
    relation_count INT DEFAULT 0,
    conversation_count INT DEFAULT 0,
    message_count INT DEFAULT 0,

    -- Bundle 数据（JSON 序列化的完整包）
    bundle_data   JSON,                       -- {facts, relations, conversations, messages}

    -- 版本与质量
    version       VARCHAR(20) DEFAULT '1.0',
    verification_status VARCHAR(20) DEFAULT 'draft',  -- 'draft' | 'verified' | 'published'
    verified_by   VARCHAR(100),               -- agent_id 或 'llm_judge'
    verification_score FLOAT,                 -- LLM-as-judge 综合评分

    -- 分享
    share_token   VARCHAR(64) UNIQUE,         -- 分享 token（可选）
    visibility    VARCHAR(20) DEFAULT 'private',  -- 'private' | 'team' | 'public'

    tags          JSON,                       -- 标签，用于发现
    metadata      JSON,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_bundle_type ON knowledge_bundles(bundle_type);
CREATE INDEX idx_bundle_source_task ON knowledge_bundles(source_task_id);
CREATE INDEX idx_bundle_visibility ON knowledge_bundles(visibility);
CREATE INDEX idx_bundle_share ON knowledge_bundles(share_token);
```

### 2.2 新增：Handoff Record（交接记录）

```sql
-- 任务交接的完整记录
CREATE TABLE handoff_records (
    id              VARCHAR(36) PRIMARY KEY,
    task_id         VARCHAR(36) NOT NULL,

    -- 交接双方
    from_agent_id   VARCHAR(100),             -- 发出方（可为 NULL = 新任务）
    from_session_id VARCHAR(100),
    to_agent_id     VARCHAR(100),             -- 接收方（可为 NULL = 待认领）
    to_session_id   VARCHAR(100),

    -- 交接内容
    handoff_type    VARCHAR(30) NOT NULL,      -- 'full' | 'partial' | 'escalation' | 'checkpoint'
    context_snapshot JSON NOT NULL,            -- 冻结的 task context（完整包）

    -- 交接质量
    instructions    TEXT,                      -- 给下一个 agent 的指令
    priority_items  JSON,                      -- 优先处理的 objective IDs
    blockers        JSON,                      -- 已知阻碍

    status          VARCHAR(20) DEFAULT 'pending',  -- 'pending' | 'accepted' | 'rejected'
    accepted_at     TIMESTAMP,

    metadata        JSON,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_handoff_task ON handoff_records(task_id);
CREATE INDEX idx_handoff_to ON handoff_records(to_agent_id);
CREATE INDEX idx_handoff_status ON handoff_records(status);
```

### 2.3 扩展：Conversation & Message 增加验证字段

```sql
-- 在现有 conversations 表增加
ALTER TABLE conversations ADD COLUMN verification_status VARCHAR(20) DEFAULT NULL;
    -- NULL = 未验证, 'verified' = 已验证, 'rejected' = 已拒绝
ALTER TABLE conversations ADD COLUMN verified_by VARCHAR(100) DEFAULT NULL;
ALTER TABLE conversations ADD COLUMN verification_score FLOAT DEFAULT NULL;

-- 在现有 messages 表增加
ALTER TABLE messages ADD COLUMN is_cherry_picked BOOLEAN DEFAULT FALSE;
    -- 标记是否被 cherry-pick 过
ALTER TABLE messages ADD COLUMN cherry_picked_to JSON DEFAULT NULL;
    -- [{conversation_id, branch_name, picked_at}]
```

### 2.4 扩展：Facts 增加验证状态

```sql
-- facts.status 现有值: 'active', 'superseded', 'invalidated'
-- 新增: 'verified', 'promoted'
-- verified = 经过 LLM 或人工验证
-- promoted = 已提升到 parent branch
```

---

## 3. Task Handoff Protocol（任务交接协议）

### 3.1 设计理念

交接不是"读上一次的输出"。交接是一个 **完整的上下文传递协议**：

```
                    ┌────────────────────────┐
                    │     Handoff Packet      │
                    │                        │
                    │  1. Task State          │  ← objectives, status, blockers
                    │  2. Agent History       │  ← who did what, their summaries
                    │  3. Key Facts           │  ← verified facts on task branch
                    │  4. Key Conversations   │  ← critical decision points
                    │  5. Unresolved Items    │  ← what still needs to be done
                    │  6. Instructions        │  ← handoff-specific guidance
                    │  7. Branch Pointer      │  ← where to continue working
                    │                        │
                    └────────────────────────┘
                              │
                    ┌─────────┴──────────┐
                    │   New Agent/Session  │
                    │                     │
                    │   Accepts handoff   │
                    │   Creates new branch│
                    │   Continues work    │
                    └─────────────────────┘
```

### 3.2 Handoff 类型

| 类型 | 场景 | Context 粒度 |
|------|------|-------------|
| `full` | Agent 完成，移交全部工作 | 完整 task context + all conversations |
| `partial` | Agent 完成部分，移交剩余 | 已完成 objectives 的 facts + 未完成 objectives 列表 |
| `escalation` | Agent 卡住，需要更高级的 agent | 完整 context + blockers + 失败尝试记录 |
| `checkpoint` | 定期保存进度，无交接 | 快照 context，不改变所有权 |

### 3.3 Handoff Engine

```python
class HandoffEngine:
    """Manages task handoff between agents/sessions."""

    async def create_handoff(
        self,
        task_id: str,
        from_agent_id: str | None = None,
        to_agent_id: str | None = None,
        handoff_type: str = "full",
        instructions: str | None = None,
        priority_objectives: list[int] | None = None,
        blockers: list[str] | None = None,
    ) -> HandoffRecord:
        """Create a handoff packet for a task.

        Steps:
        1. Freeze current task context (snapshot)
        2. Include key conversations with verification status
        3. Include all verified facts
        4. Record handoff in handoff_records
        5. If from_agent: consolidate agent's work first
        """

    async def accept_handoff(
        self,
        handoff_id: str,
        agent_id: str,
        session_id: str | None = None,
    ) -> dict:
        """Accept a handoff and prepare to continue work.

        Steps:
        1. Mark handoff as accepted
        2. Create new agent branch from task branch
        3. Inject handoff context into agent's session
        4. Return full context packet for the new agent
        """

    async def get_pending_handoffs(
        self,
        task_id: str | None = None,
        agent_id: str | None = None,
    ) -> list[HandoffRecord]:
        """List pending handoffs available for acceptance."""

    async def checkpoint(
        self,
        task_id: str,
        agent_id: str,
    ) -> HandoffRecord:
        """Create a checkpoint handoff (no ownership transfer).

        This is for periodic progress saving, enabling:
        - Stall detection (if no checkpoint in N minutes)
        - Mid-task recovery (if agent crashes)
        """
```

### 3.4 Context Snapshot 结构

```python
@dataclass
class HandoffContext:
    """The complete context packet passed during handoff."""

    # Task state
    task: dict                    # Task metadata + objectives + progress

    # Agent history
    agents: list[dict]            # All agents who worked on this task
    agent_summaries: list[dict]   # Completed agents' summaries
    active_agents: list[dict]     # Currently active agents

    # Knowledge
    verified_facts: list[dict]    # Facts with status='verified' or high confidence
    key_relations: list[dict]     # Entity relationships on task branch

    # Conversations (critical for handoff)
    key_conversations: list[dict] # Conversations with decisions/insights
    #   每个包含:
    #   - id, title, message_count
    #   - verification_status
    #   - key_messages: [{role, content, is_decision_point}]
    #   - summary: LLM-generated summary

    # Unresolved
    pending_objectives: list[dict]   # Objectives not yet done
    blockers: list[str]              # Known blockers
    recent_errors: list[dict]        # Recent error observations

    # Instructions
    instructions: str | None         # Handoff-specific guidance
    priority_items: list[int]        # Which objectives to tackle first

    # Branch info
    branch_name: str                 # Where to continue working
    parent_branch: str               # Task's parent branch
```

---

## 4. Conversation Cherry-Pick（对话级 Cherry-Pick）

### 4.1 设计理念

当前系统可以 cherry-pick facts 和 observations。但真正有价值的是**完整的对话上下文**——一段对话中的推理链、决策过程、工具调用序列。

```
Conversation A (task/fix-bug/agent-1)
├── msg 1: user "fix the auth bug"
├── msg 2: assistant "let me investigate..."
├── msg 3: tool_call: Read auth.py           ← 有价值
├── msg 4: tool_result: ...
├── msg 5: assistant "found the issue..."    ← 关键决策
├── msg 6: tool_call: Edit auth.py           ← 有价值
├── msg 7: assistant "fixed, let me test"
├── msg 8: tool_call: Bash pytest            ← 验证成功
├── msg 9: assistant "all tests pass"        ← 结论
└── msg 10: user "thanks"

Cherry-pick messages 3-9 → 这段完整的 debug + fix 流程
可以被提升到 task 分支，甚至 main 分支
```

### 4.2 Cherry-Pick 粒度

| 粒度 | 描述 | 用途 |
|------|------|------|
| **Full Conversation** | 整个对话 | 完整的工作流值得保留 |
| **Message Range** | 连续的消息范围 (from_seq, to_seq) | 提取特定的推理/决策片段 |
| **Decision Points** | 只提取 assistant 的关键决策消息 | 快速回顾关键判断 |
| **Tool Sequences** | 提取工具调用+结果序列 | 记录有效的操作步骤 |

### 4.3 Conversation Cherry-Pick Engine

```python
class ConversationCherryPickEngine:
    """Cherry-pick conversations or message ranges between branches."""

    async def cherry_pick_conversation(
        self,
        conversation_id: str,
        target_branch: str,
        include_messages: bool = True,
        verify: bool = False,
    ) -> dict:
        """Cherry-pick an entire conversation to a target branch.

        Steps:
        1. Copy conversation record with new branch_name
        2. Copy all messages (if include_messages)
        3. Mark source messages as cherry_picked
        4. Optionally run LLM verification
        """

    async def cherry_pick_message_range(
        self,
        conversation_id: str,
        from_sequence: int,
        to_sequence: int,
        target_branch: str,
        target_conversation_id: str | None = None,
        title: str | None = None,
    ) -> dict:
        """Cherry-pick a range of messages from a conversation.

        Creates a new conversation on target_branch containing
        only the selected message range. This preserves the
        reasoning chain while discarding noise.
        """

    async def cherry_pick_decisions(
        self,
        conversation_id: str,
        target_branch: str,
    ) -> dict:
        """Auto-extract and cherry-pick decision-point messages.

        Uses heuristics + optional LLM to identify:
        - Messages containing "I'll", "let me", "the approach is"
        - Messages after tool errors (recovery decisions)
        - Messages before successful tool calls (correct strategies)

        Returns a curated conversation with only decision points.
        """

    async def cherry_pick_to_facts(
        self,
        conversation_id: str,
        target_branch: str,
        use_llm: bool = True,
    ) -> dict:
        """Extract verified facts from a conversation.

        Unlike consolidation (which processes observations),
        this processes the full conversation content:
        1. Read all messages
        2. LLM extracts structured facts
        3. Each fact gets verification_status='verified'
        4. Facts are written to target_branch

        This is the bridge between Layer 1 (History) and Layer 2 (Memory).
        """
```

---

## 5. Knowledge Curation Pipeline（知识策展流水线）

### 5.1 The Curation Flow

```
Agent Work (on agent branch)
    │
    ▼
┌──────────────────────────────┐
│  Step 1: Agent Consolidation  │
│  observations → candidate     │
│  facts (confidence 0.7)       │
│  (already exists)             │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  Step 2: Verification Gate    │  ← NEW
│                               │
│  For each candidate fact:     │
│  • LLM-as-judge scores it    │
│  • Check against existing     │
│    verified facts (conflict?) │
│  • Score > threshold →        │
│    status = 'verified'        │
│  • Score < threshold →        │
│    status = 'invalidated'     │
│                               │
│  For key conversations:       │
│  • LLM evaluates correctness │
│  • Marks verification_status  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  Step 3: Cherry-Pick Merge    │  ← NEW
│                               │
│  Only verified items merge    │
│  to parent branch:            │
│  • verified facts             │
│  • verified conversations     │
│  • cherry-picked messages     │
│                               │
│  Unverified items stay on     │
│  the agent/task branch.       │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  Step 4: Bundle Creation      │  ← NEW
│                               │
│  Package verified knowledge   │
│  into a shareable bundle:     │
│  • facts + relations          │
│  • key conversations          │
│  • task metadata              │
│  • verification scores        │
│                               │
│  Bundle can be:               │
│  • Replayed (task-level)      │
│  • Shared (export/import)     │
│  • Used as template           │
└──────────────────────────────┘
```

### 5.2 Verification Engine

```python
class VerificationEngine:
    """LLM-powered verification for facts and conversations."""

    async def verify_fact(
        self,
        fact_id: str,
        context_branch: str | None = None,
    ) -> dict:
        """Verify a single fact using LLM-as-judge.

        Prompt structure:
        - Present the fact
        - Present source observation/conversation
        - Present any conflicting facts
        - Ask: Is this fact correct, complete, and useful?
        - Returns: score (0-1), verdict, explanation

        If score >= 0.7: mark fact as 'verified'
        If score < 0.4: mark fact as 'invalidated'
        Otherwise: keep as 'active' (needs human review)
        """

    async def verify_conversation(
        self,
        conversation_id: str,
    ) -> dict:
        """Verify a conversation's decision quality.

        Evaluates:
        - Were the right tools used?
        - Were decisions logically sound?
        - Did the outcome match the goal?
        - Were there any errors or suboptimal paths?

        Returns: verification_status, score, key_decisions[]
        """

    async def batch_verify(
        self,
        branch_name: str,
        fact_threshold: float = 0.7,
        conversation_threshold: float = 0.6,
    ) -> dict:
        """Verify all unverified items on a branch.

        Used during merge/curation to gate what gets promoted.
        """
```

---

## 6. Task-Level Replay（任务级重放）

### 6.1 设计理念

现有 replay 只能重放单个对话。Task-Level Replay 重放的是**整个任务的工作流**：

```
Task Replay = 完整的 "如何完成一类任务" 的教程

Original Task: "fix-oauth-bug"
├── Agent A (implementer)
│   ├── Conversation 1: 调查问题
│   ├── Conversation 2: 实现修复
│   └── Summary: "发现 token 刷新逻辑缺少重试..."
├── Agent B (reviewer)
│   ├── Conversation 3: 代码审查
│   └── Summary: "修复正确，建议增加超时处理..."
├── Agent C (tester)
│   └── Conversation 4: 验证测试
│
└── Merged Result
    ├── 3 verified facts
    ├── 2 key conversations (cherry-picked)
    └── Task summary
```

重放这个 task 意味着：
1. 展示完整的时间线（谁做了什么，按什么顺序）
2. 展示关键决策点（conversation 中的 cherry-picked 部分）
3. 展示最终成果（verified facts + merged knowledge）
4. 可以用不同参数重新执行（不同 model, 不同 prompt）

### 6.2 Task Replay Engine

```python
class TaskReplayEngine:
    """Replay an entire task's workflow."""

    async def build_task_replay(
        self,
        task_id: str,
        include_conversations: bool = True,
        include_observations: bool = False,
        verified_only: bool = False,
    ) -> TaskReplay:
        """Build a complete task replay.

        Returns:
            TaskReplay with full timeline, agent contributions,
            conversations, facts, and outcomes.
        """

    async def export_as_bundle(
        self,
        task_id: str,
        name: str | None = None,
        verified_only: bool = True,
    ) -> KnowledgeBundle:
        """Export a task's verified knowledge as a shareable bundle.

        Steps:
        1. Run batch_verify if not already done
        2. Collect verified facts + relations
        3. Collect verified conversations
        4. Package into KnowledgeBundle
        5. Generate share_token
        """

    async def replay_from_bundle(
        self,
        bundle_id: str,
        target_branch: str = "main",
        config: ReplayConfig | None = None,
    ) -> dict:
        """Import a knowledge bundle into a target branch.

        Can be used to:
        1. Bootstrap a new task with prior knowledge
        2. Share knowledge across projects
        3. Re-execute a task workflow with different parameters
        """

    async def compare_task_runs(
        self,
        task_id_a: str,
        task_id_b: str,
    ) -> dict:
        """Compare two task executions (e.g., original vs replay).

        Uses SemanticDiff at the task level:
        - Compare agent contributions
        - Compare decision points
        - Compare outcomes (facts produced, scores)
        """
```

### 6.3 TaskReplay 数据结构

```python
@dataclass
class TaskReplay:
    """Complete replay of a task's lifecycle."""

    task: dict                           # Task metadata

    # Timeline: ordered list of all events
    timeline: list[dict]
    # Each event:
    # {
    #   "timestamp": "...",
    #   "type": "agent_join" | "observation" | "fact" | "conversation" | "merge" | "handoff",
    #   "agent_id": "...",
    #   "summary": "...",
    #   "data": {...}
    # }

    # Agent contributions
    agents: list[dict]
    # {
    #   "agent_id": "...",
    #   "role": "...",
    #   "summary": "...",
    #   "facts_created": N,
    #   "conversations": [...]
    # }

    # Cherry-picked content
    key_conversations: list[dict]        # Verified conversations
    key_facts: list[dict]                # Verified facts

    # Outcome
    outcome: dict
    # {
    #   "status": "completed",
    #   "result_summary": "...",
    #   "total_facts_merged": N,
    #   "verification_score": 0.85,
    #   "merged_to": "main"
    # }
```

---

## 7. Sharing & Export（分享与导出）

### 7.1 Share Token 机制

```
                  ┌──────────────────┐
                  │ Knowledge Bundle  │
                  │                  │
                  │  share_token:    │
                  │  "kb_a3f8c2..."  │
                  │                  │
                  │  visibility:     │
                  │  "team"          │
                  └────────┬─────────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
         GET /bundles   MCP tool     Dashboard
         /{token}       import       "Import Bundle"
```

### 7.2 Bundle API

```
POST   /api/v1/bundles                        # Create bundle from task/branch
GET    /api/v1/bundles                         # List my bundles
GET    /api/v1/bundles/{id}                    # Get bundle details
GET    /api/v1/bundles/shared/{token}          # Access shared bundle
POST   /api/v1/bundles/{id}/import             # Import bundle to branch
POST   /api/v1/bundles/{id}/verify             # Run verification on bundle
PATCH  /api/v1/bundles/{id}/visibility         # Update visibility
DELETE /api/v1/bundles/{id}                    # Delete bundle
```

### 7.3 MCP Tools

```python
# 新增 MCP tools

tool("memory_handoff_create", {
    task_id: str,
    handoff_type: str,          # 'full' | 'partial' | 'escalation' | 'checkpoint'
    instructions: str | None,
    priority_objectives: list[int] | None,
    blockers: list[str] | None,
})

tool("memory_handoff_accept", {
    handoff_id: str,
    agent_id: str,
})

tool("memory_handoff_list", {
    task_id: str | None,
    status: str | None,         # 'pending' | 'accepted'
})

tool("memory_cherry_pick_conversation", {
    conversation_id: str,
    target_branch: str,
    from_sequence: int | None,  # partial pick
    to_sequence: int | None,
    verify: bool,               # run LLM verification
})

tool("memory_cherry_pick_decisions", {
    conversation_id: str,
    target_branch: str,
})

tool("memory_verify_branch", {
    branch_name: str,
    fact_threshold: float,      # default 0.7
})

tool("memory_bundle_create", {
    task_id: str | None,
    branch_name: str | None,
    name: str,
    verified_only: bool,        # default True
    visibility: str,            # 'private' | 'team' | 'public'
})

tool("memory_bundle_import", {
    bundle_id: str | None,
    share_token: str | None,
    target_branch: str,
})

tool("memory_task_replay", {
    task_id: str,
    verified_only: bool,
})

tool("memory_compare_tasks", {
    task_id_a: str,
    task_id_b: str,
})
```

---

## 8. End-to-End 流程示例

### 8.1 场景：三个 Agent 修 Bug，知识传递 + 策展 + 分享

```
Step 1: Create Task
────────────────────
POST /tasks
  name: "fix-oauth-token-refresh"
  objectives: [
    "Identify root cause of token refresh failure",
    "Implement fix",
    "Add regression tests"
  ]

→ Creates task + branch: task/fix-oauth-token-refresh


Step 2: Agent A Joins (Investigator)
────────────────────────────────────
POST /tasks/{id}/join
  agent_id: "agent-investigator"
  role: "investigator"
  assigned_objectives: [1]

→ Creates branch: task/fix-oauth-token-refresh/agent-investigator
→ Agent investigates, writes facts + observations
→ Conversation records the investigation process


Step 3: Agent A Gets Stuck — Escalation Handoff
────────────────────────────────────────────────
POST /handoffs
  task_id: task_id
  from_agent_id: "agent-investigator"
  handoff_type: "escalation"
  instructions: "Found the issue in token_service.py:142 but
    the fix requires understanding the OAuth2 state machine.
    Need someone with OAuth2 expertise."
  blockers: ["Unclear OAuth2 state transition after refresh failure"]

→ Consolidates agent's work
→ Creates handoff record with frozen context
→ Agent A's branch is preserved


Step 4: Agent B Accepts Handoff (Expert)
────────────────────────────────────────
POST /handoffs/{handoff_id}/accept
  agent_id: "agent-oauth-expert"

→ Creates branch: task/fix-oauth-token-refresh/agent-oauth-expert
→ Injects full handoff context (including Agent A's findings)
→ Agent B has access to:
  - Agent A's investigation facts
  - Agent A's conversation (the investigation process)
  - The specific blocker description
  - Priority objective: [1, 2]


Step 5: Agent B Fixes + Agent C Tests
──────────────────────────────────────
(Agent B implements fix, Agent C joins for testing)


Step 6: Cherry-Pick Correct Decisions
──────────────────────────────────────
POST /conversations/{agent_b_conv}/cherry-pick
  target_branch: "task/fix-oauth-token-refresh"
  from_sequence: 5      # The investigation + fix sequence
  to_sequence: 15
  verify: true

→ LLM verifies the conversation segment
→ Cherry-picked messages get is_cherry_picked=true
→ New curated conversation on task branch

POST /conversations/{agent_b_conv}/cherry-pick-decisions
  target_branch: "task/fix-oauth-token-refresh"

→ Auto-extracts decision points
→ Creates a "decisions only" conversation


Step 7: Verify & Merge
───────────────────────
POST /branches/task%2Ffix-oauth-token-refresh/verify

→ LLM-as-judge verifies all facts
→ Facts above threshold → 'verified'
→ Facts below threshold → 'invalidated'

POST /tasks/{id}/complete
  merge_to_main: true
  result_summary: "Fixed OAuth2 token refresh by adding retry
    logic with exponential backoff..."

→ Only verified facts + cherry-picked conversations merge to main
→ Unverified/invalidated items stay on task branch (archived)


Step 8: Create Bundle & Share
─────────────────────────────
POST /bundles
  task_id: task_id
  name: "OAuth2 Token Refresh Fix Playbook"
  verified_only: true
  visibility: "team"

→ Packages: 5 verified facts + 2 key conversations + task summary
→ Generates share_token: "kb_a3f8c2..."
→ Any team member can import this knowledge


Step 9: Future Agent Imports Bundle
────────────────────────────────────
POST /bundles/{bundle_id}/import
  target_branch: "main"

→ Verified facts merge into main
→ Key conversations available for search
→ Next agent working on OAuth issues gets this context automatically
```

---

## 9. 与现有系统的兼容性

### 9.1 不破坏现有接口

所有新能力都是 **增量添加**：
- 现有的 Task CRUD 完全不变
- 现有的 Branch/Merge 完全不变
- 现有的 Conversation/Message 完全不变
- 现有的 Replay/SemanticDiff 完全不变

新增的字段（verification_status, is_cherry_picked 等）全部有默认值，
不影响现有数据和查询。

### 9.2 渐进式采用

| 用法 | 不用 Phase 5 | 用 Phase 5 |
|------|-------------|-----------|
| 单 Agent | 自动 hook 捕获，main 分支 | 同左，无变化 |
| 多 Agent Task | create → join → complete → merge | 同左 + handoff + cherry-pick + verify |
| 知识分享 | 无 | bundle export/import |
| 质量保证 | Scoring engine (已有) | + Verification gate on merge |

---

## 10. 技术决策

### 10.1 为什么 Bundle 用 JSON 而不是新建 branch？

Bundle 是**可移植的**——它可以被导出为文件、通过 API 传递、跨项目导入。
Branch 是**存储级别的**——它绑定到 MatrixOne 的 DATA BRANCH 语法。

Bundle = 数据的序列化快照
Branch = 数据的活跃工作区

### 10.2 为什么 Handoff 需要独立表？

`get_task_context()` 已经可以返回 context，但 handoff 还需要：
- 交接指令（instructions）
- 阻碍列表（blockers）
- 优先级（priority_items）
- 状态追踪（pending/accepted）
- 审计追踪（谁交给了谁，什么时候）

这些是**交接语义**，不属于 task context 本身。

### 10.3 为什么 Verification 用 LLM 而不是人工？

1. 自动化：agent 工作流需要自动化的质量门
2. 可配置：threshold 可调（严格场景 0.9，宽松场景 0.5）
3. 已有基础：ScoringEngine 已经实现 LLM-as-judge
4. 降级方案：无 LLM 时给中性分数（0.5），不阻塞流程

### 10.4 Cherry-Pick 是否需要 embedding？

对 conversation-level cherry-pick：不需要。整个对话被复制。

对 message-range cherry-pick：不需要。按 sequence_num 范围复制。

对 cherry-pick-decisions（自动提取）：如果有 LLM 更好，但也可以用启发式规则：
- 包含 "I'll" / "the approach" / "decision" 的 assistant 消息
- 紧跟 error 后的 assistant 消息（错误恢复决策）
- 紧接成功 tool 调用前的 assistant 消息（正确策略）
