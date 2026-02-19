"""Merge engine: diff, cherry-pick, squash, auto-merge, and MO native merge."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.branch_manager import BranchManager
from day1.core.embedding import cosine_similarity, vecf32_to_embedding
from day1.core.exceptions import BranchNotFoundError
from day1.db.models import (
    BranchRegistry,
    Fact,
    MergeHistory,
    Observation,
    Relation,
)


class BranchDiff:
    """Result of comparing two branches (application-layer diff)."""

    def __init__(
        self,
        new_facts: list[Fact],
        new_relations: list[Relation],
        new_observations: list[Observation],
        conflicts: list[dict],
    ) -> None:
        self.new_facts = new_facts
        self.new_relations = new_relations
        self.new_observations = new_observations
        self.conflicts = conflicts

    def to_dict(self) -> dict:
        return {
            "new_facts": [
                {"id": f.id, "fact_text": f.fact_text, "category": f.category}
                for f in self.new_facts
            ],
            "new_relations": [
                {
                    "id": r.id,
                    "source": r.source_entity,
                    "target": r.target_entity,
                    "relation": r.relation_type,
                }
                for r in self.new_relations
            ],
            "new_observations": [
                {"id": o.id, "summary": o.summary, "type": o.observation_type}
                for o in self.new_observations
            ],
            "conflicts": self.conflicts,
        }


class MergeEngine:
    """Application-layer merge engine for memory branches."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def diff(
        self,
        source_branch: str,
        target_branch: str,
        category: str | None = None,
    ) -> BranchDiff:
        """Compare two branches to find differences.

        Args:
            source_branch: Branch with new changes.
            target_branch: Branch to merge into.
            category: Optional category filter.

        Returns:
            BranchDiff with new items and conflicts.
        """
        await self._verify_branch(source_branch)
        await self._verify_branch(target_branch)

        # Find facts in source that don't exist in target (by fact_text similarity)
        source_facts = await self._get_active_facts(source_branch, category)
        target_facts = await self._get_active_facts(target_branch, category)

        new_facts: list[Fact] = []
        conflicts: list[dict] = []

        for sf in source_facts:
            best_match = self._find_similar_fact(sf, target_facts)
            if best_match is None:
                new_facts.append(sf)
            elif (
                best_match["similarity"] > 0.85
                and sf.fact_text != best_match["fact"].fact_text
            ):
                conflicts.append(
                    {
                        "source_id": sf.id,
                        "target_id": best_match["fact"].id,
                        "source_text": sf.fact_text,
                        "target_text": best_match["fact"].fact_text,
                        "similarity": best_match["similarity"],
                    }
                )

        # Find new relations
        source_rels = await self._get_relations(source_branch)
        target_rels = await self._get_relations(target_branch)
        target_rel_keys = {
            (r.source_entity, r.target_entity, r.relation_type) for r in target_rels
        }
        new_relations = [
            r
            for r in source_rels
            if (r.source_entity, r.target_entity, r.relation_type)
            not in target_rel_keys
        ]

        # Find new observations
        source_obs = await self._get_observations(source_branch)
        target_obs_ids = {o.id for o in await self._get_observations(target_branch)}
        new_observations = [o for o in source_obs if o.id not in target_obs_ids]

        return BranchDiff(
            new_facts=new_facts,
            new_relations=new_relations,
            new_observations=new_observations,
            conflicts=conflicts,
        )

    async def merge(
        self,
        source_branch: str,
        target_branch: str = "main",
        strategy: str = "auto",
        items: list[str] | None = None,
        conflict: str = "skip",
    ) -> dict:
        """Execute a merge from source into target.

        Args:
            source_branch: Branch with new changes.
            target_branch: Branch to merge into.
            strategy: "auto", "cherry_pick", "squash", or "native".
            items: For cherry_pick, specific item IDs to merge.
            conflict: For native strategy — "skip" or "accept".

        Returns:
            Merge result with counts and merge_id.
        """
        if strategy == "native":
            return await self._native_merge(source_branch, target_branch, conflict)
        elif strategy == "cherry_pick":
            return await self._cherry_pick(source_branch, target_branch, items or [])
        elif strategy == "squash":
            return await self._squash_merge(source_branch, target_branch)
        else:
            return await self._auto_merge(source_branch, target_branch)

    async def _native_merge(
        self, source: str, target: str, conflict: str = "skip"
    ) -> dict:
        """Use MO DATA BRANCH MERGE directly."""
        mgr = BranchManager(self._session)
        result = await mgr.merge_branch_native(source, target, conflict)

        # Record merge history
        merge_record = MergeHistory(
            source_branch=source,
            target_branch=target,
            strategy=f"native_{conflict}",
            merged_by="native",
        )
        self._session.add(merge_record)
        await self._session.commit()

        result["merge_id"] = merge_record.id
        return result

    async def _cherry_pick(self, source: str, target: str, item_ids: list[str]) -> dict:
        """Selectively merge specific items."""
        merged_count = 0

        for item_id in item_ids:
            # Try facts first
            result = await self._session.execute(
                select(Fact).where(Fact.id == item_id, Fact.branch_name == source)
            )
            fact = result.scalar_one_or_none()
            if fact:
                new_fact = Fact(
                    fact_text=fact.fact_text,
                    embedding=fact.embedding,
                    category=fact.category,
                    confidence=fact.confidence,
                    source_type="merge",
                    source_id=fact.id,
                    session_id=fact.session_id,
                    branch_name=target,
                    metadata_json=fact.metadata_json,
                )
                self._session.add(new_fact)
                merged_count += 1
                continue

            # Try observations
            result = await self._session.execute(
                select(Observation).where(
                    Observation.id == item_id, Observation.branch_name == source
                )
            )
            obs = result.scalar_one_or_none()
            if obs:
                new_obs = Observation(
                    session_id=obs.session_id,
                    observation_type=obs.observation_type,
                    tool_name=obs.tool_name,
                    summary=obs.summary,
                    embedding=obs.embedding,
                    raw_input=obs.raw_input,
                    raw_output=obs.raw_output,
                    branch_name=target,
                    metadata_json=obs.metadata_json,
                )
                self._session.add(new_obs)
                merged_count += 1

        # Record merge history
        merge_record = MergeHistory(
            source_branch=source,
            target_branch=target,
            strategy="cherry_pick",
            items_merged={"ids": item_ids[:merged_count]},
            merged_by="manual",
        )
        self._session.add(merge_record)
        await self._session.commit()

        return {
            "merged_count": merged_count,
            "rejected_count": len(item_ids) - merged_count,
            "merge_id": merge_record.id,
        }

    async def _auto_merge(self, source: str, target: str) -> dict:
        """Automatic merge: non-conflicting items are merged directly."""
        diff = await self.diff(source, target)
        merged_ids: list[str] = []
        rejected_ids: list[str] = []

        conflict_fact_ids = {c["source_id"] for c in diff.conflicts}

        # Merge non-conflicting facts
        for fact in diff.new_facts:
            if fact.id not in conflict_fact_ids:
                new_fact = Fact(
                    fact_text=fact.fact_text,
                    embedding=fact.embedding,
                    category=fact.category,
                    confidence=fact.confidence,
                    source_type="merge",
                    source_id=fact.id,
                    session_id=fact.session_id,
                    branch_name=target,
                    metadata_json=fact.metadata_json,
                )
                self._session.add(new_fact)
                merged_ids.append(fact.id)

        # For conflicts, keep target version (safe default)
        for conflict in diff.conflicts:
            rejected_ids.append(conflict["source_id"])

        # Merge all new relations
        for rel in diff.new_relations:
            new_rel = Relation(
                source_entity=rel.source_entity,
                target_entity=rel.target_entity,
                relation_type=rel.relation_type,
                properties=rel.properties,
                confidence=rel.confidence,
                session_id=rel.session_id,
                branch_name=target,
            )
            self._session.add(new_rel)
            merged_ids.append(rel.id)

        # Merge new observations
        for obs in diff.new_observations:
            new_obs = Observation(
                session_id=obs.session_id,
                observation_type=obs.observation_type,
                tool_name=obs.tool_name,
                summary=obs.summary,
                embedding=obs.embedding,
                branch_name=target,
                metadata_json=obs.metadata_json,
            )
            self._session.add(new_obs)
            merged_ids.append(obs.id)

        # Update branch status
        await self._session.execute(
            update(BranchRegistry)
            .where(BranchRegistry.branch_name == source)
            .values(status="merged", merged_at=datetime.utcnow(), merge_strategy="auto")
        )

        # Record merge history
        merge_record = MergeHistory(
            source_branch=source,
            target_branch=target,
            strategy="auto",
            items_merged={"ids": merged_ids},
            items_rejected={"ids": rejected_ids},
            conflict_resolution={"conflicts": diff.conflicts},
            merged_by="auto",
        )
        self._session.add(merge_record)
        await self._session.commit()

        return {
            "merged_count": len(merged_ids),
            "rejected_count": len(rejected_ids),
            "conflicts": diff.conflicts,
            "merge_id": merge_record.id,
        }

    async def _squash_merge(self, source: str, target: str) -> dict:
        """Squash merge: combine all source facts into a summary."""
        diff = await self.diff(source, target)
        merged_ids: list[str] = []

        # Merge all facts (including conflicting ones as new entries)
        for fact in diff.new_facts:
            new_fact = Fact(
                fact_text=fact.fact_text,
                embedding=fact.embedding,
                category=fact.category,
                confidence=fact.confidence,
                source_type="merge",
                source_id=fact.id,
                session_id=fact.session_id,
                branch_name=target,
                metadata_json=fact.metadata_json,
            )
            self._session.add(new_fact)
            merged_ids.append(fact.id)

        for rel in diff.new_relations:
            new_rel = Relation(
                source_entity=rel.source_entity,
                target_entity=rel.target_entity,
                relation_type=rel.relation_type,
                properties=rel.properties,
                confidence=rel.confidence,
                session_id=rel.session_id,
                branch_name=target,
            )
            self._session.add(new_rel)
            merged_ids.append(rel.id)

        await self._session.execute(
            update(BranchRegistry)
            .where(BranchRegistry.branch_name == source)
            .values(
                status="merged", merged_at=datetime.utcnow(), merge_strategy="squash"
            )
        )

        merge_record = MergeHistory(
            source_branch=source,
            target_branch=target,
            strategy="squash",
            items_merged={"ids": merged_ids},
            merged_by="manual",
        )
        self._session.add(merge_record)
        await self._session.commit()

        return {
            "merged_count": len(merged_ids),
            "rejected_count": 0,
            "merge_id": merge_record.id,
        }

    # ---- helpers ----

    async def _verify_branch(self, branch_name: str) -> None:
        result = await self._session.execute(
            select(BranchRegistry).where(BranchRegistry.branch_name == branch_name)
        )
        if result.scalar_one_or_none() is None:
            raise BranchNotFoundError(f"Branch '{branch_name}' not found")

    async def _get_active_facts(
        self, branch_name: str, category: str | None = None
    ) -> list[Fact]:
        stmt = select(Fact).where(
            Fact.branch_name == branch_name, Fact.status == "active"
        )
        if category:
            stmt = stmt.where(Fact.category == category)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def _get_relations(self, branch_name: str) -> list[Relation]:
        result = await self._session.execute(
            select(Relation).where(
                Relation.branch_name == branch_name, Relation.valid_to.is_(None)
            )
        )
        return list(result.scalars().all())

    async def _get_observations(self, branch_name: str) -> list[Observation]:
        result = await self._session.execute(
            select(Observation).where(Observation.branch_name == branch_name)
        )
        return list(result.scalars().all())

    @staticmethod
    def _find_similar_fact(fact: Fact, candidates: list[Fact]) -> dict | None:
        """Find the most similar fact in candidates using embedding similarity."""
        if not fact.embedding or not candidates:
            return None

        fact_emb = vecf32_to_embedding(fact.embedding)
        if fact_emb is None:
            return None

        best_sim = 0.0
        best_fact = None

        for c in candidates:
            if c.embedding:
                c_emb = vecf32_to_embedding(c.embedding)
                if c_emb is not None:
                    sim = cosine_similarity(fact_emb, c_emb)
                    if sim > best_sim:
                        best_sim = sim
                        best_fact = c

        if best_fact is None:
            return None
        return {"fact": best_fact, "similarity": best_sim}
