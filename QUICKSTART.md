# Day1 Quickstart Guide

## Status

Day1 core delivery is implemented:

- Backend hardening (security / rollback / concurrency)
- CLI MVP
- REST API + Dashboard
- MCP server (50+ tools)
- Strict E2E (surface/contract) + real acceptance (valid-input) flows

---

## 方式一：Docker Compose (推荐)

**最简单的启动方式，一条命令启动所有服务**

### 前置要求

```bash
# 安装 Docker Desktop 或 Docker Engine
docker --version
docker compose version
```

### 启动

```bash
cd /path/to/day1

# 启动所有服务 (数据库 + API + Dashboard)
docker compose up -d

# 查看服务状态
docker compose ps
```

### 访问

| 服务 | 地址 | 说明 |
|------|------|------|
| Dashboard | http://localhost:9904 | 前端界面 |
| API | http://localhost:9903/api/v1 | REST API |
| API Docs | http://localhost:9903/docs | Swagger 文档 |

### 停止

```bash
# 停止所有服务
docker compose down

# 停止并删除数据（清空数据库）
docker compose down -v
```

### CLI 使用

```bash
# 健康检查
docker compose exec api uv run day1 health

# 写入事实
docker compose exec api uv run day1 write-fact "测试事实" --category test

# 搜索
docker compose exec api uv run day1 search "测试"

# 分支操作
docker compose exec api uv run day1 branch create demo/test --parent main
docker compose exec api uv run day1 branch list

# 快照
docker compose exec api uv run day1 snapshot create --label "测试前"
docker compose exec api uv run day1 snapshot list

# JSON 格式输出
docker compose exec api uv run day1 health --format json
```

---

## 方式二：本地开发

**需要 Python 3.11+、Node.js 22+、MatrixOne**

### 1. 启动数据库

```bash
# 使用 Docker 运行 MatrixOne（推荐）
docker run -d --name day1-mo -p 6001:6001 \
  -e MYSQL_ROOT_PASSWORD=111 \
  matrixorigin/matrixone:latest

# 等待启动（约 10 秒）
docker logs -f day1-mo  # 看到 "MO migration done" 后 Ctrl+C
```

### 2. 安装依赖

```bash
# Python 依赖
uv sync --all-extras

# 复制环境变量
cp .env.example .env
# 编辑 .env 配置数据库 URL 和 API 密钥

# Node.js 依赖
npm --prefix dashboard install
```

### 3. 检查数据库

```bash
uv run scripts/check_db.py
```

### 4. 启动服务

```bash
# 终端 A - 启动 API
uv run uvicorn day1.api.app:app --host 127.0.0.1 --port 8000 --reload

# 终端 B - 启动 Dashboard
cd dashboard && npm run dev
```

访问：http://localhost:5173

### 5. CLI 测试

```bash
uv run day1 health
uv run day1 branch create demo/local --parent main
uv run day1 write-fact "本地开发测试" --category test
uv run day1 search "本地"
```

### 6. 使用启动脚本（可选）

```bash
# 一键启动 API + Dashboard
bash scripts/start.sh all

# 单独启动 API
bash scripts/start.sh api

# 单独启动 Dashboard
bash scripts/start.sh dashboard
```

---

## MCP 使用

### Docker Compose 环境

在 Claude Code 中配置（`.claude/settings.json`）：

```json
{
  "mcpServers": {
    "day1": {
      "command": "docker",
      "args": [
        "compose", "exec", "-T", "api",
        "uv", "run", "python", "-m", "day1.mcp.mcp_server"
      ]
    }
  }
}
```

### 本地开发环境

```bash
uv run python -m day1.mcp.mcp_server
```

在 Claude Code 中验证：输入 `/mcp` 应该看到 `day1` 服务器和 50+ 工具。

---

## Claude Hooks (自动捕获)

如果使用 Claude Code 的 repo hooks，`.claude/settings.json` 可自动捕获：

- `SessionStart`
- `UserPromptSubmit`
- `PreToolUse`
- `PostToolUse`
- `Stop`
- `PreCompact`
- `SessionEnd`

---

## 实际验收测试

模拟真实 agent + user 交互：

```bash
export BM_DATABASE_URL='mysql+aiomysql://root:111@127.0.0.1:6001/day1'
export BM_EMBEDDING_PROVIDER=mock BM_RATE_LIMIT=0 BM_LOG_LEVEL=CRITICAL

uv run python scripts/e2e_surface.py --real-only --output docs/e2e_real_acceptance_latest.json
```

---

## 严格表面测试

包含负向/合成输入检查：

```bash
uv run python scripts/e2e_surface.py --output docs/e2e_surface_latest_report.json
```

---

## 常用 CLI 命令

### 分支操作

```bash
day1 branch create <name> --parent main
day1 branch list
day1 branch switch <name>
```

### 写入

```bash
day1 write-fact "文本" --category preference
day1 write-observation "调用了 API" --tool-name http_client
```

### 搜索

```bash
day1 search "查询" --search-type keyword
day1 search "查询" --search-type hybrid
day1 search "查询" --search-type vector
```

### 快照

```bash
day1 snapshot create --label "快照名称"
day1 snapshot list
day1 time-travel 2099-01-01T00:00:00Z
```

---

## 故障排查

### Docker Compose

| 问题 | 解决方案 |
|------|----------|
| 端口冲突 | 检查 6001/9903/9904 端口占用 |
| API 无法访问 | `docker compose logs api` |
| Dashboard 空白 | `docker compose logs dashboard` |
| 数据库连接失败 | 确保 MatrixOne 容器已启动 |

### 本地开发

| 问题 | 解决方案 |
|------|----------|
| DB 无法连接 | 运行 `uv run scripts/check_db.py` |
| API 健康检查失败 | 确保 uvicorn 正在运行 |
| MCP 客户端看不到工具 | 用 `uv run python -m day1.mcp.mcp_server` 启动 |
| Dashboard 构建失败 | 运行 `npm --prefix dashboard install` |

---

## 相关文档

- `README.md` - 高层次设置 + 本地使用
- `docs/mcp_tools.md` - 工具参考
- `docs/E2E_REAL_ACCEPTANCE.md` - 有效输入本地验证
- `docs/E2E_TEST_METHODS.md` - 严格表面/契约方法论
- `CLAUDE.md` - 仓库特定的 Claude Code 指令
