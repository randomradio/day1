"""Create Day1 v2 tables: memories, branches, snapshots."""

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    from day1.config import settings
    from day1.db.models import Base

    db_url = settings.database_url
    server_url = db_url.rsplit("/", 1)[0] + "/mo_catalog"
    target_url = db_url.rsplit("/", 1)[0] + "/day1"

    # Ensure day1 database exists
    engine = create_async_engine(server_url, echo=False, future=True)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE DATABASE IF NOT EXISTS day1"))
        logger.info("Ensured 'day1' database exists")
    await engine.dispose()

    # Create tables
    engine = create_async_engine(target_url, echo=True, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Created tables: memories, branches, snapshots")

        # FULLTEXT index for hybrid search
        try:
            await conn.execute(text("CREATE FULLTEXT INDEX ft_memories ON memories(text, context)"))
            logger.info("Created FULLTEXT index on memories")
        except Exception as e:
            logger.info("FULLTEXT index may already exist: %s", e)

        # Idempotent schema enrichment columns (safe to rerun)
        enrichment_columns = [
            ("category", "VARCHAR(50) DEFAULT NULL"),
            ("confidence", "FLOAT DEFAULT 0.7"),
            ("source_type", "VARCHAR(50) DEFAULT NULL"),
            ("status", "VARCHAR(20) DEFAULT 'active'"),
        ]
        for col_name, col_def in enrichment_columns:
            try:
                await conn.execute(text(f"ALTER TABLE memories ADD COLUMN {col_name} {col_def}"))
                logger.info("Added column: memories.%s", col_name)
            except Exception as e:
                logger.info("Column memories.%s may already exist: %s", col_name, e)

        # Indexes for new columns
        enrichment_indexes = [
            ("idx_mem_category", "category"),
            ("idx_mem_source_type", "source_type"),
            ("idx_mem_status", "status"),
        ]
        for idx_name, col_name in enrichment_indexes:
            try:
                await conn.execute(text(f"CREATE INDEX {idx_name} ON memories({col_name})"))
                logger.info("Created index: %s", idx_name)
            except Exception as e:
                logger.info("Index %s may already exist: %s", idx_name, e)

    await engine.dispose()
    logger.info("Migration complete.")


if __name__ == "__main__":
    asyncio.run(migrate())
