"""Branch manager: create, list, switch, and manage branches."""

from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from day1.core.exceptions import BranchCreationError, BranchExistsError, BranchNotFoundError
from day1.db.models import BranchRegistry

logger = logging.getLogger(__name__)

# Tables that participate in branching via DATA BRANCH CREATE TABLE
BRANCH_TABLES = ["facts", "relations", "observations", "conversations", "messages"]


def _branch_table(table: str, branch_name: str) -> str:
    """Map a base table name + branch to the actual MO table name.

    main branch uses the original table name.
    Other branches use suffixed tables: facts_feature_x.
    """
    if branch_name == "main":
        return table
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", branch_name)
    return f"{table}_{safe}"


class BranchManager:
    """Manages memory branch lifecycle using MatrixOne DATA BRANCH."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @asynccontextmanager
    async def _write_guard(self, op_name: str):
        """Rollback and close the session when a write path fails."""
        try:
            yield
        except Exception:
            logger.exception("Write path failed in BranchManager.%s", op_name)
            await self._session.rollback()
            await self._session.close()
            raise

    @asynccontextmanager
    async def _get_autocommit_conn(self) -> AsyncConnection:
        """Get an autocommit connection from the session's engine.

        Using the session's engine avoids event loop conflicts in tests
        where the global engine might be tied to a different event loop.
        """
        async with self._session.bind.connect() as raw_conn:
            conn = await raw_conn.execution_options(isolation_level="AUTOCOMMIT")
            yield conn

    async def ensure_main_branch(self) -> None:
        """Ensure the 'main' branch exists in the registry."""
        result = await self._session.execute(
            select(BranchRegistry).where(BranchRegistry.branch_name == "main")
        )
        if result.scalar_one_or_none() is None:
            try:
                async with self._write_guard("ensure_main_branch"):
                    self._session.add(
                        BranchRegistry(
                            branch_name="main",
                            parent_branch="main",
                            description="Default memory branch",
                            status="active",
                        )
                    )
                    await self._session.commit()
            except IntegrityError:
                # Concurrent initializer inserted main first.
                await self._session.rollback()

    async def create_branch(
        self,
        branch_name: str,
        parent_branch: str = "main",
        description: str | None = None,
        tables: list[str] | None = None,
    ) -> BranchRegistry:
        """Create a new memory branch using MO DATA BRANCH CREATE TABLE.

        Each branch creates suffixed copies of memory tables via zero-copy
        DATA BRANCH.

        Args:
            branch_name: New branch name.
            parent_branch: Branch to fork from.
            description: Optional description.
            tables: Override which tables to branch. None = all BRANCH_TABLES.
                     Use [] to create a branch with no table copies (for
                     curated branches that will be populated via cherry-pick).

        Returns:
            Created BranchRegistry entry.

        Raises:
            BranchExistsError: If branch already exists.
            BranchNotFoundError: If parent branch doesn't exist.
        """
        # Check branch doesn't already exist
        existing = await self._session.execute(
            select(BranchRegistry).where(BranchRegistry.branch_name == branch_name)
        )
        if existing.scalar_one_or_none() is not None:
            raise BranchExistsError(f"Branch '{branch_name}' already exists")

        # Verify parent exists
        parent = await self._session.execute(
            select(BranchRegistry).where(BranchRegistry.branch_name == parent_branch)
        )
        if parent.scalar_one_or_none() is None:
            raise BranchNotFoundError(f"Parent branch '{parent_branch}' not found")

        try:
            async with self._write_guard("create_branch"):
                # Flush and commit ORM work before DATA BRANCH operations
                await self._session.flush()

                # MO native: zero-copy branch per table (requires autocommit)
                # Use session's connection to avoid event loop conflicts
                branch_tables = tables if tables is not None else BRANCH_TABLES
                async with self._get_autocommit_conn() as ac:
                    for table in branch_tables:
                        parent_tbl = _branch_table(table, parent_branch)
                        branch_tbl = _branch_table(table, branch_name)
                        await ac.execute(
                            text(
                                f"DATA BRANCH CREATE TABLE `{branch_tbl}` FROM `{parent_tbl}`"
                            )
                        )

                # Register the branch
                registry = BranchRegistry(
                    branch_name=branch_name,
                    parent_branch=parent_branch,
                    description=description,
                    status="active",
                )
                self._session.add(registry)
                await self._session.commit()
        except Exception as e:
            raise BranchCreationError(f"Failed to create branch '{branch_name}': {e}") from e
        await self._session.refresh(registry)
        return registry

    async def list_branches(self, status: str | None = None) -> list[BranchRegistry]:
        """List all branches, optionally filtered by status."""
        stmt = select(BranchRegistry).order_by(BranchRegistry.forked_at.desc())
        if status:
            stmt = stmt.where(BranchRegistry.status == status)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_branch(self, branch_name: str) -> BranchRegistry:
        """Get a specific branch.

        Raises:
            BranchNotFoundError: If branch doesn't exist.
        """
        result = await self._session.execute(
            select(BranchRegistry).where(BranchRegistry.branch_name == branch_name)
        )
        branch = result.scalar_one_or_none()
        if branch is None:
            raise BranchNotFoundError(f"Branch '{branch_name}' not found")
        return branch

    async def _native_table_exists(self, table_name: str) -> bool:
        result = await self._session.execute(
            text("SHOW TABLES LIKE :table_name"),
            {"table_name": table_name},
        )
        return result.first() is not None

    async def _ensure_native_branch_tables(self, branch_name: str) -> None:
        missing = [
            tbl
            for base in BRANCH_TABLES
            if not await self._native_table_exists((tbl := _branch_table(base, branch_name)))
        ]
        if missing:
            raise BranchNotFoundError(
                f"Native branch tables missing for '{branch_name}': {', '.join(missing)}"
            )

    async def diff_branch(
        self,
        source_branch: str,
        target_branch: str = "main",
    ) -> list[dict]:
        """Get row-level diff between two branches using MO DATA BRANCH DIFF.

        Returns list of dicts with table name, diff flag (INSERT/UPDATE/DELETE),
        and row data.  Retries once with a fresh connection on lost-connection
        errors (transient on some MO Cloud versions).
        """
        await self.get_branch(source_branch)
        await self.get_branch(target_branch)
        await self._ensure_native_branch_tables(source_branch)
        await self._ensure_native_branch_tables(target_branch)

        all_diffs: list[dict] = []
        for table in BRANCH_TABLES:
            src = _branch_table(table, source_branch)
            tgt = _branch_table(table, target_branch)
            last_err: Exception | None = None
            for attempt in range(2):
                try:
                    async with self._get_autocommit_conn() as ac:
                        result = await ac.execute(
                            text(f"DATA BRANCH DIFF `{src}` AGAINST `{tgt}`")
                        )
                        columns = list(result.keys())
                        for row in result.fetchall():
                            row_dict = dict(zip(columns, row))
                            row_dict["_table"] = table
                            all_diffs.append(row_dict)
                    break
                except OperationalError as e:
                    last_err = e
                    if attempt == 0:
                        logger.debug("DIFF lost connection for %s, retrying", table)
            else:
                logger.warning("DIFF failed for %s after retry: %s", table, last_err)
        return all_diffs

    async def diff_branch_count(
        self,
        source_branch: str,
        target_branch: str = "main",
    ) -> dict[str, int]:
        """Get diff counts per table.

        Tries MO ``DATA BRANCH DIFF … OUTPUT COUNT`` first.  If that
        syntax is unsupported (some MO Cloud versions drop the
        connection), falls back to counting rows from a regular DIFF.
        """
        await self.get_branch(source_branch)
        await self.get_branch(target_branch)
        await self._ensure_native_branch_tables(source_branch)
        await self._ensure_native_branch_tables(target_branch)

        counts: dict[str, int] = {}
        for table in BRANCH_TABLES:
            src = _branch_table(table, source_branch)
            tgt = _branch_table(table, target_branch)
            try:
                async with self._get_autocommit_conn() as ac:
                    result = await ac.execute(
                        text(f"DATA BRANCH DIFF `{src}` AGAINST `{tgt}` OUTPUT COUNT")
                    )
                    row = result.fetchone()
                    counts[table] = int(row[0]) if row else 0
            except OperationalError:
                # Fallback: run plain DIFF and count rows
                logger.debug(
                    "OUTPUT COUNT failed for %s, falling back to row count", table
                )
                last_err: Exception | None = None
                for attempt in range(2):
                    try:
                        async with self._get_autocommit_conn() as ac:
                            result = await ac.execute(
                                text(f"DATA BRANCH DIFF `{src}` AGAINST `{tgt}`")
                            )
                            counts[table] = len(result.fetchall())
                        break
                    except OperationalError as e:
                        last_err = e
                        if attempt == 0:
                            logger.debug(
                                "DIFF row-count fallback lost connection for %s, retrying",
                                table,
                            )
                else:
                    logger.warning(
                        "DIFF row-count fallback failed for %s after retry: %s",
                        table,
                        last_err,
                    )
                    counts[table] = 0
        return counts

    async def merge_branch_native(
        self,
        source_branch: str,
        target_branch: str = "main",
        conflict: str = "skip",
    ) -> dict:
        """Merge branches using MO DATA BRANCH MERGE.

        Args:
            source_branch: Branch with changes.
            target_branch: Branch to merge into.
            conflict: Conflict strategy — "skip" (keep target) or "accept" (use source).

        Returns:
            Merge result dict.
        """
        await self.get_branch(source_branch)
        await self.get_branch(target_branch)

        conflict_clause = ""
        if conflict in ("skip", "accept"):
            conflict_clause = f" WHEN CONFLICT {conflict.upper()}"

        async with self._write_guard("merge_branch_native"):
            async with self._get_autocommit_conn() as ac:
                for table in BRANCH_TABLES:
                    src = _branch_table(table, source_branch)
                    tgt = _branch_table(table, target_branch)
                    await ac.execute(
                        text(
                            f"DATA BRANCH MERGE `{src}` INTO `{tgt}`{conflict_clause}"
                        )
                    )

            # Update branch status
            await self._session.execute(
                update(BranchRegistry)
                .where(BranchRegistry.branch_name == source_branch)
                .values(
                    status="merged",
                    merged_at=datetime.utcnow(),
                    merge_strategy=f"native_{conflict}",
                )
            )
            await self._session.commit()

        return {
            "status": "merged",
            "source": source_branch,
            "target": target_branch,
            "strategy": f"native_{conflict}",
        }

    async def archive_branch(self, branch_name: str) -> None:
        """Archive a branch: drop branch tables and mark as archived."""
        await self.get_branch(branch_name)  # Verify exists

        if branch_name == "main":
            raise BranchExistsError("Cannot archive the main branch")

        async with self._write_guard("archive_branch"):
            # Drop branch-specific tables (autocommit for DDL)
            async with self._get_autocommit_conn() as ac:
                for table in BRANCH_TABLES:
                    tbl = _branch_table(table, branch_name)
                    await ac.execute(text(f"DROP TABLE IF EXISTS `{tbl}`"))

            await self._session.execute(
                update(BranchRegistry)
                .where(BranchRegistry.branch_name == branch_name)
                .values(status="archived")
            )
            await self._session.commit()
