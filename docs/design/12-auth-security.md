# Authentication & Security

> Current implementation, isolation model, and security considerations.

## Current Authentication Model

```
┌──────────────────────────────────────────────────────┐
│                   AUTH ARCHITECTURE                    │
│                                                        │
│  Request arrives                                       │
│       │                                                │
│       ├──→ Is path /health? → ALLOW (no auth)         │
│       │                                                │
│       ├──→ Is path /mcp/*? → ALLOW (session-based)    │
│       │                                                │
│       ├──→ Is BM_API_KEY set?                         │
│       │       │                                        │
│       │       ├──→ No → ALLOW ALL (dev mode)          │
│       │       │                                        │
│       │       └──→ Yes → Check Authorization header   │
│       │               │                                │
│       │               ├──→ Bearer token matches → ALLOW│
│       │               │                                │
│       │               └──→ Missing/invalid → 401      │
│       │                                                │
│       ▼                                                │
│  Rate Limit Check (per IP, 60/min window)              │
│       │                                                │
│       ├──→ Under limit → PROCEED                      │
│       │                                                │
│       └──→ Over limit → 429 Too Many Requests         │
└──────────────────────────────────────────────────────┘
```

### Bearer Token Authentication

**Implementation**: `src/day1/api/app.py`

```python
# Optional Bearer token — if BM_API_KEY is set, all requests must include it
security = HTTPBearer(auto_error=False)

async def verify_api_key(credentials = Depends(security)):
    if not settings.api_key:
        return  # Dev mode: no auth required
    if not credentials or credentials.credentials != settings.api_key:
        raise HTTPException(401, "Invalid API key")
```

### Rate Limiting

- **Window**: 60 seconds sliding window
- **Default limit**: 60 requests per IP per window
- **Configurable**: via `BM_RATE_LIMIT` environment variable
- **Exemptions**: `/health` and `/mcp/*` paths are not rate-limited
- **Implementation**: In-memory per-IP counter with timestamp tracking

### CORS

- **Current**: Allow all origins (`*`), all methods, all headers
- **Appropriate for**: Local development, single-team deployments
- **Not appropriate for**: Production multi-tenant deployments

---

## Isolation Model

Day1 provides isolation at multiple levels:

### Branch-Level Isolation (Current)

```
┌──────────────────────────────────────────────────────┐
│                 BRANCH ISOLATION                       │
│                                                        │
│  Agent A ──→ branch: task/fix-auth/agent_a            │
│  Agent B ──→ branch: task/fix-auth/agent_b            │
│                                                        │
│  Each branch = separate physical tables               │
│  (facts_task_fix_auth_agent_a ≠                       │
│   facts_task_fix_auth_agent_b)                         │
│                                                        │
│  Queries on branch A CANNOT see branch B data          │
│  (different tables, not row-level filtering)           │
│                                                        │
│  Merging requires explicit action                      │
│  (MergeEngine.merge() with strategy selection)         │
└──────────────────────────────────────────────────────┘
```

This provides **strong logical isolation** between agents working on different branches. Each agent can only read/write its own branch tables.

### MCP Session Isolation

Each MCP session maintains its own active branch:
- Session ID from HTTP header
- Active branch tracked in `_active_branches_by_session` dict
- Branch switch only affects that session
- Session state cleared on HTTP DELETE

### What's NOT Isolated (Current)

- **API key**: Single shared key for all users
- **Database**: Single database for all branches and users
- **Rate limit**: Per-IP, not per-user or per-agent
- **Non-branched tables**: `tasks`, `sessions`, `scores`, etc. are shared across all branches

---

## Security Considerations

### Threat Model

| Threat | Current Mitigation | Gap |
|---|---|---|
| Unauthorized API access | Bearer token | Single shared key |
| Brute force attacks | Rate limiting | No account lockout |
| Cross-branch data leakage | Table-level isolation | Non-branched tables shared |
| SQL injection | SQLAlchemy ORM | Raw SQL in analytics (text()) |
| XSS in dashboard | React escaping | Need CSP headers |
| Data at rest | None | MatrixOne default encryption |
| Data in transit | HTTPS (via nginx) | Need TLS config |
| Secret exposure | Environment variables | No vault integration |

### Raw SQL Usage

The AnalyticsEngine uses `text()` for time-series queries:
```python
msg_sql = f"SELECT {trunc_expr} AS period, COUNT(*) ..."
await self._session.execute(text(msg_sql), params)
```

Parameters are bound via `:param` syntax (safe from injection), but the format string construction should be audited.

---

## Discussion: Security Roadmap

### Multi-Tenant Isolation
- **Database-level**: Separate MatrixOne databases per tenant (strongest, most expensive)
- **Schema-level**: Separate table prefixes per tenant (moderate isolation)
- **Row-level**: `tenant_id` column on every table (weakest, most flexible)
- **Recommendation**: Start with row-level for MVP, migrate to database-level for enterprise

### RBAC (Role-Based Access Control)
Potential roles:
- **Admin**: Full access, can manage templates, merge to main
- **Agent**: Read/write on assigned branches, cannot merge to main
- **Viewer**: Read-only access to specific branches
- **Question**: How to assign roles? Per API key? Per MCP session?

### Audit Logging
Currently, operations are logged via Python logging. For compliance:
- Structured audit log (who did what when)
- Immutable audit trail (append-only)
- Retention policies

### API Key Management
- **Current**: Single static key in environment variable
- **Needed**: Multiple keys, rotation, scoping (read-only keys, branch-specific keys)
- **Future**: OAuth/OIDC for enterprise SSO integration

### Data Encryption
- **At rest**: Delegate to MatrixOne's storage encryption
- **In transit**: HTTPS via nginx reverse proxy
- **Application-level**: Encrypt sensitive fact content? (may break search)

### Compliance (GDPR, SOC2)
- **Right to forget**: How to delete all memories for a specific user/session?
  - Need: Cascade delete across all tables (facts, observations, messages, conversations)
  - Challenge: Facts may have been merged to main and lost original session attribution
- **Data retention**: Automatic purge of memories older than N days?
- **Data export**: Bundle engine can serve as data export mechanism
