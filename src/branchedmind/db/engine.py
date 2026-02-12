"""Database engine setup and session management."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from branchedmind.config import settings
from branchedmind.db.models import Base


def _create_engine():
    """Create async engine with appropriate pooling."""
    kwargs: dict = {"echo": False, "future": True}

    # In-memory SQLite needs StaticPool to share state across connections
    if settings.database_url.endswith("://") or ":memory:" in settings.database_url:
        kwargs["poolclass"] = StaticPool
        kwargs["connect_args"] = {"check_same_thread": False}

    return create_async_engine(settings.database_url, **kwargs)


_engine = _create_engine()

_session_factory = async_sessionmaker(
    _engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Create all tables if they don't exist."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Create FTS5 virtual table for full-text search on facts
        await conn.execute(
            text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts "
                "USING fts5(id, fact_text, category, content='facts', content_rowid='rowid')"
            )
        )
        # Create FTS5 virtual table for observations
        await conn.execute(
            text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS observations_fts "
                "USING fts5(id, summary, tool_name, content='observations', content_rowid='rowid')"
            )
        )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session."""
    async with _session_factory() as session:
        yield session


def get_engine():
    """Return the async engine (for testing)."""
    return _engine
