"""Branch manager: create, list, switch, and manage memory branches."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from branchedmind.core.exceptions import BranchExistsError, BranchNotFoundError
from branchedmind.db.models import BranchRegistry, Fact, Observation, Relation


class BranchManager:
    """Manages memory branch lifecycle.

    In SQLite mode: branches use branch_name column filtering.
    In MatrixOne mode: branches use zero-copy database CLONE.
    """

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
        """Create a new memory branch.

        In SQLite mode, this copies all active data from parent_branch
        with the new branch_name.

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

        # Register the branch
        registry = BranchRegistry(
            branch_name=branch_name,
            parent_branch=parent_branch,
            description=description,
            status="active",
        )
        self._session.add(registry)

        # Copy facts from parent branch
        result = await self._session.execute(
            select(Fact).where(
                Fact.branch_name == parent_branch,
                Fact.status == "active",
            )
        )
        for fact in result.scalars().all():
            new_fact = Fact(
                fact_text=fact.fact_text,
                embedding_blob=fact.embedding_blob,
                category=fact.category,
                confidence=fact.confidence,
                status=fact.status,
                source_type=fact.source_type,
                source_id=fact.source_id,
                parent_id=fact.parent_id,
                session_id=fact.session_id,
                branch_name=branch_name,
                metadata_json=fact.metadata_json,
            )
            self._session.add(new_fact)

        # Copy relations from parent branch
        result = await self._session.execute(
            select(Relation).where(
                Relation.branch_name == parent_branch,
                Relation.valid_to.is_(None),
            )
        )
        for rel in result.scalars().all():
            new_rel = Relation(
                source_entity=rel.source_entity,
                target_entity=rel.target_entity,
                relation_type=rel.relation_type,
                properties=rel.properties,
                confidence=rel.confidence,
                session_id=rel.session_id,
                branch_name=branch_name,
            )
            self._session.add(new_rel)

        # Copy observations from parent branch
        result = await self._session.execute(
            select(Observation).where(Observation.branch_name == parent_branch)
        )
        for obs in result.scalars().all():
            new_obs = Observation(
                session_id=obs.session_id,
                observation_type=obs.observation_type,
                tool_name=obs.tool_name,
                summary=obs.summary,
                embedding_blob=obs.embedding_blob,
                raw_input=obs.raw_input,
                raw_output=obs.raw_output,
                branch_name=branch_name,
                metadata_json=obs.metadata_json,
            )
            self._session.add(new_obs)

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

    async def archive_branch(self, branch_name: str) -> None:
        """Archive a branch (mark as archived)."""
        await self.get_branch(branch_name)  # Verify exists
        await self._session.execute(
            update(BranchRegistry)
            .where(BranchRegistry.branch_name == branch_name)
            .values(status="archived")
        )
        await self._session.commit()
