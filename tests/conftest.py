"""Pytest fixtures for BranchedMind tests."""

from __future__ import annotations

import os
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Force test settings before any imports
os.environ["BM_DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["BM_EMBEDDING_PROVIDER"] = "mock"

from branchedmind.core.branch_manager import BranchManager
from branchedmind.core.embedding import MockEmbedding
from branchedmind.db.models import Base


@pytest_asyncio.fixture
async def db_session():
    """Create a fresh in-memory database for each test."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Create FTS5 tables
        from sqlalchemy import text

        await conn.execute(
            text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts "
                "USING fts5(id, fact_text, category, content='facts', content_rowid='rowid')"
            )
        )
        await conn.execute(
            text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS observations_fts "
                "USING fts5(id, summary, tool_name, content='observations', content_rowid='rowid')"
            )
        )

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Ensure main branch
        mgr = BranchManager(session)
        await mgr.ensure_main_branch()
        yield session

    await engine.dispose()


@pytest.fixture
def mock_embedder():
    """Return a mock embedding provider."""
    return MockEmbedding(dims=64)
