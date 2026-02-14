"""Pytest fixtures for BranchedMind tests (MatrixOne backend)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _load_env():
    """Load environment variables from .env file in project root."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    if key and key not in os.environ:
                        os.environ[key] = value


_load_env()

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

    # Cleanup: drop ALL tables including DATA BRANCH tables
    async with engine.begin() as conn:
        # First, drop any branch tables (suffixed versions of base tables)
        result = await conn.execute(text("SHOW TABLES"))
        all_tables = [row[0] for row in result.fetchall()]
        base_tables = {"facts", "relations", "observations", "branch_registry", "merge_history", "sessions"}
        for tbl in all_tables:
            if tbl not in base_tables:
                try:
                    await conn.execute(text(f"DROP TABLE IF EXISTS `{tbl}`"))
                except Exception:
                    pass

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

    # Cleanup: drop ALL tables including DATA BRANCH tables
    async with engine.begin() as conn:
        # Drop branch tables first
        base_tables = {"facts", "relations", "observations", "branch_registry", "merge_history", "sessions"}
        result = await conn.execute(text("SHOW TABLES"))
        all_tables = [row[0] for row in result.fetchall()]
        for tbl in all_tables:
            if tbl not in base_tables:
                try:
                    await conn.execute(text(f"DROP TABLE IF EXISTS `{tbl}`"))
                except Exception:
                    pass
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def mock_embedder():
    """Return a mock embedding provider."""
    return MockEmbedding(dims=64)
