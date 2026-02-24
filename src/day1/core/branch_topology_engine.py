"""Branch topology engine: lifecycle policies, stats, and metadata enrichment."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.branch_manager import BranchManager
from day1.core.exceptions import BranchNotFoundError, BranchTopologyError
from day1.db.models import (
    BranchRegistry,
    Conversation,
    Fact,
    Observation,
)

logger = logging.getLogger(__name__)

# Recognised naming conventions
_CONVENTIONS = {
    r"^task/[a-z0-9_-]+$": "task",
    r"^task/[a-z0-9_-]+/[a-z0-9_-]+$": "task/agent",
    r"^template/[a-z0-9_-]+/v\d+$": "template",
    r"^team/[a-z0-9_-]+/[a-z0-9_-]+$": "team",
    r"^main$": "main",
}


class BranchTopologyEngine:
    """Branch lifecycle management, topology tree, and metadata enrichment.

    Extends BranchManager with:
    - Hierarchical topology tree (built from parent_branch)
    - Per-branch stats (fact/conversation/observation counts)
    - Auto-archive policies (inactive days, merged, TTL)
    - Branch metadata enrichment (purpose, owner, TTL, tags)
    - Naming convention validation
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._branch_mgr = BranchManager(session)

    async def get_topology(
        self,
        root_branch: str = "main",
        max_depth: int = 10,
        include_archived: bool = False,
    ) -> dict:
        """Build a nested tree from BranchRegistry using parent_branch.

        Returns a dict representing the tree rooted at *root_branch*:
        ``{"branch_name": "main", "children": [...], "stats": {...}, ...}``
        """
        stmt = select(BranchRegistry)
        if not include_archived:
            stmt = stmt.where(BranchRegistry.status != "archived")
        result = await self._session.execute(stmt)
        all_branches = list(result.scalars().all())

        # Build adjacency list
        children_map: dict[str, list[BranchRegistry]] = {}
        branch_map: dict[str, BranchRegistry] = {}
        for b in all_branches:
            branch_map[b.branch_name] = b
            parent = b.parent_branch or "main"
            children_map.setdefault(parent, []).append(b)

        if root_branch not in branch_map:
            raise BranchNotFoundError(f"Root branch '{root_branch}' not found")

        def _build_node(name: str, depth: int) -> dict:
            b = branch_map.get(name)
            node: dict = {
                "branch_name": name,
                "parent_branch": b.parent_branch if b else "main",
                "status": b.status if b else "unknown",
                "description": b.description if b else None,
                "forked_at": b.forked_at.isoformat() if b and b.forked_at else None,
                "metadata": b.metadata_json if b else None,
                "children": [],
            }
            if depth < max_depth:
                for child in children_map.get(name, []):
                    if child.branch_name != name:  # avoid self-reference
                        node["children"].append(
                            _build_node(child.branch_name, depth + 1)
                        )
            return node

        return _build_node(root_branch, 0)

    async def get_branch_stats(self, branch_name: str) -> dict:
        """Count facts, conversations, observations on a branch.

        Also returns last_activity timestamp and distinct agent count.
        """
        await self._branch_mgr.get_branch(branch_name)

        fact_count = await self._session.scalar(
            select(func.count(Fact.id)).where(Fact.branch_name == branch_name)
        ) or 0
        conv_count = await self._session.scalar(
            select(func.count(Conversation.id)).where(
                Conversation.branch_name == branch_name
            )
        ) or 0
        obs_count = await self._session.scalar(
            select(func.count(Observation.id)).where(
                Observation.branch_name == branch_name
            )
        ) or 0

        # Last activity: most recent created_at across tables
        last_fact = await self._session.scalar(
            select(func.max(Fact.created_at)).where(Fact.branch_name == branch_name)
        )
        last_conv = await self._session.scalar(
            select(func.max(Conversation.created_at)).where(
                Conversation.branch_name == branch_name
            )
        )
        last_obs = await self._session.scalar(
            select(func.max(Observation.created_at)).where(
                Observation.branch_name == branch_name
            )
        )
        timestamps = [t for t in [last_fact, last_conv, last_obs] if t is not None]
        last_activity = max(timestamps).isoformat() if timestamps else None

        # Distinct agents
        agent_count = await self._session.scalar(
            select(func.count(func.distinct(Fact.agent_id))).where(
                Fact.branch_name == branch_name,
                Fact.agent_id.isnot(None),
            )
        ) or 0

        return {
            "branch_name": branch_name,
            "fact_count": fact_count,
            "conversation_count": conv_count,
            "observation_count": obs_count,
            "agent_count": agent_count,
            "last_activity": last_activity,
        }

    async def enrich_branch_metadata(
        self,
        branch_name: str,
        purpose: str | None = None,
        owner: str | None = None,
        ttl_days: int | None = None,
        tags: list[str] | None = None,
    ) -> BranchRegistry:
        """Update BranchRegistry.metadata_json with enrichment fields."""
        branch = await self._branch_mgr.get_branch(branch_name)
        metadata = branch.metadata_json or {}

        if purpose is not None:
            metadata["purpose"] = purpose
        if owner is not None:
            metadata["owner"] = owner
        if ttl_days is not None:
            metadata["ttl_days"] = ttl_days
        if tags is not None:
            metadata["tags"] = tags
        metadata["enriched_at"] = datetime.utcnow().isoformat()

        await self._session.execute(
            update(BranchRegistry)
            .where(BranchRegistry.branch_name == branch_name)
            .values(metadata=metadata)
        )
        await self._session.commit()

        # Re-fetch to return updated state
        return await self._branch_mgr.get_branch(branch_name)

    async def apply_auto_archive(
        self,
        inactive_days: int = 30,
        archive_merged: bool = True,
        dry_run: bool = False,
    ) -> dict:
        """Apply auto-archive policies.

        Policy 1: Archive branches with no activity in *inactive_days*.
        Policy 2: Archive merged branches (if *archive_merged*).

        Args:
            inactive_days: Days of inactivity before archival.
            archive_merged: Also archive merged branches.
            dry_run: If True, return candidates without archiving.

        Returns:
            ``{"candidates": [...], "archived": N}``
        """
        cutoff = datetime.utcnow() - timedelta(days=inactive_days)

        result = await self._session.execute(
            select(BranchRegistry).where(
                BranchRegistry.branch_name != "main",
                BranchRegistry.status.in_(["active", "merged"]),
            )
        )
        branches = list(result.scalars().all())

        candidates: list[dict] = []
        for b in branches:
            reason: str | None = None

            if archive_merged and b.status == "merged":
                reason = "merged"
            elif b.status == "active":
                # Check last activity
                stats = await self.get_branch_stats(b.branch_name)
                last = stats.get("last_activity")
                if last is None:
                    # No content at all — check forked_at
                    if b.forked_at and b.forked_at < cutoff:
                        reason = f"inactive>{inactive_days}d (empty)"
                elif datetime.fromisoformat(last) < cutoff:
                    reason = f"inactive>{inactive_days}d"

            if reason:
                candidates.append({
                    "branch_name": b.branch_name,
                    "status": b.status,
                    "reason": reason,
                })

        archived = 0
        if not dry_run:
            for c in candidates:
                try:
                    await self._branch_mgr.archive_branch(c["branch_name"])
                    archived += 1
                except Exception as e:
                    logger.warning("Failed to archive %s: %s", c["branch_name"], e)

        return {"candidates": candidates, "archived": archived}

    async def check_ttl_expiry(self) -> list[dict]:
        """Find branches where forked_at + metadata.ttl_days < now."""
        result = await self._session.execute(
            select(BranchRegistry).where(
                BranchRegistry.status == "active",
                BranchRegistry.branch_name != "main",
            )
        )
        expired: list[dict] = []
        now = datetime.utcnow()
        for b in result.scalars().all():
            meta = b.metadata_json or {}
            ttl = meta.get("ttl_days")
            if ttl and b.forked_at:
                expiry = b.forked_at + timedelta(days=int(ttl))
                if now > expiry:
                    expired.append({
                        "branch_name": b.branch_name,
                        "ttl_days": ttl,
                        "forked_at": b.forked_at.isoformat(),
                        "expired_at": expiry.isoformat(),
                    })
        return expired

    async def validate_branch_name(self, branch_name: str) -> dict:
        """Check if a branch name follows recognised naming conventions.

        Returns ``{"valid": bool, "convention": str|None, "suggestion": str|None}``.
        """
        for pattern, convention in _CONVENTIONS.items():
            if re.match(pattern, branch_name):
                return {"valid": True, "convention": convention, "suggestion": None}

        # Not matching any convention — suggest the closest
        suggestion = None
        lower = branch_name.lower().replace(" ", "-")
        if "/" not in lower:
            suggestion = f"task/{lower}"

        return {"valid": False, "convention": None, "suggestion": suggestion}
