# Testing Strategy

> Three-layer testing model: surface contract smoke, real acceptance flows, and unit tests — ensuring every endpoint, tool, and command works correctly at every level.

## Testing Philosophy

Day1's testing strategy reflects a key insight: **a memory system must be tested end-to-end**, because the value lives in the full path from agent action to durable knowledge retrieval. Unit tests verify individual engine logic, but only E2E tests can confirm that the integration surfaces (MCP, API, Hooks, CLI) correctly route through the 26 engines to MatrixOne and back.

```
┌──────────────────────────────────────────────────────────────┐
│                  TESTING PYRAMID                               │
│                                                                │
│                    ┌──────┐                                    │
│                   /  E2E   \       Real acceptance flows       │
│                  / (real)   \      Valid data, full chains     │
│                 /────────────\     API+CLI+MCP agent scenarios │
│                / E2E (surface) \   Every endpoint smoked       │
│               /  Contract tests  \ Schema validation, 4xx     │
│              /────────────────────\                             │
│             /     Unit Tests       \   Engine logic, edge      │
│            /  (pytest, async)       \  cases, error paths      │
│           /──────────────────────────\                          │
│          /     Integration Tests      \  DB + embedding +      │
│         /  (MatrixOne, real queries)   \ branch operations     │
│        /──────────────────────────────────\                     │
│                                                                │
│  Width = coverage breadth                                      │
│  Height = confidence per test                                  │
└──────────────────────────────────────────────────────────────┘
```

---

## Layer 1: E2E Surface Coverage

### Purpose

Prove that **every** API endpoint, CLI command, and MCP tool is reachable and handles inputs safely — including invalid inputs. This is a contract/smoke layer, not a correctness layer.

### How It Works

```
┌──────────────────────────────────────────────────────────────┐
│               SURFACE COVERAGE FLOW                            │
│                                                                │
│  scripts/e2e_surface.py                                        │
│       │                                                        │
│       ├──→ Enumerate surfaces dynamically                      │
│       │    ├── FastAPI routes (introspect app.routes)          │
│       │    ├── CLI leaf commands (introspect Click groups)     │
│       │    └── MCP tools (introspect tool registry)           │
│       │                                                        │
│       ├──→ Start local API server (ephemeral port)            │
│       │                                                        │
│       ├──→ For each API route:                                 │
│       │    ├── Send synthetic/empty body (POST/PUT/PATCH)     │
│       │    ├── Send placeholder IDs (GET with path params)    │
│       │    ├── Classify: pass / warn / fail                   │
│       │    └── Warn only if matches strict baseline           │
│       │                                                        │
│       ├──→ For each CLI command:                               │
│       │    ├── Run with --help                                │
│       │    └── Classify: pass / fail                          │
│       │                                                        │
│       ├──→ For each MCP tool:                                  │
│       │    ├── Invoke via HTTP streamable_http (/mcp)         │
│       │    ├── Use schema-derived inputs + seeded real IDs    │
│       │    └── Classify: pass / warn / fail                   │
│       │                                                        │
│       └──→ Generate report: e2e_surface_latest_report.json    │
└──────────────────────────────────────────────────────────────┘
```

### Result Classification

| Status | Meaning | Action |
|---|---|---|
| `pass` | Endpoint returned success for smoke input | No action needed |
| `warn` | Expected 4xx matching strict baseline | Documented in E2E_TEST_METHODS.md |
| `fail` | Transport error, HTTP 5xx, or unexpected 4xx | **Blocks release** until fixed |

### Strict Baseline Policy

Surface `warn` is allowed **only** when it matches the explicit baseline in `scripts/e2e_surface.py`. This prevents "warn drift" — if a previously-passing endpoint starts returning 4xx, it fails rather than silently becoming a warn.

Warn categories (all expected and documented):

| Category | Count | Example |
|---|---|---|
| Schema validation (422) | ~25 | `POST /facts` with empty body |
| Not found (404) | ~25 | `GET /facts/{dummy-uuid}` |
| Precondition (400) | ~3 | `POST /tasks/{id}/consolidate` without prerequisites |
| Branch not found (404) | ~5 | `GET /branches/{placeholder}/diff` |

### Latest Results

| Section | Total | Pass | Warn | Fail |
|---|---:|---:|---:|---:|
| `api_surface` | 96 | 38 | 58 | 0 |
| `cli_surface` | 29 | 29 | 0 | 0 |
| `mcp_surface` | 53 | 53 | 0 | 0 |
| **Totals** | **178** | **120** | **58** | **0** |

---

## Layer 2: E2E Real Acceptance

### Purpose

Prove that **real business flows** work end-to-end with valid data. This is the correctness layer — it verifies that the full chain from client through integration surface through engine to database works as expected.

### Scenarios

```
┌──────────────────────────────────────────────────────────────┐
│            REAL ACCEPTANCE SCENARIOS                            │
│                                                                │
│  1. API Core Chain                                             │
│     Create branch → Write fact → Search fact →                │
│     Write observation → Write relation → Graph query →        │
│     Create snapshot → Time-travel query                       │
│                                                                │
│  2. API Deep Agent Scenario (103 steps)                        │
│     Create session → Create task → Create branch →            │
│     Join agent → Write facts → Create conversation →          │
│     Post messages → Fork conversation → Cherry-pick →         │
│     Create replay → Evaluate conversation →                    │
│     Create template → Instantiate template →                   │
│     Verify facts → Create handoff → Create bundle →           │
│     Import bundle → Branch merge → Branch diff →              │
│     Analytics overview → Trends → Session analytics →         │
│     Complete agent → Complete task → Clean up                  │
│                                                                │
│  3. CLI Real Chain                                             │
│     Create branch → Write fact → Search → Write observation → │
│     Timeline → Create snapshot → Time-travel → Health check   │
│                                                                │
│  4. MCP Real Chain                                             │
│     Create branch → Switch branch → Write memory →            │
│     Search memory → Create snapshot → List snapshots →        │
│     Restore snapshot → List branches                          │
│                                                                │
│  5. MCP Exhaustive Chain                                       │
│     All 8 MCP tools + extended operations:                    │
│     Write → Search → Branch create → Branch switch →          │
│     Snapshot → Snapshot list → Restore → Branch list          │
│     + conversation, message, task, template, handoff,         │
│       bundle, replay, fork flows via MCP-seeded REST calls    │
│                                                                │
│  All MCP scenarios run over HTTP streamable_http (/mcp)       │
│  using the official Python MCP client (not stdio, not         │
│  direct dispatch)                                              │
└──────────────────────────────────────────────────────────────┘
```

### DB Verification Manifest

After a real acceptance run, the system produces a **DB verification manifest** (`e2e_real_acceptance_db_manifest.json`) containing exact IDs for every created resource. This enables:

1. **Post-run SQL verification**: Run the provided SQL queries to confirm rows exist in the database
2. **Branch isolation verification**: Confirm facts/messages are on the correct branches
3. **Cascade verification**: Confirm that task → agent → conversation → message relationships are intact
4. **Cleanup verification**: Confirm that deleted branches are properly archived

### Latest Real Acceptance Results

| Section | Total | Pass | Warn | Fail |
|---|---:|---:|---:|---:|
| `api_real` | 2 | 2 | 0 | 0 |
| `api_agent_real` | 103 | 103 | 0 | 0 |
| `cli_real` | 11 | 11 | 0 | 0 |
| `mcp_real` | 11 | 11 | 0 | 0 |
| `mcp_exhaustive` | 53 | 53 | 0 | 0 |
| **Totals** | **180** | **180** | **0** | **0** |

API valid-input route coverage: **96/96** (100%)

---

## Layer 3: Unit Tests

### Engine-Level Testing

Each of the 26 engines has corresponding unit tests using `pytest` with async support:

```
┌──────────────────────────────────────────────────────────────┐
│              UNIT TEST ARCHITECTURE                             │
│                                                                │
│  pytest + pytest-asyncio                                       │
│       │                                                        │
│       ├──→ Fixtures                                            │
│       │    ├── async_session: Test DB session (rollback)       │
│       │    ├── mock_embedder: MockEmbeddingProvider            │
│       │    ├── test_branch: Ephemeral branch for isolation     │
│       │    └── seeded_data: Pre-populated facts/conversations  │
│       │                                                        │
│       ├──→ Engine Tests (per engine)                           │
│       │    ├── Happy path: normal operations                   │
│       │    ├── Edge cases: empty input, max lengths            │
│       │    ├── Error paths: missing data, invalid state        │
│       │    └── Concurrency: parallel writes, race conditions   │
│       │                                                        │
│       ├──→ Integration Tests (cross-engine)                    │
│       │    ├── Consolidation pipeline: obs → fact → merge      │
│       │    ├── Branch lifecycle: create → write → merge        │
│       │    └── Search after write: embedding + retrieval       │
│       │                                                        │
│       └──→ Hook Tests                                          │
│            ├── Input/output contract per hook                  │
│            ├── Graceful degradation (DB unavailable)           │
│            └── Silent failure (never blocks Claude Code)       │
└──────────────────────────────────────────────────────────────┘
```

### Test Environment

| Setting | Value | Reason |
|---|---|---|
| `BM_EMBEDDING_PROVIDER` | `mock` | Deterministic, no external API calls |
| `BM_RATE_LIMIT` | `0` | Disable rate limiting for test speed |
| `BM_LOG_LEVEL` | `CRITICAL` | Quiet output during test runs |
| `BM_DATABASE_URL` | MatrixOne (local) | Real database for integration tests |
| `BM_TEST_DATABASE_URL` | MatrixOne (local) | Separate URL for test isolation |

### Key Test Categories

| Category | What It Tests | Example |
|---|---|---|
| Write path | Fact/observation/message creation | Write fact → verify in DB |
| Search path | Hybrid search (BM25 + vector + temporal) | Write + search → verify ranking |
| Branch ops | DATA BRANCH CREATE/DIFF/MERGE | Create branch → write → diff → merge |
| Consolidation | Three-level consolidation pipeline | Observations → session consolidation → facts |
| Verification | LLM-as-judge + heuristic fallback | Verify fact → check score dimensions |
| Snapshot/PITR | Point-in-time recovery | Snapshot → modify → restore → verify |
| Template lifecycle | Create → version → instantiate → deprecate | Full template lifecycle |
| Conversation replay | Fork → replay → compare | Fork at message → replay → semantic diff |
| Knowledge bundles | Export → import → verify | Create bundle → import to new branch |
| Handoff protocol | Create → verify → accept | Handoff with verified facts |

---

## Testing Principles

### 1. Dynamic Surface Enumeration

Tests **never** use a hardcoded list of endpoints. Instead, they introspect the running application to discover all routes, commands, and tools. This prevents the classic problem of adding a new endpoint but forgetting to add its test.

```
API routes  → introspect FastAPI app.routes
CLI commands → introspect Click group/subgroup
MCP tools   → introspect MCP tool registry
```

### 2. No Silent Fallbacks

MCP tests **must** run over HTTP `streamable_http` transport via the `/mcp` endpoint. They are explicitly forbidden from falling back to:
- Direct Python dispatch (bypasses transport layer)
- `stdio` transport (different protocol path)

This ensures the MCP transport layer is actually tested.

### 3. Strict Baseline for Warnings

Every `warn` in surface mode must:
1. Match a specific entry in the strict baseline in `scripts/e2e_surface.py`
2. Be individually documented in `docs/E2E_TEST_METHODS.md`
3. Have a clear explanation of why the warn is expected

If a warn stops matching its baseline (status code changes, error message changes), it becomes a `fail`.

### 4. DB-Level Verification

Real acceptance tests produce SQL queries that can be run directly against the database to verify:
- Resources were actually persisted (not just cached)
- Branch isolation is working (facts on correct branches)
- Cascade relationships are intact (task → agent → conversation → message)
- Temporal ordering is correct (sequence numbers, timestamps)

### 5. Graceful Degradation Testing

Hooks and LLM-dependent engines (VerificationEngine, ScoringEngine) must be tested in degraded mode:
- **Hooks**: DB unavailable → return empty, never block
- **VerificationEngine**: LLM unavailable → heuristic fallback scores
- **ScoringEngine**: LLM unavailable → neutral 0.5 scores
- **EmbeddingProvider**: API unavailable → write succeeds without embedding

---

## CI/CD Integration

```
┌──────────────────────────────────────────────────────────────┐
│              CI/CD TESTING PIPELINE                             │
│                                                                │
│  On Pull Request:                                              │
│  ├── Unit tests (pytest, mock embedder)                       │
│  ├── Lint + type check                                        │
│  └── Surface coverage (fast, synthetic inputs)                │
│                                                                │
│  On Merge to Main:                                             │
│  ├── All PR checks                                            │
│  ├── Real acceptance (full agent scenario)                    │
│  ├── DB verification manifest check                           │
│  └── Report preservation (JSON artifacts)                     │
│                                                                │
│  On Release:                                                   │
│  ├── All merge checks                                         │
│  ├── --real-only acceptance run                               │
│  ├── DB manifest SQL verification                             │
│  └── Sign-off: 0 failures, all warns baselined                │
└──────────────────────────────────────────────────────────────┘
```

### Release Gate

A release is blocked if:
- Any `fail` in surface or real sections
- Any `warn` not in the strict baseline
- API valid-input route coverage < 100%
- MCP not tested via HTTP streamable_http
- DB manifest verification fails

---

## Artifacts

| Artifact | Path | Purpose |
|---|---|---|
| Surface report | `docs/e2e_surface_latest_report.json` | Machine-readable surface coverage |
| Real acceptance report | `docs/e2e_real_acceptance_latest.json` | Valid-input acceptance results |
| DB manifest | `docs/e2e_real_acceptance_db_manifest.json` | SQL-verifiable resource IDs |
| Warn explanations | `docs/E2E_TEST_METHODS.md` | Human-readable warn documentation |
| Acceptance guide | `docs/E2E_REAL_ACCEPTANCE.md` | How to run and verify acceptance |

---

## Discussion

1. **Test data cleanup**: Should E2E tests clean up their branches/facts, or leave them for inspection? Currently left for DB manifest verification.
2. **Performance benchmarks**: Should we add latency assertions (e.g., search < 100ms, write < 50ms)?
3. **Chaos testing**: Simulate MatrixOne failures during branch operations — how does the system recover?
4. **Load testing**: Concurrent agent scenarios — how many simultaneous branch operations before degradation?
5. **Embedding drift testing**: When switching embedding providers, how to validate that search quality is maintained?
6. **Hook timing**: Should we assert that hooks complete within a time budget (e.g., < 500ms)?
7. **Snapshot size testing**: At what branch size does snapshot/restore become prohibitively slow?
