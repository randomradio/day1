#!/usr/bin/env python3
"""Database migration script: create all tables."""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "src")

from branchedmind.core.branch_manager import BranchManager
from branchedmind.db.engine import get_session, init_db


async def main() -> None:
    """Run database migrations."""
    print("Initializing database...")
    await init_db()
    print("Tables created.")

    print("Ensuring main branch...")
    async for session in get_session():
        mgr = BranchManager(session)
        await mgr.ensure_main_branch()
        break
    print("Main branch ready.")
    print("Migration complete!")


if __name__ == "__main__":
    asyncio.run(main())
