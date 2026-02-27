"""FastAPI application: Day1 memory layer."""

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

from day1.db.engine import close_db, init_db
from day1.mcp import mcp_server


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Day1 starting up")
    await init_db()

    # Ensure main branch exists
    from day1.core.memory_engine import MemoryEngine
    from day1.db.engine import get_session

    session_gen = get_session()
    session = await anext(session_gen)
    try:
        engine = MemoryEngine(session)
        await engine.ensure_main_branch()
    finally:
        await session_gen.aclose()

    logger.info("Day1 ready")
    mcp_http_manager = mcp_server.create_http_session_manager()
    mcp_server.set_http_session_manager(mcp_http_manager)
    try:
        async with mcp_http_manager.run():
            yield
    finally:
        mcp_server.set_http_session_manager(None)
        mcp_server.reset_mcp_http_state()
        await close_db()


app = FastAPI(
    title="Day1",
    description="Git-like memory layer for AI agents",
    version="2.0.0",
    lifespan=lifespan,
)

# MCP over HTTP (single supported transport)
for _mcp_path in ("/mcp", "/mcp/"):
    app.add_route(
        _mcp_path,
        mcp_server.mcp_http_asgi_app,
        methods=["GET", "POST", "DELETE"],
        include_in_schema=False,
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Rate limiting ──────────────────────────────────────────────────
_rate_buckets: dict[str, list[float]] = defaultdict(list)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if settings.rate_limit <= 0 or request.url.path in ("/health",) or request.url.path.startswith("/mcp"):
        return await call_next(request)
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    bucket = _rate_buckets[client_ip]
    _rate_buckets[client_ip] = [t for t in bucket if now - t < 60.0]
    if len(_rate_buckets[client_ip]) >= settings.rate_limit:
        return JSONResponse(status_code=429, content={"detail": "Too many requests."})
    _rate_buckets[client_ip].append(now)
    return await call_next(request)


# ── API key auth ───────────────────────────────────────────────────
_bearer = HTTPBearer(auto_error=False)


async def verify_api_key(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> None:
    if not settings.api_key:
        return
    if credentials is None or credentials.credentials != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}
