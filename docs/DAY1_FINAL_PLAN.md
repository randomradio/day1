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

---

## 8. 执行标记（2026-02-26）

> 对照“Day1 一日交付实施计划”的实际执行结果，供发布前复核。

### 8.1 战术优先级（第1节）

- [x] 后端安全与一致性：已完成 SQL 注入修复、事务回滚补强、归档并发互斥修复与验证。
- [x] CLI 最小切片：已完成 CLI MVP（写入/搜索/分支/快照/时光回溯/健康检查）。
- [x] 可观察性与启动体验：已完成 OTEL collector 骨架与 `scripts/start.sh` / `scripts/check_db.py`。
- [x] 知识图谱与 SDK 前置：已完成图谱 API、Dashboard 占位组件、REST SDK 占位与示例。
- [x] 测试闭环：已执行全量 `pytest` 与矩阵关键项联调；发现问题已回到对应步骤修复。

### 8.2 关键修复任务（第2节）

- [x] SQL 注入修复
  - 验证：`curl` 注入 `branch_name='; DROP TABLE messages; --` 返回 `400`，错误为 `Invalid branch name format.`
  - 数据库核对：`messages` 表仍存在。

- [x] 事务回滚
  - 验证：后端加固用例已覆盖（异常写路径 rollback），全量回归通过。

- [x] 分支归档加锁
  - 验证：并发归档测试通过（仅一条归档成功，状态一致）。
  - 备注：针对 MatrixOne 版本对 `SKIP LOCKED` 兼容性问题已实现 fallback。

### 8.3 时间分块执行状态（第3节）

- [x] S0 后端加固（完成）
- [x] S1 CLI MVP（完成）
- [x] S2 可观察与启动骨架（完成）
- [x] S3 知识图谱 + SDK 占位（完成）
- [x] S4 测试与文档收口（完成，含后续补测与修复）

### 8.4 文件清单对照（第4节）

- [x] CLI / OTEL / 启动脚本 / 图谱组件 / SDK / examples 新增文件已按清单落地。
- [x] 文档 `CLI_DESIGN/architecture/mcp_tools` 已更新。
- [x] 清单外的额外修改（收口修复）：
  - `scripts/e2e_surface.py`（API/CLI/MCP 全端点枚举 + 真实链路 E2E 报告脚本）
  - `src/day1/core/snapshot_manager.py`（修复 `time-travel` 分支隔离）
  - `tests/test_core/test_snapshot.py`（新增分支隔离回归测试）
  - `src/day1/db/engine.py`、`src/day1/api/app.py`、`src/day1/mcp/mcp_server.py`、`src/day1/cli/commands/common.py`、`scripts/check_db.py`（修复短生命周期进程 `aiomysql` 连接清理）
  - `dashboard/src/components/BranchTopologyPanel.tsx`（移除未使用导入，恢复构建通过）

### 8.5 测试矩阵执行记录（第5节）

- [x] 安全：通过
  - SQL 注入 `curl` 返回 `400`；数据库表完好。
  - XSS/CSRF 浏览器侧专项未做独立自动化验证（当前以 API 参数/头校验和既有回归为主）。

- [x] 事务：通过
  - 后端加固测试覆盖异常写路径，断言无脏数据。

- [x] 并发：通过
  - 归档并发压测/测试用例通过。

- [x] CLI：通过
  - `search/write-fact/write-observation/branch/snapshot/time-travel/health` 实测通过。
  - `search` 结果已与 API 对照。

- [x] 可观察性：通过
  - OTEL collector 启动、示例上报、`/recent` 查询通过。

- [x] 启动：通过（终端烟测）
  - `bash scripts/start.sh api` 可启动。
  - `uv run scripts/check_db.py` 返回 `OK`。
  - MCP HTTP `/mcp` 可用（挂载于 API，同端口）。

- [x] Dashboard：通过（构建）
  - `npm ci` / `npm run build` 通过。
  - 浏览器交互与 Profiler 项未在当前终端环境完成。

- [x] SDK：通过
  - `examples/simple_rest.py` 与 `Day1Client.write_fact/search` 已实测成功。

- [x] API / CLI / MCP 全端点覆盖（新增收口项）
  - 使用 `scripts/e2e_surface.py` 自动枚举并执行 surface smoke + real-chain。
  - 严格模式（2026-02-26，已启用 surface warn 白名单基线）：
    - `api_surface`: `96`（`38` pass / `58` warn / `0` fail）
    - `api_real`: `2`（`2` pass / `0` fail）
    - `api_agent_real`: `103`（真实 agent 对话/任务/回放/评分/验证/handoff/bundle/template/分支操作联调，`103` pass / `0` fail）
    - `cli_surface`: `29`（`29` pass / `0` fail）
    - `cli_real`: `11`（`11` pass / `0` fail，含 `day1 health`）
    - `mcp_surface`: `53`（`53` pass / `0` warn / `0` fail，使用真实 ID 级联调用，HTTP `streamable_http`）
    - `mcp_real`: `11`（`11` pass / `0` fail，HTTP `streamable_http`）
    - 总计：`305`（`247` pass / `58` warn / `0` fail）
  - 说明：当前 `warn` 全部来自 `api_surface`，且均为严格白名单中的预期 4xx（空 body 校验 / dummy 资源 not-found / 受控 400 业务前置条件）。任何未匹配白名单的 4xx 会直接判定为 `fail`。
  - [x] Real Acceptance（有效输入验收，独立于 negative surface）
    - 使用：`scripts/e2e_surface.py --real-only`
    - 结果（2026-02-26）：`180` / `180` pass，`0 warn`，`0 fail`
    - API 有效输入路由覆盖：`96/96`（全部覆盖）
    - 产物：`docs/e2e_real_acceptance_latest.json`、`docs/e2e_real_acceptance_db_manifest.json`、`docs/E2E_REAL_ACCEPTANCE.md`（含可直接执行 SQL 验证示例）

### 8.6 发布前检查（第6节）

- [x] `pytest`（全量）通过：`167 passed`
- [x] `pytest`（全量）复验通过：`169 passed`（MCP HTTP 迁移后）
- [x] `uv run scripts/check_db.py` 通过
- [x] `day1 health` 通过
- [ ] 打版本标签（待提交后执行）
  - 说明：当前工作区存在未提交改动；直接打 tag 会指向旧 `HEAD`，不包含本次变更。

### 8.7 本轮收口修复备注

- [x] 修复 `time-travel` 跨分支结果混入（`SnapshotManager.time_travel_query` 增加 `branch_name` 过滤）。
- [x] 修复短生命周期 CLI / 脚本 / API / MCP 的 `aiomysql Connection.__del__ -> Event loop is closed` 清理问题（统一增加 `close_db()` 并在入口边界调用）。
- [x] 验证 `aiomysql` 清理修复有效：`day1` CLI、`scripts/check_db.py`、MCP 单次调用、API 受控关闭未再观察到 `Event loop is closed` 析构告警。
- [x] 修复 API 路由遮蔽：`/api/v1/messages/search` 不再被 `/api/v1/messages/{message_id}` 抢先匹配。
- [x] 修复带 `/` 的分支名在路径参数中的可用性：相关路由改为 `{branch_name:path}`，真实任务分支场景（如 `task/.../agent`）联调通过。
- [x] 修复 API 会话写入链路缺失 `sessions` 表记录：创建 conversation 时幂等注册 session，`sessions/*` 与 `analytics/sessions/*` 真实 E2E 通过。
- [x] 强化 `scripts/e2e_surface.py`：加入严格 surface warn 基线校验（未知 4xx -> fail）与深度 `api_agent_real` 场景。
- [x] MCP 传输方式收敛：由 `stdio` 收敛为 HTTP `streamable_http`（挂载 `FastAPI /mcp`，不保留双接口）。
- [x] 验证 MCP HTTP：本地 `/mcp`、Docker `/mcp`、Claude Code `claude mcp add --transport http` 均已实测成功。
- [ ] 残余非阻塞问题：代码中存在多处 `datetime.utcnow()` 的弃用告警（不影响当前交付与测试结果）。
