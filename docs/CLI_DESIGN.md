# Day1 CLI Design (MVP)

## Scope

Day1 CLI 在 Day1 一日交付中提供一条本地快速操作路径，复用现有引擎能力，覆盖最常用动作：

- `write-fact`
- `write-observation`
- `search`
- `branch create/list/switch`
- `snapshot create/list`
- `time-travel`
- `health`

同时保留已有进程包装命令：

- `api`
- `dashboard`
- `migrate`
- `test`

## Design Notes

- **入口兼容**：新增 `src/day1/cli/` 包并导出 `main()`，保持 `day1.cli:main` entrypoint 可用。
- **实现方式**：使用标准库 `argparse`（MVP 先行，避免额外依赖）；输出支持 `--format json|table`。
- **引擎复用**：CLI 直接调用 `FactEngine` / `ObservationEngine` / `SearchEngine` / `BranchManager` / `SnapshotManager`，不走 HTTP。
- **分支切换语义**：`branch switch` 仅切换当前 CLI 进程内 active branch，并提供 `--print-export` 输出 shell export 提示。
- **健康检查**：`day1 health` 访问 `/health`，供发布前快速验收。

## Example

```bash
day1 write-fact "修复 SQL 注入" --category security --format json
day1 search "SQL 注入" --search-type keyword --format table
day1 branch list --format table
day1 snapshot create --label s0-hardened
day1 health
```

