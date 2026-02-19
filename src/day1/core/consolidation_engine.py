"""Consolidation engine: distill observations into facts, deduplicate, promote."""

from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.exceptions import ConsolidationError
from day1.db.models import (
    ConsolidationHistory,
    Fact,
    Observation,
    Task,
    TaskAgent,
)


class ConsolidationEngine:
    """Consolidates observations into facts, deduplicates, and promotes
    knowledge up the scope hierarchy (session → agent → task → project)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def consolidate_session(
        self,
        session_id: str,
        branch_name: str,
        task_id: str | None = None,
        agent_id: str | None = None,
    ) -> dict:
        """Session-level consolidation: observations → candidate facts.

        Steps:
        1. Gather observations from this session (insight/decision types).
        2. For each, check if a similar fact exists (Jaccard > 0.85).
        3. New facts are created; existing similar facts get confidence boost.
        4. Record in consolidation_history.

        Returns:
            Dict with facts_created, facts_updated, facts_deduplicated,
            observations_processed.
        """
        # Get session observations that are meaningful
        result = await self._session.execute(
            select(Observation).where(
                Observation.session_id == session_id,
                Observation.branch_name == branch_name,
                Observation.observation_type.in_(["insight", "decision", "discovery"]),
            )
        )
        observations = list(result.scalars().all())

        if not observations:
            return {
                "facts_created": 0,
                "facts_updated": 0,
                "facts_deduplicated": 0,
                "observations_processed": 0,
            }

        # Get existing facts on this branch for dedup
        existing_facts = await self._get_active_facts(branch_name)

        facts_created = 0
        facts_updated = 0
        facts_deduplicated = 0

        for obs in observations:
            # Check similarity against existing facts
            best_match = _find_similar_by_text(obs.summary, existing_facts)

            if best_match and best_match["similarity"] > 0.85:
                # Existing fact covers this — boost confidence
                new_confidence = min(best_match["fact"].confidence + 0.1, 1.0)
                if new_confidence != best_match["fact"].confidence:
                    await self._session.execute(
                        update(Fact)
                        .where(Fact.id == best_match["fact"].id)
                        .values(
                            confidence=new_confidence,
                            updated_at=datetime.utcnow(),
                        )
                    )
                    facts_updated += 1
                else:
                    facts_deduplicated += 1
            else:
                # New fact from observation
                fact = Fact(
                    fact_text=obs.summary,
                    category=_infer_category(obs.observation_type, obs.summary),
                    confidence=0.7,
                    source_type="consolidation",
                    source_id=obs.id,
                    session_id=session_id,
                    branch_name=branch_name,
                    task_id=task_id,
                    agent_id=agent_id,
                )
                self._session.add(fact)
                existing_facts.append(fact)
                facts_created += 1

        # Record consolidation
        history = ConsolidationHistory(
            task_id=task_id,
            agent_id=agent_id,
            session_id=session_id,
            consolidation_type="session_end",
            source_branch=branch_name,
            target_branch=branch_name,
            facts_created=facts_created,
            facts_updated=facts_updated,
            facts_deduplicated=facts_deduplicated,
            observations_processed=len(observations),
        )
        self._session.add(history)
        await self._session.commit()

        return {
            "facts_created": facts_created,
            "facts_updated": facts_updated,
            "facts_deduplicated": facts_deduplicated,
            "observations_processed": len(observations),
        }

    async def consolidate_agent(
        self,
        task_id: str,
        agent_id: str,
    ) -> dict:
        """Agent-level consolidation: cross-session dedup + summary.

        Steps:
        1. Get all facts on the agent's branch.
        2. Deduplicate across sessions (Jaccard similarity).
        3. Generate an agent summary fact.

        Returns:
            Dict with facts_deduplicated, summary.
        """
        # Find agent's branch
        result = await self._session.execute(
            select(TaskAgent).where(
                TaskAgent.task_id == task_id,
                TaskAgent.agent_id == agent_id,
            )
        )
        agent = result.scalar_one_or_none()
        if agent is None:
            raise ConsolidationError(f"No agent '{agent_id}' found on task '{task_id}'")

        # Deduplicate facts on agent branch
        deduplicated = await self._deduplicate_facts(agent.branch_name)

        # Generate summary from remaining facts
        facts = await self._get_active_facts(agent.branch_name)
        summary_parts = [f.fact_text for f in facts[:10]]
        summary = f"Agent {agent_id} produced {len(facts)} facts. " + (
            "Key findings: " + "; ".join(summary_parts[:5])
            if summary_parts
            else "No significant facts."
        )

        # Record consolidation
        history = ConsolidationHistory(
            task_id=task_id,
            agent_id=agent_id,
            consolidation_type="agent_complete",
            source_branch=agent.branch_name,
            target_branch=agent.branch_name,
            facts_deduplicated=deduplicated,
            summary=summary[:500],
        )
        self._session.add(history)
        await self._session.commit()

        return {
            "facts_deduplicated": deduplicated,
            "summary": summary,
        }

    async def consolidate_task(self, task_id: str) -> dict:
        """Task-level consolidation: classify facts as durable vs ephemeral.

        Durable facts (high confidence, useful categories) can be promoted
        to the parent branch (e.g., main). Ephemeral facts stay on the
        task branch.

        Returns:
            Dict with durable_fact_ids, ephemeral_count.
        """
        result = await self._session.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        if task is None:
            raise ConsolidationError(f"Task '{task_id}' not found")

        facts = await self._get_active_facts(task.branch_name)

        durable_categories = {
            "bug_fix",
            "architecture",
            "pattern",
            "decision",
            "security",
            "performance",
        }
        durable_facts = []
        ephemeral_count = 0

        for fact in facts:
            is_durable = fact.confidence >= 0.8 and fact.category in durable_categories
            if is_durable:
                durable_facts.append(fact.id)
            else:
                ephemeral_count += 1

        # Record consolidation
        history = ConsolidationHistory(
            task_id=task_id,
            consolidation_type="task_checkpoint",
            source_branch=task.branch_name,
            target_branch=task.parent_branch,
            summary=(
                f"Identified {len(durable_facts)} durable,"
                f" {ephemeral_count} ephemeral facts"
            ),
        )
        self._session.add(history)
        await self._session.commit()

        return {
            "durable_fact_ids": durable_facts,
            "ephemeral_count": ephemeral_count,
        }

    async def _deduplicate_facts(
        self,
        branch_name: str,
        threshold: float = 0.85,
    ) -> int:
        """Deduplicate facts on a branch using Jaccard token overlap.

        Uses text-based similarity (no embedding dependency) so it works
        with the two-layer architecture where embeddings may not exist yet.

        Returns:
            Number of facts deduplicated (superseded).
        """
        facts = await self._get_active_facts(branch_name)
        if len(facts) < 2:
            return 0

        # Build similarity groups using simple Union-Find
        parent = list(range(len(facts)))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for i in range(len(facts)):
            for j in range(i + 1, len(facts)):
                sim = _jaccard_similarity(facts[i].fact_text, facts[j].fact_text)
                if sim > threshold:
                    union(i, j)

        # Group by root
        groups: dict[int, list[int]] = {}
        for i in range(len(facts)):
            root = find(i)
            groups.setdefault(root, []).append(i)

        # For each group with > 1 member, keep the best
        deduplicated = 0
        for indices in groups.values():
            if len(indices) <= 1:
                continue
            group_facts = [facts[i] for i in indices]
            best = max(group_facts, key=lambda f: (f.confidence, f.created_at))
            for f in group_facts:
                if f.id != best.id:
                    await self._session.execute(
                        update(Fact)
                        .where(Fact.id == f.id)
                        .values(status="superseded", parent_id=best.id)
                    )
                    deduplicated += 1

        if deduplicated > 0:
            await self._session.commit()
        return deduplicated

    async def _get_active_facts(self, branch_name: str) -> list[Fact]:
        """Get all active facts on a branch."""
        result = await self._session.execute(
            select(Fact).where(
                Fact.branch_name == branch_name,
                Fact.status == "active",
            )
        )
        return list(result.scalars().all())


def _jaccard_similarity(text_a: str, text_b: str) -> float:
    """Compute Jaccard similarity between two texts using word tokens."""
    tokens_a = set(_tokenize(text_a))
    tokens_b = set(_tokenize(text_b))
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _tokenize(text: str) -> list[str]:
    """Simple word tokenization: lowercase, split on non-alphanumeric."""
    return [w for w in re.split(r"\W+", text.lower()) if len(w) > 1]


def _find_similar_by_text(
    text: str,
    candidates: list[Fact],
    threshold: float = 0.0,
) -> dict | None:
    """Find the most similar fact by Jaccard text similarity."""
    best_sim = threshold
    best_fact = None
    for c in candidates:
        sim = _jaccard_similarity(text, c.fact_text)
        if sim > best_sim:
            best_sim = sim
            best_fact = c
    if best_fact is None:
        return None
    return {"fact": best_fact, "similarity": best_sim}


def _infer_category(observation_type: str, summary: str) -> str:
    """Infer a fact category from the observation type and content."""
    if observation_type == "decision":
        return "decision"
    if observation_type == "discovery":
        return "discovery"
    summary_lower = summary.lower()
    if any(w in summary_lower for w in ["bug", "fix", "error", "issue"]):
        return "bug_fix"
    if any(w in summary_lower for w in ["architect", "design", "structure"]):
        return "architecture"
    if any(w in summary_lower for w in ["security", "vulnerability", "auth"]):
        return "security"
    return "insight"
