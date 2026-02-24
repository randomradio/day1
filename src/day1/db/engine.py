"""Database engine setup and session management (MatrixOne via aiomysql)."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import exc as sa_exc
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from day1.config import settings
from day1.db.models import Base

logger = logging.getLogger(__name__)

# Lazy initialization - set by init_db()
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_engine_kwargs() -> dict:
    """Get standard engine kwargs."""
    return {
        "echo": False,
        "future": True,
        "pool_size": 5,
        "max_overflow": 10,
        "pool_recycle": 3600,
    }


def _create_engine(url: str) -> AsyncEngine:
    """Create async engine for MatrixOne (MySQL-compatible)."""
    return create_async_engine(url, **_get_engine_kwargs())


def get_engine() -> AsyncEngine:
    """Get the current engine (for testing)."""
    if _engine is None:
        # Fallback: create engine from settings if not initialized
        return _create_engine(settings.database_url)
    return _engine


async def init_db() -> None:
    """Create database (if needed) and all tables with MatrixOne fulltext indexes.

    This function is idempotent - safe to call multiple times.
    Always uses 'day1' database regardless of what's in .env file.
    """
    global _engine, _session_factory

    # If already initialized, skip
    if _engine is not None and _session_factory is not None:
        return

    db_url = settings.database_url

    # Always create/use the 'day1' database
    # Extract server URL (everything before the last '/')
    server_url = db_url.rsplit('/', 1)[0] + '/mo_catalog'

    # Create day1 database if it doesn't exist
    engine = _create_engine(server_url)
    async with engine.begin() as conn:
        try:
            await conn.execute(text("CREATE DATABASE IF NOT EXISTS day1"))
            logger.info("Ensured 'day1' database exists")
        except sa_exc.DatabaseError as e:
            logger.debug("Database check: %s", e)
    await engine.dispose()

    # Always connect to 'day1' database (ignore what was in .env)
    target_url = db_url.rsplit('/', 1)[0] + '/day1'
    _engine = _create_engine(target_url)
    _session_factory = async_sessionmaker(
        _engine, class_=AsyncSession, expire_on_commit=False
    )

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Create FULLTEXT indexes (MatrixOne doesn't support IF NOT EXISTS in this position)
        fulltext_stmts = [
            "CREATE FULLTEXT INDEX ft_facts ON facts(fact_text, category)",
            "CREATE FULLTEXT INDEX ft_obs ON observations(summary, tool_name)",
            "CREATE FULLTEXT INDEX ft_messages ON messages(content, role)",
        ]
        for stmt in fulltext_stmts:
            try:
                await conn.execute(text(stmt))
            except sa_exc.DatabaseError as e:
                # Index may already exist - ignore error 1064
                if e.orig.args[0] != 1064 if hasattr(e, 'orig') and e.orig.args else True:
                    logger.debug("Fulltext index may already exist: %s", e)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with _session_factory() as session:
        yield session


@asynccontextmanager
async def get_autocommit_conn() -> AsyncGenerator[AsyncConnection, None]:
    """Yield an autocommit connection for MO DDL-like operations.

    MO's DATA BRANCH (CREATE/DIFF/MERGE) and CREATE SNAPSHOT cannot
    run inside an uncommitted transaction.  Use this helper for those.
    """
    engine = get_engine()
    async with engine.connect() as raw_conn:
        conn = await raw_conn.execution_options(isolation_level="AUTOCOMMIT")
        yield conn
