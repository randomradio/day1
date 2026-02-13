"""Branch manager: create, list, switch, and manage memory branches (MatrixOne native)."""

from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from branchedmind.core.exceptions import BranchExistsError, BranchNotFoundError
from branchedmind.db.models import BranchRegistry

# Tables that participate in branching via DATA BRANCH CREATE TABLE
BRANCH_TABLES = ["facts", "relations", "observations"]


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

    async def ensure_main_branch(self) -> None:
        """Ensure the 'main' branch exists in the registry."""
        result = await self._session.execute(
            select(BranchRegistry).where(BranchRegistry.branch_name == "main")
        )
        if result.scalar_one_or_none() is None:
            self._session.add(
                BranchRegistry(
                    branch_name="main",
                    parent_branch="main",
                    description="Default memory branch",
                    status="active",
                )
            )
            await self._session.commit()

    async def create_branch(
        self,
        branch_name: str,
        parent_branch: str = "main",
        description: str | None = None,
    ) -> BranchRegistry:
        """Create a new memory branch using MO DATA BRANCH CREATE TABLE.

        Each branch creates suffixed copies of facts/relations/observations
        tables via zero-copy DATA BRANCH.

        Args:
            branch_name: New branch name.
            parent_branch: Branch to fork from.
            description: Optional description.

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

        # MO native: zero-copy branch per table
        for table in BRANCH_TABLES:
            parent_tbl = _branch_table(table, parent_branch)
            branch_tbl = _branch_table(table, branch_name)
            await self._session.execute(
                text(f"DATA BRANCH CREATE TABLE {branch_tbl} FROM {parent_tbl}")
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
        return registry

    async def list_branches(
        self, status: str | None = None
    ) -> list[BranchRegistry]:
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

    async def diff_branch(
        self,
        source_branch: str,
        target_branch: str = "main",
    ) -> list[dict]:
        """Get row-level diff between two branches using MO DATA BRANCH DIFF.

        Returns list of dicts with table name, diff flag (INSERT/UPDATE/DELETE),
        and row data.
        """
        await self.get_branch(source_branch)
        await self.get_branch(target_branch)

        all_diffs: list[dict] = []
        for table in BRANCH_TABLES:
            src = _branch_table(table, source_branch)
            tgt = _branch_table(table, target_branch)
            result = await self._session.execute(
                text(f"DATA BRANCH DIFF {src} AGAINST {tgt}")
            )
            columns = list(result.keys())
            for row in result.fetchall():
                row_dict = dict(zip(columns, row))
                row_dict["_table"] = table
                all_diffs.append(row_dict)
        return all_diffs

    async def diff_branch_count(
        self,
        source_branch: str,
        target_branch: str = "main",
    ) -> dict[str, int]:
        """Get diff counts per table using MO DATA BRANCH DIFF OUTPUT COUNT."""
        await self.get_branch(source_branch)
        await self.get_branch(target_branch)

        counts: dict[str, int] = {}
        for table in BRANCH_TABLES:
            src = _branch_table(table, source_branch)
            tgt = _branch_table(table, target_branch)
            result = await self._session.execute(
                text(f"DATA BRANCH DIFF {src} AGAINST {tgt} OUTPUT COUNT")
            )
            row = result.fetchone()
            counts[table] = int(row[0]) if row else 0
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

        for table in BRANCH_TABLES:
            src = _branch_table(table, source_branch)
            tgt = _branch_table(table, target_branch)
            await self._session.execute(
                text(f"DATA BRANCH MERGE {src} INTO {tgt}{conflict_clause}")
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

        # Drop branch-specific tables
        for table in BRANCH_TABLES:
            tbl = _branch_table(table, branch_name)
            await self._session.execute(text(f"DROP TABLE IF EXISTS {tbl}"))

        await self._session.execute(
            update(BranchRegistry)
            .where(BranchRegistry.branch_name == branch_name)
            .values(status="archived")
        )
        await self._session.commit()
