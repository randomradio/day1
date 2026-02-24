"""FastAPI application: REST API for Day1 memory layer."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from day1.config import settings
from day1.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

from day1.api.routes import (
    analytics,
    branch_topology,
    branches,
    conversations,
    facts,
    messages,
    observations,
    relations,
    replays,
    scores,
    search,
    sessions,
    snapshots,
    tasks,
    templates,
)
from day1.db.engine import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    logger.info("Day1 API starting up")
    await init_db()
    # Ensure main branch
    from day1.core.branch_manager import BranchManager
    from day1.db.engine import get_session

    async for session in get_session():
        mgr = BranchManager(session)
        await mgr.ensure_main_branch()
        break
    logger.info("Day1 API ready — %d routes loaded", len(app.routes))
    yield


app = FastAPI(
    title="Day1",
    description="Git-like memory layer for AI agents",
    version="0.1.0",
    lifespan=lifespan,
)


# ── CORS ──────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Rate Limiting (in-memory, per-IP) ─────────────────────────────
_rate_buckets: dict[str, list[float]] = defaultdict(list)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Simple sliding-window rate limiter.  Disabled when rate_limit=0."""
    if settings.rate_limit <= 0 or request.url.path == "/health":
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    window = 60.0

    bucket = _rate_buckets[client_ip]
    _rate_buckets[client_ip] = [t for t in bucket if now - t < window]

    if len(_rate_buckets[client_ip]) >= settings.rate_limit:
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Try again later."},
        )

    _rate_buckets[client_ip].append(now)
    return await call_next(request)


# ── API Key Authentication ────────────────────────────────────────
_bearer_scheme = HTTPBearer(auto_error=False)


async def verify_api_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """Verify Bearer token.  Disabled when BM_API_KEY is empty."""
    if not settings.api_key:
        return
    if credentials is None or credentials.credentials != settings.api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Routers ───────────────────────────────────────────────────────
_auth = [Depends(verify_api_key)]

# Search and message-search routes must come before parameterized routes
app.include_router(search.router, prefix="/api/v1", tags=["search"], dependencies=_auth)
app.include_router(messages.router, prefix="/api/v1", tags=["messages"], dependencies=_auth)
app.include_router(conversations.router, prefix="/api/v1", tags=["conversations"], dependencies=_auth)
app.include_router(tasks.router, prefix="/api/v1", tags=["tasks"], dependencies=_auth)
app.include_router(facts.router, prefix="/api/v1", tags=["facts"], dependencies=_auth)
app.include_router(observations.router, prefix="/api/v1", tags=["observations"], dependencies=_auth)
app.include_router(relations.router, prefix="/api/v1", tags=["relations"], dependencies=_auth)
# Topology routes before branches (fixed paths before {branch_name} param)
app.include_router(branch_topology.router, prefix="/api/v1", tags=["branch-topology"], dependencies=_auth)
app.include_router(branches.router, prefix="/api/v1", tags=["branches"], dependencies=_auth)
app.include_router(templates.router, prefix="/api/v1", tags=["templates"], dependencies=_auth)
app.include_router(sessions.router, prefix="/api/v1", tags=["sessions"], dependencies=_auth)
app.include_router(snapshots.router, prefix="/api/v1", tags=["snapshots"], dependencies=_auth)
app.include_router(replays.router, prefix="/api/v1", tags=["replays"], dependencies=_auth)
app.include_router(analytics.router, prefix="/api/v1", tags=["analytics"], dependencies=_auth)
app.include_router(scores.router, prefix="/api/v1", tags=["scores"], dependencies=_auth)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
