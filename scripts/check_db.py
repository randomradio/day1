#!/usr/bin/env python3
"""Simple database health check for Day1 release verification."""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from day1.config import settings
from day1.db.engine import close_db, get_engine, init_db


async def _main() -> int:
    await init_db()
    engine = get_engine()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        print(f"OK: database reachable ({settings.database_url})")
        return 0
    except Exception as exc:
        print(f"ERROR: database check failed: {exc}")
        return 1
    finally:
        await close_db()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
