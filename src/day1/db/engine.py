"""Database engine setup and session management (MatrixOne via aiomysql)."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import exc as sa_exc
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from day1.config import settings
from day1.db.models import Base

logger = logging.getLogger(__name__)


def _create_engine():
    """Create async engine for MatrixOne (MySQL-compatible)."""
    kwargs: dict = {
        "echo": False,
        "future": True,
        "pool_size": 5,
        "max_overflow": 10,
        "pool_recycle": 3600,
    }
    return create_async_engine(settings.database_url, **kwargs)


_engine = _create_engine()

_session_factory = async_sessionmaker(
    _engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Create database (if needed) and all tables with MatrixOne fulltext indexes."""
    # First, connect without specifying a database to create 'day1' database
    db_url = settings.database_url
    needs_db_creation = db_url.endswith('/mo_catalog') or db_url.endswith('/sys') or not any(
        f'/{name}' in db_url for name in ('day1', 'branchedmind')
    )

    if needs_db_creation:
        # Create connection to server and create day1 database
        from sqlalchemy.ext.asyncio import create_async_engine
        server_url = db_url.rsplit('/', 1)[0] + '/mo_catalog'
        engine = create_async_engine(server_url, **{"echo": False, "future": True})

        async with engine.begin() as conn:
            try:
                await conn.execute(text("CREATE DATABASE IF NOT EXISTS day1"))
                logger.info("Created 'day1' database")
            except sa_exc.DatabaseError as e:
                logger.debug("Database may already exist: %s", e)
        await engine.dispose()

    # Now connect to the actual database and create tables
    target_url = db_url.rsplit('/', 1)[0] + '/day1'
    engine = create_async_engine(target_url, **{"echo": False, "future": True})
    global _engine, _session_factory
    _engine = engine
    _session_factory = async_sessionmaker(
        _engine, class_=AsyncSession, expire_on_commit=False
    )

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Create FULLTEXT indexes (MO auto-indexes, replaces FTS5 virtual tables)
        fulltext_stmts = [
            "CREATE FULLTEXT INDEX IF NOT EXISTS"
            " ft_facts ON facts(fact_text, category)",
            "CREATE FULLTEXT INDEX IF NOT EXISTS"
            " ft_obs ON observations(summary, tool_name)",
            "CREATE FULLTEXT INDEX IF NOT EXISTS"
            " ft_messages ON messages(content, role)",
        ]
        for stmt in fulltext_stmts:
            try:
                await conn.execute(text(stmt))
            except sa_exc.DatabaseError as e:
                logger.debug("Fulltext index may already exist: %s", e)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session."""
    async with _session_factory() as session:
        yield session


@asynccontextmanager
async def get_autocommit_conn() -> AsyncGenerator[AsyncConnection, None]:
    """Yield an autocommit connection for MO DDL-like operations.

    MO's DATA BRANCH (CREATE/DIFF/MERGE) and CREATE SNAPSHOT cannot
    run inside an uncommitted transaction.  Use this helper for those.
    """
    async with _engine.connect() as raw_conn:
        conn = await raw_conn.execution_options(isolation_level="AUTOCOMMIT")
        yield conn


def get_engine():
    """Return the async engine (for testing)."""
    return _engine
