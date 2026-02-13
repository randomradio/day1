"""Pytest fixtures for BranchedMind tests (MatrixOne backend)."""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Use MO test database; override with BM_TEST_DATABASE_URL env var
_TEST_DB_URL = os.environ.get(
    "BM_TEST_DATABASE_URL",
    os.environ.get(
        "BM_DATABASE_URL",
        "mysql+aiomysql://root:111@127.0.0.1:6001/branchedmind",
    ),
)
os.environ["BM_DATABASE_URL"] = _TEST_DB_URL
os.environ["BM_EMBEDDING_PROVIDER"] = "mock"

from branchedmind.core.branch_manager import BranchManager
from branchedmind.core.embedding import MockEmbedding
from branchedmind.db.models import Base


@pytest_asyncio.fixture
async def db_session():
    """Create a fresh database schema for each test.

    Uses the configured MatrixOne connection. Each test gets a clean
    set of tables (tables are dropped and recreated).
    """
    engine = create_async_engine(_TEST_DB_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        # Create FULLTEXT indexes (MO auto-indexes, replaces FTS5 virtual tables)
        for stmt in [
            "CREATE FULLTEXT INDEX IF NOT EXISTS ft_facts ON facts(fact_text, category)",
            "CREATE FULLTEXT INDEX IF NOT EXISTS ft_obs ON observations(summary, tool_name)",
        ]:
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Ensure main branch
        mgr = BranchManager(session)
        await mgr.ensure_main_branch()
        yield session

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def mock_embedder():
    """Return a mock embedding provider."""
    return MockEmbedding(dims=64)
