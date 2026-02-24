# Day1 v2: 纯粹记忆层架构设计

## 重新定位：从"多 Agent 平台"到"纯粹记忆层"

---

## 0. 设计哲学的转变

### v1 的问题
v1 设计中，Day1 试图同时解决两个问题：记忆管理 + 多 Agent 编排。这导致系统既要关心 Agent 如何运行，又要管理记忆如何存储，职责不清晰。

### v2 的核心原则

**Day1 是一个纯粹的记忆层（Memory Layer），它：**

1. **不关心上层是什么** —— 可以是 1 个 Claude Code session，也可以是 20 个并行 Agent，也可以是一个 Cursor/Copilot/任意 AI agent
2. **只关心记忆的生命周期** —— 写入、检索、分支、合并、快照、时间回溯
3. **通过标准接口暴露能力** —— MCP Server + Claude Code Plugin + REST API
4. **自然覆盖所有场景** —— 单 Agent 持久记忆、多 Agent 共享记忆、记忆分支与合并 —— 都是同一套 API 的不同使用方式

### 类比

```
Day1 之于 Agent Memory ≈ Git 之于 Source Code

Git 不关心你用什么 IDE、几个人开发、什么语言。
它只管：存储、分支、合并、历史、回溯。
上层工具（GitHub, VS Code, CI/CD）自己决定怎么用它。

Day1 同理。
```

---

## 1. Claude Code 生态调研总结

### 1.1 Claude Code 原生记忆机制

```
Claude Code 的记忆是一个层级系统：

┌─ Enterprise Level ─────────────────────────────────┐
│  ~/.claude/settings.json (全局配置)                  │
│  ~/.claude/CLAUDE.md (全局用户偏好)                   │
├─ Project Level ────────────────────────────────────┤
│  ./CLAUDE.md 或 ./.claude/CLAUDE.md (项目指令)       │
│  ./.claude/settings.json (项目配置)                  │
├─ Auto Memory ──────────────────────────────────────┤
│  ~/.claude/projects/<project>/memory/               │
│  ├── MEMORY.md (索引，前200行注入 system prompt)      │
│  ├── debugging.md (按主题的详细笔记)                   │
│  └── patterns.md (Claude 自动写入)                   │
├─ Session Level ────────────────────────────────────┤
│  SQLite DB: ~/.claude/ (session_id, messages)       │
│  支持 resume (-r session_id) 和 fork (forkSession)   │
└────────────────────────────────────────────────────┘

关键限制:
- MEMORY.md 只加载前 200 行 → 记忆有"淡化"问题
- Auto Memory 是平面 Markdown，无结构化查询
- 无跨 session 的语义检索能力
- 无分支/合并概念
- 无多 Agent 记忆共享
```

### 1.2 Claude Agent SDK 的集成点

```
SDK 提供了 3 个关键集成机制：

1. MCP Server（最重要）
   - 通过 mcpServers 配置注入自定义工具
   - Agent 可以调用 MCP tools 读写记忆
   - 支持 stdio / SSE / HTTP / SDK 内嵌模式
   - 这是我们的主要集成入口

2. Hooks System
   - SessionStart: 注入历史记忆上下文
   - PostToolUse: 捕获 Agent 每次工具调用（观察记录）
   - PreCompact: 在上下文压缩前保存记忆
   - Stop: 生成 session 摘要
   - SessionEnd: 最终清理
   - 这是我们的自动记忆捕获入口

3. Plugin System
   - 打包 Hooks + MCP + Skills 为一个可安装单元
   - 通过 marketplace 分发
   - 这是我们的分发入口
```

### 1.3 claude-mem（18k stars）的经验教训

```
claude-mem 的架构:
- 5 个 Lifecycle Hooks 自动捕获
- SQLite + Chroma (vector) 双存储
- Worker Service (Bun, port 37777)
- MCP Tools: search, timeline, get_observations
- Progressive Disclosure: 分层检索节省 token

它做得好的:
✅ 完全自动，无需手动干预
✅ Token-aware 的渐进式检索
✅ Plugin 打包，一键安装
✅ 观察压缩（5000 tokens → 500 tokens）

它缺少的:
❌ 无分支/合并能力
❌ 无 PITR/时间回溯
❌ 无多 Agent 记忆隔离
❌ 无结构化知识图谱
❌ Chroma 是额外依赖，不如 MatrixOne 内置 vector + BM25
```

### 1.4 CodePilot 的参考价值

```
CodePilot 的做法:
- 封装 Claude Agent SDK 的 query() 调用
- SQLite (WAL mode) 存储 sessions 和 messages
- 自管理 session 生命周期（create, rename, archive, resume）
- 不依赖 Claude Code 原生 session 存储

关键启示:
→ 可以完全自管理 session/memory 存储
→ Agent SDK 的 session_id 可以作为 memory branch 的关联键
→ 通过 resume + forkSession 可以实现 session 分叉
→ 我们可以在 session 分叉时自动创建 memory branch
```

---

## 2. 重新设计的架构

### 2.1 整体分层

```
┌─────────────────────────────────────────────────────────────┐
│                     上层消费者（我们不关心）                      │
│  Claude Code Session  │  多个并行 Agent  │  Cursor  │  任意    │
│  (单人单 session)      │  (Agent SDK)     │  Copilot │  客户端   │
└───────────┬────────────┴────────┬─────────┴─────┬───────────┘
            │                     │               │
            ▼                     ▼               ▼
┌─────────────────────────────────────────────────────────────┐
│                   集成接口层 (Integration)                     │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Claude Code  │  │  MCP Server  │  │    REST API      │   │
│  │   Plugin     │  │  (stdio/SSE) │  │  (HTTP, 通用)     │   │
│  │  (Hooks +    │  │              │  │                  │   │
│  │   Skills)    │  │  memory_*    │  │  /api/v1/...     │   │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘   │
│         │                 │                    │             │
│         └─────────────────┼────────────────────┘             │
│                           ▼                                 │
│  ┌─────────────────────────────────────────────────────┐     │
│  │            Memory Orchestrator (核心引擎)              │     │
│  │                                                     │     │
│  │  ┌─────────────┐ ┌──────────────┐ ┌──────────────┐  │     │
│  │  │ Branch Mgr  │ │ Fact Engine  │ │ Search Engine│  │     │
│  │  │ 分支管理     │ │ 事实提取/合并  │ │ 混合检索     │  │     │
│  │  └─────────────┘ └──────────────┘ └──────────────┘  │     │
│  │  ┌─────────────┐ ┌──────────────┐ ┌──────────────┐  │     │
│  │  │ Merge Engine│ │ Trace Logger │ │ Snapshot Mgr │  │     │
│  │  │ 合并引擎    │ │ 追踪记录     │ │ 快照管理      │  │     │
│  │  └─────────────┘ └──────────────┘ └──────────────┘  │     │
│  └──────────────────────┬──────────────────────────────┘     │
│                         ▼                                   │
│  ┌─────────────────────────────────────────────────────┐     │
│  │              MatrixOne Database                      │     │
│  │                                                     │     │
│  │  main_memory (主分支)                                 │     │
│  │  ├── facts (结构化事实 + vector embedding)            │     │
│  │  ├── relations (实体关系图)                           │     │
│  │  ├── observations (工具调用观察记录)                   │     │
│  │  ├── sessions (会话追踪)                              │     │
│  │  └── branch_registry (分支注册表)                     │     │
│  │                                                     │     │
│  │  branch_<name> (按需 CLONE 的独立分支)                │     │
│  │  └── 同 schema，完全隔离的读写                        │     │
│  └─────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 核心 Data Model

```sql
-- ============================================
-- 所有分支共享相同 schema
-- main_memory 是默认分支，branch_* 通过 CLONE 创建
-- ============================================

-- 1. 事实存储（mem0 风格的结构化事实）
CREATE TABLE facts (
    id            VARCHAR(36) PRIMARY KEY,
    fact_text     TEXT NOT NULL,                    -- 事实的自然语言描述
    embedding     VECF32(1536),                     -- 向量嵌入
    category      VARCHAR(50),                      -- bug_fix, architecture, preference, pattern, etc.
    confidence    FLOAT DEFAULT 1.0,                -- 置信度
    status        ENUM('active','superseded','invalidated') DEFAULT 'active',
    source_type   VARCHAR(20),                      -- observation, manual, extraction, merge
    source_id     VARCHAR(36),                      -- 来源 ID（observation_id 等）
    parent_id     VARCHAR(36),                      -- 被取代的旧 fact ID
    session_id    VARCHAR(100),                     -- 关联的 session
    branch_name   VARCHAR(100) DEFAULT 'main',      -- 所属分支名
    metadata      JSON,                             -- 扩展字段
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_embedding USING HNSW (embedding),
    FULLTEXT INDEX idx_fact_text (fact_text)
);

-- 2. 关系图谱（mem0g 风格的实体关系）
CREATE TABLE relations (
    id              VARCHAR(36) PRIMARY KEY,
    source_entity   VARCHAR(200) NOT NULL,
    target_entity   VARCHAR(200) NOT NULL,
    relation_type   VARCHAR(100) NOT NULL,          -- depends_on, causes, fixes, implements, etc.
    properties      JSON,                           -- 关系属性
    confidence      FLOAT DEFAULT 1.0,
    valid_from      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    valid_to        TIMESTAMP NULL,                 -- NULL = 仍然有效
    session_id      VARCHAR(100),
    branch_name     VARCHAR(100) DEFAULT 'main',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_source (source_entity),
    INDEX idx_target (target_entity),
    INDEX idx_relation_type (relation_type)
);

-- 3. 观察记录（claude-mem 风格的工具调用捕获）
CREATE TABLE observations (
    id              VARCHAR(36) PRIMARY KEY,
    session_id      VARCHAR(100) NOT NULL,
    observation_type VARCHAR(30) NOT NULL,           -- tool_use, discovery, decision, error, insight
    tool_name       VARCHAR(100),                    -- Bash, Edit, Read, Write, etc.
    summary         TEXT NOT NULL,                    -- 压缩后的观察摘要
    embedding       VECF32(1536),
    raw_input       TEXT,                             -- 工具输入（可选，用于详细查看）
    raw_output      TEXT,                             -- 工具输出（可选，压缩存储）
    branch_name     VARCHAR(100) DEFAULT 'main',
    metadata        JSON,                            -- token_count, duration_ms, etc.
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_embedding USING HNSW (embedding),
    FULLTEXT INDEX idx_summary (summary),
    INDEX idx_session (session_id),
    INDEX idx_type (observation_type)
);

-- 4. 会话记录
CREATE TABLE sessions (
    session_id      VARCHAR(100) PRIMARY KEY,
    parent_session  VARCHAR(100),                    -- fork 自哪个 session
    branch_name     VARCHAR(100) DEFAULT 'main',
    project_path    VARCHAR(500),
    status          ENUM('active','completed','abandoned') DEFAULT 'active',
    summary         TEXT,                            -- session 结束时的摘要
    metadata        JSON,                            -- model, cost, turns, etc.
    started_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at        TIMESTAMP NULL
);

-- 5. 分支注册表
CREATE TABLE branch_registry (
    branch_name     VARCHAR(100) PRIMARY KEY,
    parent_branch   VARCHAR(100) DEFAULT 'main',
    description     TEXT,
    status          ENUM('active','merged','archived') DEFAULT 'active',
    forked_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    merged_at       TIMESTAMP NULL,
    merge_strategy  VARCHAR(50),                     -- cherry_pick, fast_forward, squash
    metadata        JSON
);

-- 6. 合并记录（审计追踪）
CREATE TABLE merge_history (
    id              VARCHAR(36) PRIMARY KEY,
    source_branch   VARCHAR(100) NOT NULL,
    target_branch   VARCHAR(100) NOT NULL,
    strategy        VARCHAR(50) NOT NULL,
    items_merged    JSON,                            -- [{type: 'fact', id: '...', action: 'adopt'}, ...]
    items_rejected  JSON,
    conflict_resolution JSON,                        -- 冲突如何解决
    merged_by       VARCHAR(100),                    -- 'auto', 'llm_judge', 'manual'
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 3. 三层集成接口设计

### 3.1 MCP Server —— 核心集成入口

这是最重要的接口。任何支持 MCP 的客户端（Claude Code, Claude Desktop, Cursor 等）都能直接使用。

```typescript
// MCP Server: branched-memory-server
// 通过 stdio 或 SSE 暴露以下 tools:

// ========== 基础记忆操作 ==========

// 写入一条事实
tool("memory_write_fact", {
  fact_text: string,          // "项目使用 FastAPI + SQLAlchemy 架构"
  category?: string,          // "architecture"
  confidence?: number,        // 0.9
  branch?: string,            // 默认 "main"
})

// 写入一条观察
tool("memory_write_observation", {
  observation_type: string,   // "tool_use" | "discovery" | "decision" | "error"
  summary: string,            // "执行 pytest 发现 3 个失败测试..."
  tool_name?: string,         // "Bash"
  raw_input?: string,
  raw_output?: string,
  branch?: string,
})

// 写入一条关系
tool("memory_write_relation", {
  source_entity: string,      // "AuthService"
  target_entity: string,      // "UserModel"
  relation_type: string,      // "depends_on"
  properties?: object,
  branch?: string,
})

// ========== 检索操作 ==========

// 语义搜索记忆（混合 BM25 + Vector）
tool("memory_search", {
  query: string,              // "如何修复认证相关的 bug?"
  search_type?: "hybrid" | "vector" | "keyword",  // 默认 hybrid
  branch?: string,            // 在哪个分支搜索，默认 main
  category?: string,          // 限定类别
  limit?: number,             // 默认 10
  time_range?: {after?: string, before?: string},
})

// 获取记忆的时间线
tool("memory_timeline", {
  session_id?: string,        // 某个 session 的时间线
  branch?: string,
  after?: string,
  before?: string,
  limit?: number,
})

// 图谱查询：查找与实体相关的所有关系
tool("memory_graph_query", {
  entity: string,             // "AuthService"
  relation_type?: string,     // 可选过滤
  depth?: number,             // 遍历深度，默认 1
  branch?: string,
})

// ========== 分支操作 ==========

// 创建分支（从 main 或指定分支 CLONE）
tool("memory_branch_create", {
  branch_name: string,        // "agent-001-fix-auth"
  parent_branch?: string,     // 默认 "main"
  description?: string,
})

// 列出所有分支
tool("memory_branch_list", {
  status?: "active" | "merged" | "archived",
})

// 切换当前操作的分支（后续操作默认使用该分支）
tool("memory_branch_switch", {
  branch_name: string,
})

// ========== 合并操作 ==========

// 比较两个分支的差异
tool("memory_branch_diff", {
  source_branch: string,
  target_branch: string,
  category?: string,          // 只比较某类差异
})

// 合并分支到目标分支
tool("memory_branch_merge", {
  source_branch: string,
  target_branch?: string,     // 默认 "main"
  strategy: "auto" | "cherry_pick" | "squash",
  items?: string[],           // cherry_pick 时指定 fact/observation IDs
})

// ========== 快照与回溯 ==========

// 创建快照
tool("memory_snapshot", {
  label?: string,             // "before-refactor"
  branch?: string,
})

// 列出快照
tool("memory_snapshot_list", {
  branch?: string,
})

// 回溯到某个时间点查询（不修改数据）
tool("memory_time_travel", {
  timestamp: string,          // ISO 格式
  query: string,              // 在那个时间点执行搜索
  branch?: string,
})
```

### 3.2 Claude Code Plugin —— 自动记忆捕获

通过 Hooks 自动捕获，用户无需手动操作。

```jsonc
// .claude-plugin/manifest.json
{
  "name": "branched-memory",
  "version": "1.0.0",
  "description": "Git-like branching memory system powered by MatrixOne",
  "hooks": {
    "SessionStart": [
      {
        "command": "node dist/hooks/session-start.js",
        // 注入相关历史记忆到 session 上下文
        // 返回 { systemMessage: "相关历史记忆..." }
      }
    ],
    "PostToolUse": [
      {
        "command": "node dist/hooks/post-tool-use.js",
        // 捕获每次工具调用，压缩为 observation 写入
        // 异步执行，不阻塞主流程
      }
    ],
    "PreCompact": [
      {
        "command": "node dist/hooks/pre-compact.js",
        // 在上下文压缩前，提取事实和关系写入记忆
        // 确保压缩不会丢失关键信息
      }
    ],
    "Stop": [
      {
        "command": "node dist/hooks/stop.js",
        // Agent 完成一轮回答后，生成阶段性摘要
      }
    ],
    "SessionEnd": [
      {
        "command": "node dist/hooks/session-end.js",
        // Session 结束时生成完整摘要
        // 提取最终事实和关系
      }
    ]
  },
  "mcpServers": {
    "branched-memory": {
      "command": "node",
      "args": ["dist/mcp-server.js"],
      "env": {
        "MO_HOST": "127.0.0.1",
        "MO_PORT": "6001",
        "MO_DATABASE": "main_memory"
      }
    }
  },
  "skills": [
    {
      "name": "memory-search",
      "description": "Search through project memory with natural language",
      "path": "dist/skills/memory-search.js"
    },
    {
      "name": "memory-branch",
      "description": "Manage memory branches (create, merge, diff)",
      "path": "dist/skills/memory-branch.js"
    }
  ]
}
```

### 3.3 Hook 实现详解

```typescript
// hooks/session-start.ts
// 在 session 开始时注入相关记忆

import type { SessionStartHookInput, SyncHookJSONOutput } from './types';
import { MemoryClient } from '../client';

export async function handler(input: SessionStartHookInput): Promise<SyncHookJSONOutput> {
  const client = new MemoryClient();
  
  // 1. 获取当前项目在 main 分支上的关键事实（top-k by recency + relevance）
  const facts = await client.search({
    query: '', // 空 query = 按 recency 排序
    branch: 'main',
    category: undefined, 
    limit: 20,
    search_type: 'keyword', // 快速，不用 embedding
  });
  
  // 2. 获取最近 session 的摘要
  const recentSessions = await client.getRecentSessions({ limit: 3 });
  
  // 3. 组装注入内容（控制 token 量）
  const contextParts: string[] = [];
  
  if (facts.length > 0) {
    contextParts.push('## 项目记忆（关键事实）');
    for (const fact of facts.slice(0, 15)) {
      contextParts.push(`- ${fact.fact_text} [${fact.category}]`);
    }
  }
  
  if (recentSessions.length > 0) {
    contextParts.push('\n## 最近 Session 摘要');
    for (const s of recentSessions) {
      contextParts.push(`- ${s.started_at}: ${s.summary?.slice(0, 200) || '无摘要'}`);
    }
  }
  
  // 4. 检查是否有活跃的分支
  const branches = await client.listBranches({ status: 'active' });
  if (branches.length > 1) { // > 1 因为 main 总是存在
    contextParts.push('\n## 活跃记忆分支');
    for (const b of branches.filter(b => b.branch_name !== 'main')) {
      contextParts.push(`- ${b.branch_name}: ${b.description || '无描述'}`);
    }
  }
  
  return {
    hookSpecificOutput: {
      hookEventName: 'SessionStart',
      additionalContext: contextParts.join('\n'),
    }
  };
}
```

```typescript
// hooks/post-tool-use.ts
// 异步捕获每次工具调用

import type { PostToolUseHookInput, AsyncHookJSONOutput } from './types';
import { MemoryClient } from '../client';
import { compressObservation } from '../compress';

export async function handler(input: PostToolUseHookInput): Promise<AsyncHookJSONOutput> {
  // 异步执行，不阻塞 Claude 的响应
  const client = new MemoryClient();
  
  // 压缩观察（5000 tokens → ~500 tokens）
  const summary = await compressObservation({
    tool_name: input.tool_name,
    tool_input: input.tool_input,
    tool_response: input.tool_response,
  });
  
  // 写入当前活跃分支
  await client.writeObservation({
    session_id: input.session_id,
    observation_type: 'tool_use',
    tool_name: input.tool_name,
    summary,
    raw_input: JSON.stringify(input.tool_input).slice(0, 2000),  // 截断保护
    raw_output: JSON.stringify(input.tool_response).slice(0, 2000),
  });
  
  return { async: true, asyncTimeout: 10000 };
}
```

```typescript
// hooks/pre-compact.ts
// 在上下文压缩前提取事实

import type { PreCompactHookInput, SyncHookJSONOutput } from './types';
import { MemoryClient } from '../client';
import { extractFacts, extractRelations } from '../extract';

export async function handler(input: PreCompactHookInput): Promise<SyncHookJSONOutput> {
  const client = new MemoryClient();
  
  // 读取当前 session 的 transcript
  // 使用 LLM 提取事实和关系
  const transcript = await readTranscript(input.transcript_path);
  
  // 事实提取（类 mem0 的方式）
  const facts = await extractFacts(transcript);
  for (const fact of facts) {
    // 冲突检测：与已有 facts 对比
    const existing = await client.search({
      query: fact.fact_text,
      search_type: 'vector',
      limit: 3,
    });
    
    if (existing.length > 0 && existing[0].similarity > 0.92) {
      // 高度相似 → 更新而非新增
      await client.updateFact(existing[0].id, {
        fact_text: fact.fact_text,
        confidence: Math.max(existing[0].confidence, fact.confidence),
      });
    } else {
      await client.writeFact(fact);
    }
  }
  
  // 关系提取
  const relations = await extractRelations(transcript);
  for (const rel of relations) {
    await client.writeRelation(rel);
  }
  
  return {
    systemMessage: `[Day1] 从即将压缩的上下文中提取了 ${facts.length} 条事实和 ${relations.length} 条关系。`,
  };
}
```

### 3.4 REST API —— 通用接口

为非 MCP 客户端提供 HTTP 接口（Dashboard、外部工具、CI/CD 等）。

```
POST   /api/v1/facts                   # 写入事实
GET    /api/v1/facts/search            # 搜索事实
GET    /api/v1/facts/:id               # 获取单条事实

POST   /api/v1/observations            # 写入观察
GET    /api/v1/observations/search     # 搜索观察
GET    /api/v1/observations/timeline   # 时间线

POST   /api/v1/relations               # 写入关系
GET    /api/v1/relations/graph         # 图谱查询

POST   /api/v1/branches                # 创建分支
GET    /api/v1/branches                # 列出分支
GET    /api/v1/branches/:name/diff     # 分支差异
POST   /api/v1/branches/:name/merge    # 合并分支

POST   /api/v1/snapshots               # 创建快照
GET    /api/v1/snapshots               # 列出快照
GET    /api/v1/time-travel             # 时间回溯查询
```

---

## 4. 场景覆盖：同一套 API，不同使用方式

### 场景 A：单个 Claude Code Session（最基础）

```
用户在 Claude Code 中正常工作，完全无感。

1. SessionStart Hook → 注入历史记忆
2. 用户发出指令
3. Claude 使用工具（Bash, Edit, Read...）
4. PostToolUse Hook → 自动捕获每次工具调用
5. Claude 回答完毕
6. Stop Hook → 生成阶段性摘要
7. 下次 session → SessionStart 注入上次记忆

所有操作都在 main 分支，零配置。
```

### 场景 B：单 Agent 手动创建分支（实验性开发）

```
开发者在尝试一个不确定的方案。

1. Agent 调用 memory_branch_create("experiment-new-auth")
2. 后续所有记忆写入 experiment-new-auth 分支
3. 尝试成功 → memory_branch_merge(source="experiment-new-auth", target="main")
4. 尝试失败 → 分支丢弃，main 不受影响
```

### 场景 C：多 Agent 并行（Wide Coding）

```
上层编排器（如 CodePilot 或自定义脚本）启动多个 Agent。

编排器负责:
1. 调用 memory_branch_create("agent-A-fix-auth")
2. 调用 memory_branch_create("agent-B-fix-auth")  
3. 调用 memory_branch_create("agent-C-fix-auth")

每个 Agent 的 session 连接到自己的分支:
- Agent A 的 MCP config 设置 branch="agent-A-fix-auth"
- Agent B 的 MCP config 设置 branch="agent-B-fix-auth"
- Agent C 的 MCP config 设置 branch="agent-C-fix-auth"

完成后:
4. 调用 memory_branch_diff 比较三个分支
5. 调用 memory_branch_merge(strategy="cherry_pick", items=[...])
6. 合并最佳记忆到 main

Day1 完全不知道（也不关心）有多少 Agent 在运行。
它只看到不同的分支有数据在写入。
```

### 场景 D：跨项目知识共享

```
1. 项目 A 积累了 "如何处理 OAuth 2.0" 的记忆
2. 新项目 B 启动时，memory_search 可以跨项目检索
3. 相关知识自动注入新项目的上下文

通过 metadata.project_path 区分，但搜索时可以跨越。
```

---

## 5. 分支与合并引擎（核心差异化）

### 5.1 MatrixOne 分支操作（Git4Data — 表级分支）

```sql
-- 创建分支（零拷贝，CoW 语义，表级别）
DATA BRANCH CREATE TABLE facts_agent_A FROM facts;
DATA BRANCH CREATE TABLE relations_agent_A FROM relations;
DATA BRANCH CREATE TABLE observations_agent_A FROM observations;

-- 分支表完全隔离，Agent 读写自己的分支表
-- 命名规则: {table}_{branch_name}，main 分支用原始表名

-- 行级差异比较（基于 PK）
DATA BRANCH DIFF facts_agent_A AGAINST facts;
DATA BRANCH DIFF facts_agent_A AGAINST facts OUTPUT COUNT;

-- 原生合并（两种冲突策略）
DATA BRANCH MERGE facts_agent_A INTO facts;                    -- 默认
DATA BRANCH MERGE facts_agent_A INTO facts WHEN CONFLICT SKIP;   -- 保留 target
DATA BRANCH MERGE facts_agent_A INTO facts WHEN CONFLICT ACCEPT; -- 用 source 覆盖

-- 快照（零拷贝）
CREATE SNAPSHOT sp_before_refactor FOR DATABASE branchedmind;

-- PITR 时间旅行查询
SELECT * FROM facts {AS OF TIMESTAMP '2025-01-15 10:00:00'} ORDER BY created_at DESC;
```

### 5.2 Dual-Strategy Merge Engine

```python
class MergeEngine:
    """
    双策略合并引擎:
    - native: 使用 MO DATA BRANCH MERGE (SKIP/ACCEPT 冲突策略)
    - auto/cherry_pick/squash: 应用层精细化合并 (LLM 辅助冲突解决)
    """
    
    async def diff(self, source_branch: str, target_branch: str) -> BranchDiff:
        """比较两个分支的差异"""
        
        # 获取 source 分支特有的 facts
        source_facts = await self.db.query(f"""
            SELECT f.* FROM `branch_{source_branch}`.facts f
            WHERE f.id NOT IN (
                SELECT id FROM `{target_branch}`.facts
            )
            AND f.status = 'active'
            ORDER BY f.created_at
        """)
        
        # 获取冲突的 facts（同一 parent_id 的不同更新）
        conflicts = await self.detect_conflicts(source_branch, target_branch)
        
        return BranchDiff(
            new_facts=source_facts,
            new_relations=source_relations,
            new_observations=source_observations,
            conflicts=conflicts,
        )
    
    async def merge(
        self, 
        source_branch: str, 
        target_branch: str,
        strategy: str,
        items: list[str] | None = None,
    ) -> MergeResult:
        """执行合并"""
        
        if strategy == 'cherry_pick':
            return await self._cherry_pick(source_branch, target_branch, items)
        elif strategy == 'squash':
            return await self._squash_merge(source_branch, target_branch)
        elif strategy == 'auto':
            return await self._auto_merge(source_branch, target_branch)
    
    async def _cherry_pick(self, source, target, item_ids):
        """选择性合并指定 items"""
        for item_id in item_ids:
            # 从 source 复制到 target
            await self.db.execute(f"""
                INSERT INTO `{target}`.facts 
                SELECT * FROM `branch_{source}`.facts 
                WHERE id = %s
            """, [item_id])
        
        # 记录合并历史
        await self.db.insert('merge_history', {
            'source_branch': source,
            'target_branch': target,
            'strategy': 'cherry_pick',
            'items_merged': json.dumps(item_ids),
        })
    
    async def _auto_merge(self, source, target):
        """LLM 辅助的自动合并"""
        diff = await self.diff(source, target)
        
        # 无冲突的直接合并
        for fact in diff.new_facts:
            if not any(c.involves(fact.id) for c in diff.conflicts):
                await self._cherry_pick(source, target, [fact.id])
        
        # 有冲突的让 LLM 判断
        for conflict in diff.conflicts:
            resolution = await self.llm_resolve_conflict(conflict)
            if resolution.keep == 'source':
                await self._cherry_pick(source, target, [conflict.source_id])
            elif resolution.keep == 'target':
                pass  # 保持 target 不变
            elif resolution.keep == 'both':
                # 创建一个合并后的新 fact
                merged_fact = resolution.merged_fact
                await self.db.insert(f'{target}.facts', merged_fact)
```

---

## 6. 技术栈与 MVP 实现计划

### 6.1 技术栈

```
Database:     MatrixOne (Cloud/Docker) — vecf32 + FULLTEXT INDEX + DATA BRANCH + PITR
Backend:      Python 3.11+ (FastAPI + SQLAlchemy 2.0 async + aiomysql)
Frontend:     React + Vite + React Flow + D3.js + Zustand + Tailwind CSS
MCP Server:   mcp (official Python SDK)
Plugin:       Claude Code Plugin format (.claude-plugin/)
LLM:          Claude API (事实提取, 冲突解决, 观察压缩)
Embedding:    OpenAI text-embedding-3-small 或本地模型
```

### 6.2 MVP 实现计划（72 小时 Hackathon）

```
Phase 1: 基础记忆层 (Day 1, ~20h)
├── MatrixOne Docker 部署 + Schema 创建 (3h)
├── Memory Client SDK (TypeScript) (6h)
│   ├── CRUD: facts, observations, relations, sessions
│   ├── Hybrid Search (BM25 + Vector union)
│   └── Embedding 生成
├── MCP Server 实现 (8h)
│   ├── memory_write_fact
│   ├── memory_write_observation  
│   ├── memory_search
│   ├── memory_graph_query
│   └── memory_timeline
└── 单元测试 (3h)

Phase 2: Claude Code 集成 (Day 2, ~24h)
├── Plugin 打包结构 (2h)
├── Hooks 实现 (10h)
│   ├── session-start.ts (记忆注入)
│   ├── post-tool-use.ts (观察捕获)
│   ├── pre-compact.ts (事实提取)
│   ├── stop.ts (阶段摘要)
│   └── session-end.ts (完整摘要)
├── 事实提取 + 冲突检测 (6h)
├── 观察压缩 (3h)
└── 集成测试：单 Agent 完整流程 (3h)

Phase 3: 分支差异化 (Day 3, ~24h)  
├── Branch CLONE 集成 (4h)
├── MCP 分支操作 tools (4h)
│   ├── memory_branch_create
│   ├── memory_branch_list
│   ├── memory_branch_diff
│   └── memory_branch_merge
├── Merge Engine (8h)
│   ├── diff 比较
│   ├── cherry_pick
│   └── auto merge (LLM judge)
├── Web Dashboard (6h)
│   ├── 分支树可视化
│   ├── 记忆时间线
│   └── 合并界面
└── End-to-end Demo (2h)
```

### 6.3 Demo 场景

**"三个 Agent 修同一个 Bug，记忆分支合并"**

```
准备:
- 一个有 bug 的 Python 项目（API 状态码错误）
- Day1 已安装为 Claude Code Plugin

演示:
1. 通过 Agent SDK 启动 3 个并行 Claude Code sessions
2. 每个 session 自动创建独立 memory branch
3. Dashboard 实时展示:
   - 三条分支时间线
   - 每个 Agent 提取的 facts 和 relations
   - 观察记录的差异
4. Agent 完成后，触发 merge:
   - diff 展示三个分支的差异
   - auto merge 用 LLM 判断每条 fact 的正确性
   - cherry_pick 最佳 facts 到 main
5. 启动第 4 个 session:
   - SessionStart Hook 注入合并后的 main 记忆
   - Agent 立刻获得三个前辈的"最佳经验"
   - 快速解决类似问题
```

---

## 7. 与 v1 设计的关键差异

| 维度 | v1 | v2 |
|------|----|----|
| **定位** | 多 Agent 协作平台 | 纯粹记忆层 |
| **上层感知** | 知道有几个 Agent，管理 Agent 生命周期 | 完全不关心，只看到 branch + session |
| **集成方式** | 自定义 Python SDK | MCP Server + Claude Code Plugin + REST |
| **自动化** | 手动调 API | Hooks 自动捕获，零配置 |
| **兼容性** | 仅支持自研 Agent Loop | Claude Code, Agent SDK, Cursor, 任意 MCP 客户端 |
| **Backend** | Python FastAPI | Python 3.11+ (FastAPI + SQLAlchemy 2.0 async) |
| **数据库** | 同 | MatrixOne（不变，核心优势）|
| **分发** | 需要部署整个平台 | `npm install` 或 Plugin marketplace |

---

## 8. 未来扩展

1. **Claude Code Plugin Marketplace** —— 一键安装
2. **实时 Pub/Sub** —— 分支变更事件通知
3. **记忆市场** —— 跨项目/跨团队共享有价值的记忆
4. **可视化记忆图谱** —— D3.js 交互式知识图谱
5. **记忆质量评分** —— 自动评估 fact 的可靠性
6. **多模型支持** —— 不仅 Claude，也支持 GPT, Gemini 等
7. **记忆压缩策略** —— 长期记忆自动精炼和淘汰
8. **Dashboard 可视化增强** —— 更丰富的 MO PITR 时间旅行集成、知识图谱可视化
