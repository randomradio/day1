# Infrastructure

> EmbeddingProvider, LLMClient, database engine, configuration — the foundation services.

## EmbeddingProvider

**Source**: `src/day1/core/embedding.py`

### Design Rationale

Embeddings enable semantic search and similarity computation. The EmbeddingProvider is designed as a pluggable abstraction with three implementations:

```
┌──────────────────────────────────────────────────┐
│              EMBEDDING ARCHITECTURE                │
│                                                    │
│  ┌────────────────────────────────┐               │
│  │     EmbeddingProvider (ABC)    │               │
│  │  embed(text) → list[float]    │               │
│  │  embed_batch(texts) → list    │               │
│  └──────────┬─────────────────────┘               │
│             │                                      │
│    ┌────────┼──────────┐                          │
│    │        │          │                          │
│    ▼        ▼          ▼                          │
│  OpenAI   Doubao     Mock                         │
│  1536d    1024d      128d (random)                │
│  $0.02/M  varies     $0 (testing)                 │
│                                                    │
│  Factory: get_embedding_provider()                │
│  Configured via: BM_EMBEDDING_PROVIDER env var    │
└──────────────────────────────────────────────────┘
```

### Non-Blocking Principle

Embeddings are **enrichment, not requirements**:
- Every write engine catches embedding errors and logs a warning
- The record is saved with `embedding = NULL`
- Search degrades to keyword-only when embeddings are missing
- This means the system is fully functional with `BM_EMBEDDING_PROVIDER=mock`

### Helper Functions

```python
embedding_to_vecf32(vec: list[float]) -> str   # Python list → MatrixOne vecf32 string
vecf32_to_embedding(vec_str: str) -> list[float]  # MatrixOne vecf32 → Python list
cosine_similarity(a: list[float], b: list[float]) -> float  # In-memory similarity
```

---

## LLMClient

**Source**: `src/day1/core/llm.py`

### Design Rationale

Only two engines (ScoringEngine, VerificationEngine) need LLM access. The LLM client is:
- **Optional**: System works fully without it (heuristic fallback)
- **OpenAI-compatible**: Works with any OpenAI API-compatible endpoint
- **Structured output**: Supports JSON schema for reliable parsing

### Integration Pattern

```python
# LLM is lazily initialized and optional
def get_llm_client() -> LLMClient | None:
    if not settings.llm_api_key:
        return None  # No LLM configured — engines will use heuristics
    return create_client(settings.llm_api_key, settings.llm_base_url)
```

### Entry Points

Only two engines call the LLM:

| Engine | Method | Purpose |
|---|---|---|
| VerificationEngine | `_call_fact_verifier()` | Evaluate fact quality |
| ScoringEngine | `_call_llm_judge()` | Score conversation quality |

---

## Database Engine

**Source**: `src/day1/db/engine.py`

### Initialization Sequence

```
init_db()
    │
    ├──→ Create AsyncEngine (SQLAlchemy 2.0 + aiomysql)
    │       └──→ Connection URL: mysql+aiomysql://user:pass@host:port/db
    │
    ├──→ Create all tables (Base.metadata.create_all)
    │       └──→ 15+ tables defined in models.py
    │
    ├──→ Create FULLTEXT indexes
    │       └──→ CREATE FULLTEXT INDEX ft_memories ON memories(text, context)
    │
    └──→ Create async session factory
```

### Connection Pattern

```python
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency injection: yields a DB session per request."""
    async with _session_factory() as session:
        yield session
```

Every API route and engine receives a session via this dependency.

---

## Configuration

**Source**: `src/day1/config.py`

### Environment Variables

All configuration uses the `BM_` prefix:

| Variable | Default | Purpose |
|---|---|---|
| `BM_DATABASE_URL` | `mysql+aiomysql://root:111@localhost:6001/day1` | MatrixOne connection |
| `BM_EMBEDDING_PROVIDER` | `openai` | Embedding provider: openai, doubao, mock |
| `BM_OPENAI_API_KEY` | (empty) | OpenAI API key for embeddings |
| `BM_EMBEDDING_DIMENSIONS` | `1536` | Embedding vector dimensions |
| `BM_LLM_API_KEY` | (empty) | LLM API key (for scoring/verification) |
| `BM_LLM_BASE_URL` | (empty) | LLM API base URL |
| `BM_API_KEY` | (empty) | API authentication key (empty = open access) |
| `BM_RATE_LIMIT` | `60` | Requests per minute per IP |
| `BM_HOST` | `127.0.0.1` | Server host |
| `BM_PORT` | `8000` | Server port |
| `BM_LOG_LEVEL` | `INFO` | Logging level |
| `BM_BRANCH` | `main` | Default active branch |
| `BM_TASK_ID` | (empty) | Task context for hooks |
| `BM_AGENT_ID` | (empty) | Agent context for hooks |
| `BM_PARENT_SESSION` | (empty) | Parent session for context handoff |

### Development Mode

When `BM_API_KEY` is empty, the API runs in open-access mode — no authentication required. This is intended for local development only.

When `BM_EMBEDDING_PROVIDER=mock`, a mock embedding provider generates random vectors. This avoids API costs during testing but disables meaningful semantic search.

---

## Discussion

1. **Embedding migration**: Switching from OpenAI to another provider means all existing embeddings are incompatible. How to handle migration?
2. **Connection pooling**: What pool size is optimal for concurrent agent access?
3. **Config validation**: Currently minimal validation. Should we enforce that production deployments have real API keys?
4. **Secret management**: API keys in environment variables — should we support vault integration?
5. **Database migrations**: Currently uses `create_all()` which doesn't handle schema evolution. Need Alembic?
