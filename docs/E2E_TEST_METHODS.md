# E2E Test Methods and Latest Coverage Results

## Strict Policy (No Bypass)

- API / CLI / MCP E2E coverage must be executed strictly; no manual skipping of endpoints/tools is allowed.
- The runner must enumerate the current code surface dynamically (FastAPI routes, CLI leaf commands, MCP tools) and execute every item.
- Surface `warn` is allowed only when it matches the explicit strict baseline in `scripts/e2e_surface.py` (route/tool + status + message fragments). Any unexpected `4xx` becomes `fail`.
- Real scenarios are mandatory and must include API/CLI/MCP valid write-read flows; API must additionally run the deep real-agent dialogue scenario (`api_agent_real`).
- Any `fail` (transport error, unexpected `4xx`, or HTTP `5xx`) blocks release until fixed and rerun.

## Purpose

- Record a repeatable end-to-end test method for API / CLI / MCP coverage.
- Preserve the latest executed coverage results and warn explanations for release review.
- Provide a stable reference for future regression checks.
- Clarify that this document covers **surface/contract + combined E2E methodology**, while valid-input release acceptance is documented separately in `docs/E2E_REAL_ACCEPTANCE.md`.

## Scope

- `API` surface coverage: enumerate all FastAPI route/method pairs and smoke each one with synthetic inputs.
- `CLI` surface coverage: enumerate all CLI leaf commands and run command/help smoke.
- `MCP` surface coverage: enumerate all MCP tools and invoke each tool through MCP dispatch with schema-derived inputs (plus seeded real IDs for downstream tools).
- Real scenarios: API core chain, API deep agent dialogue/task chain, CLI real chain, MCP real chain.

## Entry Points

- Script: `scripts/e2e_surface.py`
- Latest report (machine-readable): `docs/e2e_surface_latest_report.json`
- Real acceptance (valid-input only) report: `docs/e2e_real_acceptance_latest.json`
- Real acceptance DB verification manifest: `docs/e2e_real_acceptance_db_manifest.json`

## Environment and Preconditions

- MatrixOne is running and reachable (local runs use `127.0.0.1:6001`).
- Set explicit DB URLs for both runtime and test flows when validating locally (`BM_DATABASE_URL`, `BM_TEST_DATABASE_URL`).
- For deterministic local E2E smoke, set `BM_EMBEDDING_PROVIDER=mock` and `BM_RATE_LIMIT=0`.
- For quieter output during report generation, set `BM_LOG_LEVEL=CRITICAL`.

## Recommended Command

```bash
export BM_DATABASE_URL='mysql+aiomysql://root:111@127.0.0.1:6001/day1'
export BM_TEST_DATABASE_URL='mysql+aiomysql://root:111@127.0.0.1:6001/day1'
export BM_EMBEDDING_PROVIDER=mock BM_RATE_LIMIT=0 BM_LOG_LEVEL=CRITICAL
uv run python scripts/e2e_surface.py --output docs/e2e_surface_latest_report.json
```

## Result Classification

- `pass`: endpoint/tool returned success for the smoke input or real scenario step.
- `warn`: only for surface mode, and only when the response matches the explicit strict baseline.
- `fail`: transport/protocol failure, HTTP `5xx`, or any unexpected `4xx`; must be fixed before release.

## Latest Preserved Run

- Generated at: `2026-02-26T04:49:05Z`
- Base URL: `http://127.0.0.1:8000`
- API log artifact: `/tmp/day1-e2e-api-1v6o9si9.log`

| Section | Total | Pass | Warn | Fail |
|---|---:|---:|---:|---:|
| `api_surface` | 96 | 38 | 58 | 0 |
| `api_real` | 2 | 2 | 0 | 0 |
| `api_agent_real` | 103 | 103 | 0 | 0 |
| `cli_surface` | 15 | 15 | 0 | 0 |
| `cli_real` | 11 | 11 | 0 | 0 |
| `mcp_surface` | 53 | 53 | 0 | 0 |
| `mcp_real` | 11 | 11 | 0 | 0 |
| `totals` | 291 | 233 | 58 | 0 |

## API Warn Explanations (All, Strict-Baselined)

All API warns below are expected **only** because they match the strict surface baseline in `scripts/e2e_surface.py`. Any status/message drift will fail the run.

| # | Route | HTTP | Why Warn Is Expected |
|---:|---|---:|---|
| 1 | `POST /api/v1/branches` | 422 | Surface smoke intentionally sends empty or partial bodies for mutation endpoints to verify schema validation returns 422 (not 500). |
| 2 | `POST /api/v1/branches/curated` | 422 | Surface smoke intentionally sends empty or partial bodies for mutation endpoints to verify schema validation returns 422 (not 500). |
| 3 | `POST /api/v1/branches/validate-name` | 422 | Surface smoke intentionally sends empty or partial bodies for mutation endpoints to verify schema validation returns 422 (not 500). |
| 4 | `DELETE /api/v1/branches/{branch_name:path}` | 404 | Surface smoke uses a placeholder branch name that is intentionally not created; controlled 404 confirms branch-not-found error mapping. |
| 5 | `GET /api/v1/branches/{branch_name:path}/diff` | 404 | Surface smoke uses a placeholder branch name that is intentionally not created; controlled 404 confirms branch-not-found error mapping. |
| 6 | `GET /api/v1/branches/{branch_name:path}/diff/native` | 404 | Surface smoke uses a placeholder branch name that is intentionally not created; controlled 404 confirms branch-not-found error mapping. |
| 7 | `GET /api/v1/branches/{branch_name:path}/diff/native/count` | 404 | Surface smoke uses a placeholder branch name that is intentionally not created; controlled 404 confirms branch-not-found error mapping. |
| 8 | `POST /api/v1/branches/{branch_name:path}/enrich` | 404 | Surface smoke uses a placeholder branch name that is intentionally not created; controlled 404 confirms branch-not-found error mapping. |
| 9 | `POST /api/v1/branches/{branch_name:path}/merge` | 404 | Surface smoke uses a placeholder branch name that is intentionally not created; controlled 404 confirms branch-not-found error mapping. |
| 10 | `GET /api/v1/branches/{branch_name:path}/stats` | 404 | Surface smoke uses a placeholder branch name that is intentionally not created; controlled 404 confirms branch-not-found error mapping. |
| 11 | `POST /api/v1/bundles` | 422 | Surface smoke intentionally sends empty or partial bodies for mutation endpoints to verify schema validation returns 422 (not 500). |
| 12 | `GET /api/v1/bundles/{bundle_id}` | 404 | Surface smoke intentionally references non-existent resources (dummy UUIDs/placeholders) to verify stable not-found handling and error mapping. |
| 13 | `GET /api/v1/bundles/{bundle_id}/export` | 404 | Surface smoke intentionally references non-existent resources (dummy UUIDs/placeholders) to verify stable not-found handling and error mapping. |
| 14 | `POST /api/v1/bundles/{bundle_id}/import` | 422 | Surface smoke intentionally sends empty or partial bodies for mutation endpoints to verify schema validation returns 422 (not 500). |
| 15 | `GET /api/v1/conversations/{conv_a}/semantic-diff/{conv_b}` | 404 | Surface smoke intentionally references placeholder conversation IDs; semantic diff resolves to a controlled not-found/no-message response. |
| 16 | `GET /api/v1/conversations/{conversation_id}` | 404 | Surface smoke intentionally references non-existent resources (dummy UUIDs/placeholders) to verify stable not-found handling and error mapping. |
| 17 | `POST /api/v1/conversations/{conversation_id}/cherry-pick` | 422 | Surface smoke intentionally sends empty or partial bodies for mutation endpoints to verify schema validation returns 422 (not 500). |
| 18 | `POST /api/v1/conversations/{conversation_id}/complete` | 404 | Surface smoke intentionally references non-existent resources (dummy UUIDs/placeholders) to verify stable not-found handling and error mapping. |
| 19 | `POST /api/v1/conversations/{conversation_id}/evaluate` | 404 | Surface smoke intentionally references non-existent resources (dummy UUIDs/placeholders) to verify stable not-found handling and error mapping. |
| 20 | `POST /api/v1/conversations/{conversation_id}/fork` | 422 | Surface smoke intentionally sends empty or partial bodies for mutation endpoints to verify schema validation returns 422 (not 500). |
| 21 | `POST /api/v1/conversations/{conversation_id}/messages` | 422 | Surface smoke intentionally sends empty or partial bodies for mutation endpoints to verify schema validation returns 422 (not 500). |
| 22 | `POST /api/v1/conversations/{conversation_id}/messages/batch` | 422 | Surface smoke intentionally sends empty or partial bodies for mutation endpoints to verify schema validation returns 422 (not 500). |
| 23 | `POST /api/v1/conversations/{conversation_id}/replay` | 422 | Surface smoke intentionally sends empty or partial bodies for mutation endpoints to verify schema validation returns 422 (not 500). |
| 24 | `POST /api/v1/facts` | 422 | Surface smoke intentionally sends empty or partial bodies for mutation endpoints to verify schema validation returns 422 (not 500). |
| 25 | `POST /api/v1/facts/search` | 422 | Surface smoke intentionally sends empty or partial bodies for mutation endpoints to verify schema validation returns 422 (not 500). |
| 26 | `GET /api/v1/facts/{fact_id}` | 404 | Surface smoke intentionally references non-existent resources (dummy UUIDs/placeholders) to verify stable not-found handling and error mapping. |
| 27 | `PATCH /api/v1/facts/{fact_id}` | 404 | Surface smoke intentionally references non-existent resources (dummy UUIDs/placeholders) to verify stable not-found handling and error mapping. |
| 28 | `GET /api/v1/facts/{fact_id}/related` | 404 | Surface smoke intentionally references non-existent resources (dummy UUIDs/placeholders) to verify stable not-found handling and error mapping. |
| 29 | `GET /api/v1/facts/{fact_id}/verification` | 404 | Surface smoke intentionally references non-existent resources (dummy UUIDs/placeholders) to verify stable not-found handling and error mapping. |
| 30 | `POST /api/v1/facts/{fact_id}/verify` | 404 | Surface smoke intentionally references non-existent resources (dummy UUIDs/placeholders) to verify stable not-found handling and error mapping. |
| 31 | `POST /api/v1/handoffs` | 422 | Surface smoke intentionally sends empty or partial bodies for mutation endpoints to verify schema validation returns 422 (not 500). |
| 32 | `GET /api/v1/handoffs/{handoff_id}` | 404 | Surface smoke intentionally references non-existent resources (dummy UUIDs/placeholders) to verify stable not-found handling and error mapping. |
| 33 | `GET /api/v1/messages/{message_id}` | 404 | Surface smoke intentionally references non-existent resources (dummy UUIDs/placeholders) to verify stable not-found handling and error mapping. |
| 34 | `POST /api/v1/observations` | 422 | Surface smoke intentionally sends empty or partial bodies for mutation endpoints to verify schema validation returns 422 (not 500). |
| 35 | `POST /api/v1/relations` | 422 | Surface smoke intentionally sends empty or partial bodies for mutation endpoints to verify schema validation returns 422 (not 500). |
| 36 | `POST /api/v1/replays/{replay_id}/complete` | 404 | Surface smoke intentionally references non-existent resources (dummy UUIDs/placeholders) to verify stable not-found handling and error mapping. |
| 37 | `GET /api/v1/replays/{replay_id}/context` | 404 | Surface smoke intentionally references non-existent resources (dummy UUIDs/placeholders) to verify stable not-found handling and error mapping. |
| 38 | `GET /api/v1/replays/{replay_id}/diff` | 404 | Surface smoke intentionally references non-existent resources (dummy UUIDs/placeholders) to verify stable not-found handling and error mapping. |
| 39 | `GET /api/v1/replays/{replay_id}/semantic-diff` | 404 | Surface smoke intentionally references non-existent resources (dummy UUIDs/placeholders) to verify stable not-found handling and error mapping. |
| 40 | `POST /api/v1/scores` | 422 | Surface smoke intentionally sends empty or partial bodies for mutation endpoints to verify schema validation returns 422 (not 500). |
| 41 | `GET /api/v1/sessions/{session_id}` | 404 | Surface smoke intentionally references non-existent resources (dummy UUIDs/placeholders) to verify stable not-found handling and error mapping. |
| 42 | `GET /api/v1/sessions/{session_id}/context` | 404 | Surface smoke intentionally references non-existent resources (dummy UUIDs/placeholders) to verify stable not-found handling and error mapping. |
| 43 | `GET /api/v1/snapshots/{snapshot_id}` | 404 | Surface smoke intentionally references non-existent resources (dummy UUIDs/placeholders) to verify stable not-found handling and error mapping. |
| 44 | `POST /api/v1/tasks` | 422 | Surface smoke intentionally sends empty or partial bodies for mutation endpoints to verify schema validation returns 422 (not 500). |
| 45 | `GET /api/v1/tasks/{task_id}` | 404 | Surface smoke intentionally references non-existent resources (dummy UUIDs/placeholders) to verify stable not-found handling and error mapping. |
| 46 | `POST /api/v1/tasks/{task_id}/agents/{agent_id}/complete` | 404 | Surface smoke intentionally references non-existent resources (dummy UUIDs/placeholders) to verify stable not-found handling and error mapping. |
| 47 | `POST /api/v1/tasks/{task_id}/complete` | 404 | Surface smoke intentionally references non-existent resources (dummy UUIDs/placeholders) to verify stable not-found handling and error mapping. |
| 48 | `POST /api/v1/tasks/{task_id}/consolidate` | 400 | Surface smoke omits required consolidation preconditions on purpose; the endpoint should reject with a controlled 400 guard-rail error. |
| 49 | `POST /api/v1/tasks/{task_id}/join` | 422 | Surface smoke intentionally sends empty or partial bodies for mutation endpoints to verify schema validation returns 422 (not 500). |
| 50 | `PATCH /api/v1/tasks/{task_id}/objectives/{objective_id}` | 422 | Surface smoke intentionally sends empty or partial bodies for mutation endpoints to verify schema validation returns 422 (not 500). |
| 51 | `POST /api/v1/templates` | 422 | Surface smoke intentionally sends empty or partial bodies for mutation endpoints to verify schema validation returns 422 (not 500). |
| 52 | `GET /api/v1/templates/{name}` | 404 | Surface smoke intentionally references non-existent resources (dummy UUIDs/placeholders) to verify stable not-found handling and error mapping. |
| 53 | `POST /api/v1/templates/{name}/deprecate` | 404 | Surface smoke intentionally references non-existent resources (dummy UUIDs/placeholders) to verify stable not-found handling and error mapping. |
| 54 | `POST /api/v1/templates/{name}/instantiate` | 422 | Surface smoke intentionally sends empty or partial bodies for mutation endpoints to verify schema validation returns 422 (not 500). |
| 55 | `POST /api/v1/templates/{name}/update` | 422 | Surface smoke intentionally sends empty or partial bodies for mutation endpoints to verify schema validation returns 422 (not 500). |
| 56 | `POST /api/v1/time-travel` | 422 | Surface smoke intentionally sends empty or partial bodies for mutation endpoints to verify schema validation returns 422 (not 500). |
| 57 | `POST /api/v1/verification/batch` | 422 | Surface smoke intentionally sends empty or partial bodies for mutation endpoints to verify schema validation returns 422 (not 500). |
| 58 | `POST /api/v1/verification/merge-gate` | 422 | Surface smoke intentionally sends empty or partial bodies for mutation endpoints to verify schema validation returns 422 (not 500). |

## MCP Surface Warnings

- Latest strict run has **no MCP surface warnings**.

## Important Distinction: Surface Warnings vs Real E2E

- `surface` mode proves every endpoint/tool is reachable and safely handles invalid/synthetic inputs without server-side failure.
- `real` mode proves end-to-end business flows work with valid data (API core chain, API deep agent scenario, CLI chain, MCP chain).
- `negative surface` (`field missing`, `not found`, etc.) is **not** the real acceptance pass criterion. Use `docs/E2E_REAL_ACCEPTANCE.md` and `docs/e2e_real_acceptance_latest.json` for release-style validation.
- Both are required; neither replaces the other.

## Latest Fixes Confirmed by E2E

- `time-travel` branch isolation fix (`SnapshotManager.time_travel_query`) verified by API and CLI real chains.
- Native branch diff/count routes now return controlled `404` for missing native branch tables instead of `500` (and surface baseline now also covers branch-not-found placeholder paths).
- `aiomysql` short-lived process cleanup issue (`Event loop is closed` on shutdown) fixed via explicit DB/session cleanup in CLI/API/MCP/script entrypoints.
- `/api/v1/messages/search` route-shadowing bug fixed by declaring the static search route before `/messages/{message_id}`.
- Branch-name path-param support for slash-containing branch names (e.g. `task/...`) fixed via `{branch_name:path}` on relevant API routes.
- API conversation creation now registers `sessions` rows idempotently, enabling `sessions/*` and `analytics/sessions/*` real E2E checks.
