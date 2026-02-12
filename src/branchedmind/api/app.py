"""FastAPI application: REST API for BranchedMind memory layer."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from branchedmind.api.routes import branches, facts, observations, relations, search, snapshots, tasks
from branchedmind.db.engine import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    await init_db()
    # Ensure main branch
    from branchedmind.core.branch_manager import BranchManager
    from branchedmind.db.engine import get_session

    async for session in get_session():
        mgr = BranchManager(session)
        await mgr.ensure_main_branch()
        break
    yield


app = FastAPI(
    title="BranchedMind",
    description="Git-like memory layer for AI agents",
    version="0.1.0",
    lifespan=lifespan,
)

# Search routes must come before parameterized routes to avoid conflicts
app.include_router(search.router, prefix="/api/v1", tags=["search"])
app.include_router(tasks.router, prefix="/api/v1", tags=["tasks"])
app.include_router(facts.router, prefix="/api/v1", tags=["facts"])
app.include_router(observations.router, prefix="/api/v1", tags=["observations"])
app.include_router(relations.router, prefix="/api/v1", tags=["relations"])
app.include_router(branches.router, prefix="/api/v1", tags=["branches"])
app.include_router(snapshots.router, prefix="/api/v1", tags=["snapshots"])


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
