# Day1 一日交付实施计划

**日期**：2026-02-25  
**范围**：后端核心引擎 + API + CLI + Dashboard + SDK  
**目标**：在 1 天内完成关键安全加固、交付最小可用 CLI，并为后续能力（OTEL、启动脚本、知识图谱、REST SDK）打好补丁基础。所有改动在完成后必须跑通回归测试。

---

## 1. 战术优先级

1. **后端安全与一致性**：修补 SQL 注入、补齐事务回滚、给分支归档加锁，避免把新增功能搭在不安全的数据层之上。  
2. **CLI 最小切片**：把现有 MCP 工具映射成 CLI 命令，解锁更快的迭代入口。  
3. **可观察性与启动体验**：准备 OTEL 采集骨架与一键启动脚本，确保新用户 5 分钟内可体验。  
4. **知识图谱与 SDK 的前置工作**：定义 API/组件/类型占位，确保 Day2 能直接实现可视化与 SDK。  
5. **测试闭环**：安全/性能/内存/端到端测试全部跑通，发现问题立即回到对应步骤处理。

---

## 2. 关键修复任务（先完成）

| 任务 | 描述 | 交付与验证 |
|------|------|------------|
| SQL 注入修复 | `src/day1/core/analytics_engine.py` 改为使用绑定参数，禁止 f-string 直接拼接 `branch_name` 等输入。 | 编写/更新单元测试 + 运行 `curl -X GET "http://localhost:8000/analytics/trends?branch_name='; DROP TABLE messages; --"`，确认返回 400 且数据库完好。 |
| 事务回滚 | 在 `branch_manager.py`、`branch_topology_engine.py`、`conversation_cherry_pick.py` 等所有写路径添加 `try/except/finally`，抛错时 `rollback + close`。 | 为每个写路径新增 `pytest.mark.asyncio` 用例，使用无效输入触发异常并断言数据库无脏数据。 |
| 分支归档加锁 | `branch_topology_engine.apply_auto_archive` 使用 `SELECT ... FOR UPDATE SKIP LOCKED` 或数据库锁，确保多 worker 时不会重复归档。 | 压测脚本同时触发 2 个归档协程，确认只有一份成功且状态一致。 |

> ⚠️ 完成以上三项并通过测试后，才能继续下面的功能迭代。

---

## 3. 一日时间分块

| 时间段 | 名称 | 内容 |
|--------|------|------|
| 09:00-11:00 | **S0 后端加固** | 完成表 2 的三大修复，更新数据层回归测试。 |
| 11:00-14:00 | **S1 CLI MVP** | 建立 `src/day1/cli` 包结构，落地 `write-fact`、`write-observation`、`search`、`branch create/list/switch`、`snapshot` 等命令，确保与引擎复用；完成 Rich/Click 输出和配置参数。 |
| 14:00-16:00 | **S2 可观察与启动骨架** | 编写 `src/day1/otel/` 内的 collector/exporter 框架与 LangGraph/AutoGen helper，占位核心类；同步创建 `scripts/start.sh`、`scripts/check_db.py`，支持一键启动/健康检查。 |
| 16:00-18:00 | **S3 知识图谱 + SDK 占位** | API 新增 `GET /relations/graph`、`GET /facts/{id}/related`；Dashboard 添加 `KnowledgeGraph`、`CrossReferencePanel` 等组件骨架与 `React Flow` 集成点；在 `src/day1/sdk/` 下放置 `Day1Client` 与类型定义，以及 `examples/simple_rest.py`。 |
| 18:00-20:00 | **S4 测试与文档收口** | 执行安全/性能/内存/CLI 端到端测试，更新 README/CLI_DESIGN/architecture 等相关文档，整理发布说明。 |

---

## 4. 交付物与文件清单

### 新增文件

- `src/day1/cli/__init__.py`、`commands/*.py`、`main.py`：CLI 命令与工具函数。  
- `src/day1/otel/__init__.py`、`collector.py`、`server.py`、`instrumentation/{langgraph,autogen}.py`。  
- `scripts/start.sh`、`scripts/check_db.py`。  
- `dashboard/src/components/{KnowledgeGraph.tsx,CrossReferencePanel.tsx,RelatedContent.tsx}`。  
- `src/day1/sdk/{__init__.py,client.py,types.py}` 与 `examples/{otel/langgraph.py,simple_rest.py}`。

### 修改文件

- `src/day1/core/analytics_engine.py`、`branch_manager.py`、`branch_topology_engine.py`、`conversation_cherry_pick.py`。  
- `src/day1/api/routes/{facts.py,relations.py}`（新增图谱 API）。  
- `dashboard/src/{api/client.ts,types/schema.ts,App.tsx,components/FactDetail.tsx}`（接入图谱/交叉引用）。  
- `docs/CLI_DESIGN.md`、`docs/architecture.md`、`docs/mcp_tools.md`（对齐 CLI/SDK/OTEL 变化）。

---

## 5. 测试矩阵

| 类别 | 操作 | 预期 |
|------|------|------|
| 安全 | SQL 注入、XSS Payload `curl`、CSRF/Headers 校验 | 所有请求返回 400/422，数据库无异常。 |
| 事务 | 异常分支创建、错误 Cherry Pick | 捕获自定义异常，数据库状态回滚。 |
| 并发 | 两个归档 worker 并行执行 | 仅一条记录被归档，其余保持 active。 |
| CLI | `day1 search`, `day1 write-fact`, `day1 branch list/create/switch`, `day1 snapshot/time-travel` | 返回值与直接调用 API 相同；支持 `--format json/table`。 |
| 可观察性 | LangGraph/AutoGen 示例把 trace 写入 collector | 转换出的 conversations/messages 正确入库。 |
| 启动 | `bash scripts/start.sh` / `bash scripts/start.sh api` | 5 分钟内可用；`check_db.py` 返回 OK。 |
| Dashboard | 图谱视图渲染、节点交互、交叉引用面板 | 无内存泄漏；React DevTools Profiler 无重复渲染。 |
| SDK | `Day1Client.write_fact/search`、`examples/simple_rest.py` | 成功写入/查询；异常时抛出 HTTP 错误并附带上下文。 |

---

## 6. 发布与回滚

1. 完成 S4 测试后，记录版本号、生成变更日志。  
2. 打标签前运行 `pytest`, `uv run scripts/check_db.py`, `day1 health`。  
3. 如生产发现问题：  
   - CLI/SDK 层回滚到上一发布包；  
   - 数据库相关问题使用最新 snapshot 恢复；  
   - Dashboard 回滚前需要清除浏览器缓存。

---

## 7. 后续关注

- 继续扩展 CLI（批量导入、模板分支操作）。  
- 为 OTEL Collector 增加链路采样与高可用部署脚本。  
- 图谱组件接入权限控制与 server-side pagination。  
- SDK 补充同步版本与 TypedDict/ Pydantic schema。
