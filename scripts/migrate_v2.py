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

    await engine.dispose()
    logger.info("Migration complete.")


if __name__ == "__main__":
    asyncio.run(migrate())
