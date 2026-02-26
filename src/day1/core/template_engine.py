"""Template engine: create, version, instantiate, and discover reusable branch templates."""

from __future__ import annotations

import logging
import re
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.branch_manager import BranchManager
from day1.core.exceptions import (
    BranchNotFoundError,
    TemplateError,
    TemplateNotFoundError,
)
from day1.db.models import (
    Conversation,
    Fact,
    TemplateBranch,
)

logger = logging.getLogger(__name__)


def _slug(name: str) -> str:
    """Convert a template name into a branch-safe slug."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class TemplateEngine:
    """Registry and lifecycle for reusable branch templates.

    Templates package curated knowledge (facts, conversations) from a source
    branch into a versioned, forkable unit.  New agents instantiate a template
    to start with pre-loaded knowledge.

    Key concepts:
    - **Create**: snapshot a source branch into ``template/<slug>/v1``
    - **Instantiate**: fork the template branch into a working branch (zero-copy)
    - **Update**: bump version (v1 → v2), deprecate old version
    - **Find**: match template by task type or semantic description
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._branch_mgr = BranchManager(session)

    async def create_template(
        self,
        name: str,
        source_branch: str,
        description: str | None = None,
        applicable_task_types: list[str] | None = None,
        tags: list[str] | None = None,
        created_by: str | None = None,
    ) -> TemplateBranch:
        """Create a template from an existing branch.

        1. Verify source branch exists.
        2. Create template branch ``template/<slug>/v1`` via BranchManager.
        3. Count facts/conversations on the template branch.
        4. Insert TemplateBranch registry record.

        Args:
            name: Human-readable template name (must be unique).
            source_branch: Branch to snapshot.
            description: Optional template description.
            applicable_task_types: Task types this template applies to.
            tags: Discovery tags.
            created_by: Creator identifier.

        Returns:
            Created TemplateBranch record.

        Raises:
            BranchNotFoundError: Source branch doesn't exist.
            TemplateError: Template name already exists or creation failed.
        """
        # Check uniqueness
        existing = await self._session.execute(
            select(TemplateBranch).where(
                TemplateBranch.name == name,
                TemplateBranch.status != "deprecated",
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise TemplateError(f"Template '{name}' already exists")

        # Verify source branch
        await self._branch_mgr.get_branch(source_branch)

        # Create template branch (zero-copy fork)
        slug = _slug(name)
        branch_name = f"template/{slug}/v1"
        try:
            await self._branch_mgr.create_branch(
                branch_name=branch_name,
                parent_branch=source_branch,
                description=f"Template: {name} (v1)",
            )
        except Exception as e:
            raise TemplateError(f"Failed to create template branch: {e}") from e

        # Count content on the new template branch
        # Count from source branch. DATA BRANCH creates zero-copy table clones and
        # row-level branch_name values are not rewritten automatically.
        fact_count = await self._session.scalar(
            select(func.count(Fact.id)).where(Fact.branch_name == source_branch)
        ) or 0
        conv_count = await self._session.scalar(
            select(func.count(Conversation.id)).where(
                Conversation.branch_name == source_branch
            )
        ) or 0

        # Register template
        template = TemplateBranch(
            name=name,
            description=description,
            version=1,
            branch_name=branch_name,
            source_branch=source_branch,
            applicable_task_types=applicable_task_types,
            tags=tags,
            fact_count=fact_count,
            conversation_count=conv_count,
            status="active",
            created_by=created_by,
        )
        self._session.add(template)
        await self._session.commit()
        await self._session.refresh(template)
        return template

    async def instantiate_template(
        self,
        template_name: str,
        target_branch_name: str,
        task_id: str | None = None,
    ) -> dict:
        """Fork a template into a working branch.

        Args:
            template_name: Name of the template to instantiate.
            target_branch_name: Name for the new working branch.
            task_id: Optional task ID to associate.

        Returns:
            Dict with branch_name, template info, and inherited content counts.

        Raises:
            TemplateNotFoundError: Template doesn't exist or is deprecated.
            TemplateError: Fork failed.
        """
        template = await self._get_active_template(template_name)

        try:
            await self._branch_mgr.create_branch(
                branch_name=target_branch_name,
                parent_branch=template.branch_name,
                description=f"Instantiated from template '{template_name}' v{template.version}",
            )
        except Exception as e:
            raise TemplateError(f"Failed to instantiate template: {e}") from e

        return {
            "branch_name": target_branch_name,
            "template_name": template.name,
            "template_version": template.version,
            "source_branch": template.branch_name,
            "facts_inherited": template.fact_count,
            "conversations_inherited": template.conversation_count,
            "task_id": task_id,
        }

    async def update_template(
        self,
        template_name: str,
        source_branch: str,
        reason: str | None = None,
    ) -> TemplateBranch:
        """Evolve a template by creating a new version.

        1. Look up current active version, mark as deprecated.
        2. Create new template branch ``template/<slug>/v<N+1>``.
        3. Fork from source_branch.
        4. Register new version.

        Args:
            template_name: Name of template to update.
            source_branch: Branch with updated knowledge.
            reason: Optional reason for the update.

        Returns:
            New TemplateBranch record.

        Raises:
            TemplateNotFoundError: Template doesn't exist.
            TemplateError: Update failed.
        """
        current = await self._get_active_template(template_name)
        new_version = current.version + 1

        # Deprecate current version
        await self._session.execute(
            update(TemplateBranch)
            .where(TemplateBranch.id == current.id)
            .values(status="deprecated")
        )

        # Verify source branch
        await self._branch_mgr.get_branch(source_branch)

        # Create new version branch
        slug = _slug(template_name)
        branch_name = f"template/{slug}/v{new_version}"
        try:
            await self._branch_mgr.create_branch(
                branch_name=branch_name,
                parent_branch=source_branch,
                description=f"Template: {template_name} (v{new_version})",
            )
        except Exception as e:
            raise TemplateError(f"Failed to create template branch v{new_version}: {e}") from e

        # Count content
        fact_count = await self._session.scalar(
            select(func.count(Fact.id)).where(Fact.branch_name == source_branch)
        ) or 0
        conv_count = await self._session.scalar(
            select(func.count(Conversation.id)).where(
                Conversation.branch_name == source_branch
            )
        ) or 0

        # Register new version
        metadata = {"previous_version": current.version}
        if reason:
            metadata["update_reason"] = reason

        new_template = TemplateBranch(
            name=template_name,
            description=current.description,
            version=new_version,
            branch_name=branch_name,
            source_branch=source_branch,
            applicable_task_types=current.applicable_task_types,
            tags=current.tags,
            fact_count=fact_count,
            conversation_count=conv_count,
            status="active",
            created_by=current.created_by,
            metadata_json=metadata,
        )
        self._session.add(new_template)
        await self._session.commit()
        await self._session.refresh(new_template)
        return new_template

    async def list_templates(
        self,
        task_type: str | None = None,
        tags: list[str] | None = None,
        status: str = "active",
        limit: int = 20,
    ) -> list[TemplateBranch]:
        """List templates with optional filters.

        Args:
            task_type: Filter by applicable task type.
            tags: Filter by tags (any match).
            status: Filter by status (default "active").
            limit: Max results.

        Returns:
            List of TemplateBranch records.
        """
        stmt = (
            select(TemplateBranch)
            .where(TemplateBranch.status == status)
            .order_by(TemplateBranch.updated_at.desc())
            .limit(limit)
        )

        result = await self._session.execute(stmt)
        templates = list(result.scalars().all())

        # Filter in Python since JSON column querying varies by DB
        if task_type:
            templates = [
                t for t in templates
                if t.applicable_task_types and task_type in t.applicable_task_types
            ]
        if tags:
            tag_set = set(tags)
            templates = [
                t for t in templates
                if t.tags and tag_set.intersection(t.tags)
            ]

        return templates

    async def get_template(self, template_name: str) -> TemplateBranch:
        """Get a template by name (latest active version).

        Raises:
            TemplateNotFoundError: If template doesn't exist.
        """
        return await self._get_active_template(template_name)

    async def find_applicable_template(
        self,
        task_type: str,
        task_description: str | None = None,
    ) -> TemplateBranch | None:
        """Find the best template for a given task type.

        Exact match on applicable_task_types first.  Returns None if no match.

        Args:
            task_type: Task type to match.
            task_description: Optional description for future semantic matching.

        Returns:
            Best matching TemplateBranch, or None.
        """
        result = await self._session.execute(
            select(TemplateBranch).where(TemplateBranch.status == "active")
        )
        templates = list(result.scalars().all())

        # Exact match on task type
        for t in templates:
            if t.applicable_task_types and task_type in t.applicable_task_types:
                return t

        return None

    async def deprecate_template(self, template_name: str) -> TemplateBranch:
        """Deprecate a template (all active versions).

        Args:
            template_name: Template to deprecate.

        Returns:
            The deprecated TemplateBranch record.

        Raises:
            TemplateNotFoundError: If template doesn't exist.
        """
        template = await self._get_active_template(template_name)

        await self._session.execute(
            update(TemplateBranch)
            .where(
                TemplateBranch.name == template_name,
                TemplateBranch.status == "active",
            )
            .values(status="deprecated")
        )
        await self._session.commit()

        # Re-fetch to return updated state
        result = await self._session.execute(
            select(TemplateBranch).where(TemplateBranch.id == template.id)
        )
        return result.scalar_one()

    async def _get_active_template(self, template_name: str) -> TemplateBranch:
        """Get the latest active version of a template.

        Raises:
            TemplateNotFoundError: If no active version exists.
        """
        result = await self._session.execute(
            select(TemplateBranch)
            .where(
                TemplateBranch.name == template_name,
                TemplateBranch.status == "active",
            )
            .order_by(TemplateBranch.version.desc())
            .limit(1)
        )
        template = result.scalar_one_or_none()
        if template is None:
            raise TemplateNotFoundError(f"Template '{template_name}' not found")
        return template
