# memory — Day1 记忆

MCP 配置（`.mcp.json`）：
```json
{ "mcpServers": { "day1": { "type": "http", "url": "http://127.0.0.1:9903/mcp" } } }
```

工作时用以下工具维护跨 session 上下文。自然语言写入，自然语言搜索。

---

## 写入记忆

```
memory_write(
  text="发生了什么（简洁描述）",
  context="为什么 / 怎么做 / 结果是什么（自由叙述）",
  file_context="src/相关文件.py"   # 可选
)
```

**何时写入**：学到新约束、遇到 bug、做了架构决策、完成一个阶段。

---

## 搜索记忆

```
memory_search(query="自然语言查询")
memory_search(query="authentication bug", file_context="src/auth.py")
```

**何时搜索**：开始新任务前、遇到熟悉问题时。

---

## 分支隔离（实验前使用）

```
memory_branch_create(branch_name="exp/my-feature", description="试验新方案")
memory_branch_switch(branch_name="exp/my-feature")

# 实验结束后切回
memory_branch_switch(branch_name="main")

# 查看所有分支
memory_branch_list()
```

---

## 快照（高风险操作前使用）

```
memory_snapshot(label="before-refactor")

# 查看快照
memory_snapshot_list()

# 恢复
memory_restore(snapshot_id="...")
```
