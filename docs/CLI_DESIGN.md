# Day1 CLI 工具设计

**Date**: 2026-02-25
**Idea**: 将 MCP 工具暴露为 CLI 命令,无需运行服务端

---

## 一、问题分析

### 1.1 MCP 的设计缺陷

```
┌─────────────┐               ┌─────────────┐
│  Claude Code│               │  MCP Server │
│   (Client)  │◄──── JSON-RPC ──►│   (stdio)   │
└─────────────┘               └─────────────┘
      ▲                              │
      │                              │
      └────────── 每次会话都要启动 ───┘
```

**问题**:

1. **启动开销** - 每次会话都要启动 Python 进程
2. **进程管理** - 需要管理服务器进程生命周期
3. **调试困难** - 出错时难以定位是客户端还是服务端问题
4. **资源浪费** - 长期运行的进程占用内存

### 1.2 直接 CLI 调用模式

```
┌─────────────┐
│  Claude Code│
│   (Client)  │
└─────────────┘
      │
      ▼
┌─────────────────────────────────┐
│  day1 search "用户偏好"          │
│  day1 write-fact "AI使用暗色主题" │
│  day1 list-branches              │
└─────────────────────────────────┘
```

**优点**:

1. **零启动开销** - 直接执行,无需服务进程
2. **简单调试** - 每个命令独立,容易测试
3. **Unix 哲学** - 管道、重定向等天然支持
4. **语言无关** - 任何能调用 subprocess 的语言都能用

---

## 二、CLI 工具设计

### 2.1 命令结构

```bash
# 基本格式
day1 <tool-name> <args>

# 写入
day1 write-fact "用户偏好使用暗色主题" --category preference --confidence 0.9
day1 write-observation "调用了 settings API" --tool-name api_client
day1 write-relation UserService --depends_on --Database

# 搜索
day1 search "用户偏好" --limit 10 --branch main
day1 graph-query UserService --depth 2

# 分支
day1 create-branch feature-x --parent main
day1 list-branches --status active
day1 switch-branch feature-x
day1 merge feature-x --into main --strategy auto

# 对话
day1 create-conversation "代码审查会话"
day1 add-message <conversation-id> --role user --content "请审查这段代码"
day1 list-conversations --session-id <session-id>

# 时间旅行
day1 snapshot --label "重构前"
day1 time-travel "2025-02-01T00:00:00Z" --query "API design"

# 任务
day1 create-task "实现登录功能" --type feature
day1 join-task <task-id> --agent-id agent-1
day1 task-status <task-id>
```

### 2.2 实现架构

```python
# src/day1/cli/__init__.py
"""
Day1 CLI 工具

将 MCP 工具暴露为命令行工具
"""

import sys
import json
import asyncio
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from day1.db.engine import get_session, init_db
from day1.core.fact_engine import FactEngine
from day1.core.search_engine import SearchEngine
from day1.core.branch_manager import BranchManager
# ... 其他引擎

console = Console()


@click.group()
@click.version_option("0.1.0")
@click.option("--database-url", envvar="BM_DATABASE_URL", help="Database URL")
@click.option("--branch", envvar="BM_BRANCH", default="main", help="Default branch")
@click.option("--session-id", envvar="BM_SESSION_ID", help="Session ID")
@click.option("--agent-id", envvar="BM_AGENT_ID", help="Agent ID")
@click.pass_context
def cli(ctx, database_url, branch, session_id, agent_id):
    """Day1 Memory Layer - Git-like memory for AI agents"""
    ctx.ensure_object(dict)
    ctx.obj["database_url"] = database_url
    ctx.obj["branch"] = branch
    ctx.obj["session_id"] = session_id
    ctx.obj["agent_id"] = agent_id


# ─────────────────────────────────────────────────────────────
# 写入命令
# ─────────────────────────────────────────────────────────────

@cli.command()
@click.argument("fact_text")
@click.option("--category", "-c", help="Fact category")
@click.option("--confidence", "-C", type=float, default=1.0, help="Confidence score")
@click.option("--branch", "-b", help="Branch name")
@click.pass_context
def write_fact(ctx, fact_text, category, confidence, branch):
    """Write a fact to memory"""
    async def _write():
        async for session in get_session():
            engine = FactEngine(session)
            fact = await engine.write_fact(
                fact_text=fact_text,
                category=category,
                confidence=confidence,
                session_id=ctx.obj.get("session_id"),
                branch_name=branch or ctx.obj.get("branch"),
            )
            console.print_json({
                "id": fact.id,
                "fact_text": fact.fact_text,
                "created_at": fact.created_at.isoformat(),
            })
            return fact
    asyncio.run(_write())


@cli.command()
@click.argument("summary")
@click.option("--type", "-t", default="observation",
              type=click.Choice(["tool_use", "discovery", "decision", "error", "insight"]))
@click.option("--tool-name", "-T", help="Tool name if type is tool_use")
@click.option("--branch", "-b", help="Branch name")
@click.pass_context
def write_observation(ctx, summary, type, tool_name, branch):
    """Write an observation to memory"""
    async def _write():
        async for session in get_session():
            from day1.core.observation_engine import ObservationEngine
            engine = ObservationEngine(session)
            obs = await engine.write_observation(
                observation_type=type,
                summary=summary,
                tool_name=tool_name,
                session_id=ctx.obj.get("session_id"),
                branch_name=branch or ctx.obj.get("branch"),
            )
            console.print_json({
                "id": obs.id,
                "summary": obs.summary,
                "created_at": obs.created_at.isoformat(),
            })
            return obs
    asyncio.run(_write())


# ─────────────────────────────────────────────────────────────
# 搜索命令
# ─────────────────────────────────────────────────────────────

@cli.command()
@click.argument("query")
@click.option("--limit", "-n", default=10, help="Max results")
@click.option("--search-type", "-s",
              type=click.Choice(["hybrid", "vector", "keyword"]),
              default="hybrid")
@click.option("--branch", "-b", help="Branch name")
@click.option("--format", "-f", type=click.Choice(["json", "table", "text"]),
              default="text", help="Output format")
@click.pass_context
def search(ctx, query, limit, search_type, branch, format):
    """Search memory"""
    async def _search():
        async for session in get_session():
            engine = SearchEngine(session)
            results = await engine.search(
                query=query,
                search_type=search_type,
                limit=limit,
                branch_name=branch or ctx.obj.get("branch"),
            )

            if format == "json":
                console.print_json([r.__dict__ for r in results])
            elif format == "table":
                table = Table(title=f"Search: {query}")
                table.add_column("ID", style="cyan")
                table.add_column("Fact", style="green")
                table.add_column("Score", style="yellow")
                table.add_column("Category")

                for r in results:
                    table.add_row(
                        r.id[:8],
                        r.fact_text[:50] + "..." if len(r.fact_text) > 50 else r.fact_text,
                        f"{r.score:.2f}",
                        r.category or "-",
                    )
                console.print(table)
            else:
                for r in results:
                    console.print(f"[cyan]{r.id[:8]}[/cyan] {r.fact_text}")
    asyncio.run(_search())


# ─────────────────────────────────────────────────────────────
# 分支命令
# ─────────────────────────────────────────────────────────────

@cli.group()
def branch():
    """Branch operations"""
    pass


@branch.command("create")
@click.argument("name")
@click.option("--parent", "-p", default="main", help="Parent branch")
@click.option("--description", "-d", help="Branch description")
@click.pass_context
def create_branch(ctx, name, parent, description):
    """Create a new branch"""
    async def _create():
        async for session in get_session():
            engine = BranchManager(session)
            branch = await engine.create_branch(
                branch_name=name,
                parent_branch=parent,
                description=description,
            )
            console.print(f"✅ Branch [cyan]{name}[/cyan] created")
            console.print_json({
                "name": branch.branch_name,
                "parent": branch.parent_branch,
                "created_at": branch.created_at.isoformat(),
            })
    asyncio.run(_create())


@branch.command("list")
@click.option("--status", "-s", type=click.Choice(["active", "merged", "archived"]))
@click.pass_context
def list_branches(ctx, status):
    """List all branches"""
    async def _list():
        async for session in get_session():
            engine = BranchManager(session)
            branches = await engine.list_branches(status=status)

            table = Table(title="Branches")
            table.add_column("Name", style="cyan")
            table.add_column("Parent", style="dim")
            table.add_column("Status", style="green")
            table.add_column("Description")

            for b in branches:
                table.add_row(
                    b.branch_name,
                    b.parent_branch or "-",
                    b.status,
                    b.description or "-",
                )
            console.print(table)
    asyncio.run(_list())


@branch.command("switch")
@click.argument("name")
@click.pass_context
def switch_branch(ctx, name):
    """Switch active branch (sets environment variable hint)"""
    console.print(f"export BM_BRANCH={name}")
    console.print(f"# Add to your shell profile or run:")
    console.print(f"export BM_BRANCH={name}")


# ─────────────────────────────────────────────────────────────
# 实用命令
# ─────────────────────────────────────────────────────────────

@cli.command()
@click.option("--label", "-l", help="Snapshot label")
@click.option("--branch", "-b", help="Branch name")
@click.pass_context
def snapshot(ctx, label, branch):
    """Create a point-in-time snapshot"""
    async def _snapshot():
        async for session in get_session():
            from day1.core.snapshot_manager import SnapshotManager
            engine = SnapshotManager(session)
            snap = await engine.create_snapshot(
                label=label,
                branch_name=branch or ctx.obj.get("branch"),
            )
            console.print(f"✅ Snapshot created: [cyan]{snap.id}[/cyan]")
    asyncio.run(_snapshot())


@cli.command()
@click.pass_context
def init(ctx):
    """Initialize Day1 database"""
    async def _init():
        await init_db()
        async for session in get_session():
            from day1.core.branch_manager import BranchManager
            mgr = BranchManager(session)
            await mgr.ensure_main_branch()
        console.print("✅ Day1 database initialized")
    asyncio.run(_init())


@cli.command()
@click.pass_context
def health(ctx):
    """Check Day1 health"""
    async def _check():
        try:
            await init_db()
            async for session in get_session():
                result = await session.execute("SELECT 1 as ok")
                row = result.fetchone()
                if row and row[0] == 1:
                    console.print("✅ Database: [green]OK[/green]")

                    # 检查分支
                    from day1.core.branch_manager import BranchManager
                    mgr = BranchManager(session)
                    branches = await mgr.list_branches()
                    console.print(f"✅ Branches: {len(branches)}")
                    break
        except Exception as e:
            console.print(f"❌ Error: {e}")
            raise SystemExit(1)
    asyncio.run(_check())


# ─────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────

def main():
    """CLI entry point"""
    cli()


if __name__ == "__main__":
    main()
```

### 2.3 安装方式

```bash
# 开发安装
pip install -e /path/to/day1

# CLI 自动可用
day1 --help
```

### 2.4 与 MCP 对比

| 操作 | MCP (服务端模式) | CLI (直接调用) |
|------|------------------|----------------|
| 启动 | 需要 `python -m day1.mcp.mcp_server` | 无需启动 |
| 调用 | JSON-RPC over stdio | 直接 subprocess |
| 配置 | `.claude/settings.json` | 环境变量或参数 |
| 调试 | 需要查看服务端日志 | 直接看输出 |
| 依赖 | 需要 MCP 客户端 SDK | 任何能调用进程的语言 |

---

## 三、Claude Code 集成

### 3.1 使用 CLI 替代 MCP

```json
// .claude/settings.json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [
          {
            "name": "day1-context",
            "exe": "day1",
            "args": ["search", "$DAY1_LAST_QUERY", "--limit", "5", "--format", "json"]
          }
        ]
      },
      "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "name": "day1-observation",
            "exe": "day1",
            "args": ["write-observation", "$TOOL_NAME", "--summary", "$TOOL_RESULT"]
          }
        ]
      }
    ]
  }
}
```

### 3.2 混合模式 (推荐)

```json
{
  "hooks": {
    // 简单操作用 CLI
    "SessionStart": [{"matcher": "*", "hooks": ["day1 search ..."]}],

    // 复杂操作用 MCP
    "PreToolUse": [{"matcher": "*", "hooks": ["mcp://day1"]}]
  },
  "mcpServers": {
    // 保留 MCP 用于需要状态管理的场景
    "day1": {
      "command": "python",
      "args": ["-m", "day1.mcp.mcp_server"]
    }
  }
}
```

---

## 四、实现文件

```
src/day1/
├── cli/
│   ├── __init__.py            # CLI 主入口
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── write.py           # write-fact, write-observation
│   │   ├── search.py          # search, graph-query
│   │   ├── branch.py          # create-branch, list-branches
│   │   ├── conversation.py    # create-conversation, add-message
│   │   ├── snapshot.py        # snapshot, time-travel
│   │   └── task.py            # create-task, join-task
│   └── utils.py               # 输出格式化, 错误处理
│
└── __main__.py                # day1 CLI 入口
```

---

## 五、MCP 工具到 CLI 命令的映射

| MCP Tool | CLI Command | 说明 |
|----------|-------------|------|
| `memory_write_fact` | `day1 write-fact` | 写入事实 |
| `memory_write_observation` | `day1 write-observation` | 写入观察 |
| `memory_write_relation` | `day1 write-relation` | 写入关系 |
| `memory_search` | `day1 search` | 搜索 |
| `memory_graph_query` | `day1 graph-query` | 图查询 |
| `memory_timeline` | `day1 timeline` | 时间线 |
| `memory_branch_create` | `day1 branch create` | 创建分支 |
| `memory_branch_list` | `day1 branch list` | 列出分支 |
| `memory_branch_switch` | `day1 branch switch` | 切换分支 |
| `memory_snapshot` | `day1 snapshot` | 创建快照 |
| `memory_time_travel` | `day1 time-travel` | 时间旅行 |
| `memory_task_create` | `day1 create-task` | 创建任务 |
| `memory_consolidate` | `day1 consolidate` | 整合记忆 |

---

## 六、实现优先级

### Phase 1: 核心 CLI 命令 (2-3天)

| 命令 | 描述 |
|------|------|
| `day1 init` | 初始化数据库 |
| `day1 health` | 健康检查 |
| `day1 write-fact` | 写入事实 |
| `day1 search` | 搜索 |
| `day1 branch create/list/switch` | 分支操作 |

### Phase 2: 完整命令集 (2-3天)

| 命令 | 描述 |
|------|------|
| `day1 write-observation` | 写入观察 |
| `day1 write-relation` | 写入关系 |
| `day1 snapshot/time-travel` | 快照操作 |
| `day1 create-conversation/add-message` | 对话操作 |
| `day1 create-task/join-task` | 任务操作 |

### Phase 3: Claude Code 集成 (1天)

| 文件 | 描述 |
|------|------|
| `hooks/cli_hooks.py` | CLI 版本的 hooks |
| `docs/CLI_INTEGRATION.md` | CLI 集成文档 |

---

## 七、验证标准

- [ ] `day1 search "test"` 能正常返回结果
- [ ] `day1 write-fact "test fact"` 能正常写入
- [ ] `day1 branch list` 能列出所有分支
- [ ] Claude Code 能通过 hooks 调用 CLI 工具
- [ ] CLI 输出格式支持 json/table/text
