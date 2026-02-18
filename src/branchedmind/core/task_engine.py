"""Task engine: manage long-running tasks with multi-agent coordination."""

from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from branchedmind.core.branch_manager import BranchManager
from branchedmind.core.exceptions import TaskAgentError, TaskNotFoundError
from branchedmind.core.merge_engine import MergeEngine
from branchedmind.db.models import Fact, Observation, Task, TaskAgent


class TaskEngine:
    """Manages task lifecycle: create, assign agents, track objectives, consolidate."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_task(
        self,
        name: str,
        description: str | None = None,
        task_type: str | None = None,
        tags: list[str] | None = None,
        objectives: list[dict] | None = None,
        parent_branch: str = "main",
    ) -> Task:
        """Create a task and its corresponding branch.

        Args:
            name: Task name (e.g., "fix-oauth2-bug").
            description: What this task aims to accomplish.
            task_type: Category: bug_fix, pr_review, feature, research, etc.
            tags: Cross-cutting labels for discovery.
            objectives: List of {"description": "..."} items.
            parent_branch: Branch to fork from.

        Returns:
            Created Task object.
        """
        slug = _slugify(name)
        branch_name = f"task/{slug}"

        # Number objectives
        numbered_objectives = None
        if objectives:
            numbered_objectives = [
                {
                    "id": i + 1,
                    "description": (
                        obj.get("description", obj)
                        if isinstance(obj, dict)
                        else str(obj)
                    ),
                    "status": "todo",
                    "agent_id": None,
                }
                for i, obj in enumerate(objectives)
            ]

        # Create branch via BranchManager
        branch_mgr = BranchManager(self._session)
        await branch_mgr.create_branch(
            branch_name=branch_name,
            parent_branch=parent_branch,
            description=f"Task: {name}",
        )

        task = Task(
            name=name,
            description=description,
            branch_name=branch_name,
            parent_branch=parent_branch,
            task_type=task_type,
            tags=tags,
            objectives=numbered_objectives,
        )
        self._session.add(task)
        await self._session.commit()
        await self._session.refresh(task)
        return task

    async def get_task(self, task_id: str) -> Task:
        """Get a task by ID.

        Raises:
            TaskNotFoundError: If task doesn't exist.
        """
        result = await self._session.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        if task is None:
            raise TaskNotFoundError(f"Task {task_id} not found")
        return task

    async def list_tasks(
        self,
        status: str | None = None,
        task_type: str | None = None,
        limit: int = 20,
    ) -> list[Task]:
        """List tasks with optional filters."""
        stmt = select(Task).order_by(Task.created_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(Task.status == status)
        if task_type:
            stmt = stmt.where(Task.task_type == task_type)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def join_task(
        self,
        task_id: str,
        agent_id: str,
        role: str | None = None,
        assigned_objectives: list[int] | None = None,
    ) -> dict:
        """Register an agent on a task.

        Creates an isolated agent branch forked from the task branch
        and returns the full task context.

        Args:
            task_id: Task to join.
            agent_id: Unique agent identifier (global, cross-task).
            role: Agent role (implementer, reviewer, tester).
            assigned_objectives: Objective IDs this agent will work on.

        Returns:
            Dict with agent_branch and task_context.
        """
        task = await self.get_task(task_id)

        # Check agent not already active on this task
        existing = await self._session.execute(
            select(TaskAgent).where(
                TaskAgent.task_id == task_id,
                TaskAgent.agent_id == agent_id,
                TaskAgent.status == "active",
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise TaskAgentError(
                f"Agent '{agent_id}' is already active on task '{task_id}'"
            )

        # Create agent branch
        agent_branch = f"{task.branch_name}/{agent_id}"
        branch_mgr = BranchManager(self._session)
        await branch_mgr.create_branch(
            branch_name=agent_branch,
            parent_branch=task.branch_name,
            description=f"Agent {agent_id} on task: {task.name}",
        )

        # Update objectives to active if assigned
        if assigned_objectives and task.objectives:
            updated_objectives = list(task.objectives)
            for obj in updated_objectives:
                if obj["id"] in assigned_objectives:
                    obj["status"] = "active"
                    obj["agent_id"] = agent_id
            await self._session.execute(
                update(Task)
                .where(Task.id == task_id)
                .values(objectives=updated_objectives, updated_at=datetime.utcnow())
            )

        # Register the agent
        task_agent = TaskAgent(
            task_id=task_id,
            agent_id=agent_id,
            branch_name=agent_branch,
            role=role,
            assigned_objectives=assigned_objectives,
        )
        self._session.add(task_agent)
        await self._session.commit()

        # Return task context
        context = await self.get_task_context(task_id)
        return {
            "agent_branch": agent_branch,
            "task_context": context,
        }

    async def get_task_context(self, task_id: str) -> dict:
        """Build the full context a new agent needs to start working.

        Returns:
            Dict with task info, objectives, agent summaries, key facts,
            and active agents.
        """
        task = await self.get_task(task_id)

        # Get all agents on this task
        result = await self._session.execute(
            select(TaskAgent)
            .where(TaskAgent.task_id == task_id)
            .order_by(TaskAgent.joined_at)
        )
        agents = list(result.scalars().all())

        # Agent summaries (completed agents)
        agent_summaries = [
            {"agent_id": a.agent_id, "role": a.role, "summary": a.summary}
            for a in agents
            if a.status == "completed" and a.summary
        ]

        # Active agents
        active_agents = [
            {
                "agent_id": a.agent_id,
                "role": a.role,
                "assigned_objectives": a.assigned_objectives,
            }
            for a in agents
            if a.status == "active"
        ]

        # Key facts on task branch (most recent)
        fact_result = await self._session.execute(
            select(Fact)
            .where(
                Fact.branch_name == task.branch_name,
                Fact.status == "active",
            )
            .order_by(Fact.created_at.desc())
            .limit(20)
        )
        key_facts = [
            {
                "id": f.id,
                "fact_text": f.fact_text,
                "category": f.category,
                "confidence": f.confidence,
                "agent_id": f.agent_id,
            }
            for f in fact_result.scalars().all()
        ]

        # Progress
        progress = {"total": 0, "done": 0, "active": 0, "todo": 0, "blocked": 0}
        if task.objectives:
            progress["total"] = len(task.objectives)
            for obj in task.objectives:
                status = obj.get("status", "todo")
                if status in progress:
                    progress[status] += 1

        return {
            "task": {
                "id": task.id,
                "name": task.name,
                "description": task.description,
                "task_type": task.task_type,
                "tags": task.tags,
                "status": task.status,
                "objectives": task.objectives or [],
            },
            "agent_summaries": agent_summaries,
            "active_agents": active_agents,
            "key_facts": key_facts,
            "progress": progress,
        }

    async def update_objective(
        self,
        task_id: str,
        objective_id: int,
        status: str,
        agent_id: str | None = None,
        notes: str | None = None,
    ) -> Task:
        """Update an objective's status.

        Args:
            task_id: Task ID.
            objective_id: Objective number (1-based).
            status: New status (done, active, todo, blocked).
            agent_id: Agent making the update.
            notes: Notes about completion or blockers.
        """
        task = await self.get_task(task_id)
        if not task.objectives:
            raise TaskAgentError("Task has no objectives")

        updated = list(task.objectives)
        found = False
        for obj in updated:
            if obj["id"] == objective_id:
                obj["status"] = status
                if agent_id:
                    obj["agent_id"] = agent_id
                if notes:
                    obj["notes"] = notes
                found = True
                break

        if not found:
            raise TaskAgentError(f"Objective {objective_id} not found")

        await self._session.execute(
            update(Task)
            .where(Task.id == task_id)
            .values(objectives=updated, updated_at=datetime.utcnow())
        )
        await self._session.commit()
        return await self.get_task(task_id)

    async def complete_agent(
        self,
        task_id: str,
        agent_id: str,
        summary: str | None = None,
    ) -> dict:
        """Mark an agent as completed and merge its branch to task branch.

        Args:
            task_id: Task ID.
            agent_id: Agent ID to complete.
            summary: Summary of what the agent accomplished.

        Returns:
            Merge result dict.
        """
        task = await self.get_task(task_id)

        # Find the agent
        result = await self._session.execute(
            select(TaskAgent).where(
                TaskAgent.task_id == task_id,
                TaskAgent.agent_id == agent_id,
                TaskAgent.status == "active",
            )
        )
        agent = result.scalar_one_or_none()
        if agent is None:
            raise TaskAgentError(f"No active agent '{agent_id}' on task '{task_id}'")

        # Mark agent as completed
        await self._session.execute(
            update(TaskAgent)
            .where(TaskAgent.id == agent.id)
            .values(
                status="completed",
                summary=summary,
                left_at=datetime.utcnow(),
            )
        )

        # Update assigned objectives to done
        if agent.assigned_objectives and task.objectives:
            updated = list(task.objectives)
            for obj in updated:
                if (
                    obj["id"] in agent.assigned_objectives
                    and obj.get("agent_id") == agent_id
                ):
                    obj["status"] = "done"
            await self._session.execute(
                update(Task)
                .where(Task.id == task_id)
                .values(objectives=updated, updated_at=datetime.utcnow())
            )

        # Commit ORM changes before merge (which uses DATA BRANCH operations)
        await self._session.commit()

        # Merge agent branch → task branch
        merge_engine = MergeEngine(self._session)
        merge_result = await merge_engine.merge(
            source_branch=agent.branch_name,
            target_branch=task.branch_name,
            strategy="auto",
        )

        return merge_result

    async def complete_task(
        self,
        task_id: str,
        merge_to_main: bool = True,
        result_summary: str | None = None,
    ) -> dict:
        """Complete a task and optionally merge durable facts to main.

        Args:
            task_id: Task ID.
            merge_to_main: Whether to merge task branch to main.
            result_summary: Summary of task outcome.

        Returns:
            Dict with task status and optional merge result.
        """
        task = await self.get_task(task_id)

        # Mark task as completed
        await self._session.execute(
            update(Task)
            .where(Task.id == task_id)
            .values(
                status="completed",
                result_summary=result_summary,
                completed_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )

        merge_result = None
        if merge_to_main:
            # Commit ORM changes before merge (which uses DATA BRANCH operations)
            await self._session.commit()
            merge_engine = MergeEngine(self._session)
            merge_result = await merge_engine.merge(
                source_branch=task.branch_name,
                target_branch=task.parent_branch,
                strategy="auto",
            )
        else:
            await self._session.commit()

        return {
            "task_id": task_id,
            "status": "completed",
            "merge_result": merge_result,
        }

    async def replay_agent(
        self,
        agent_id: str,
        task_type: str | None = None,
        limit: int = 50,
    ) -> dict:
        """Replay an agent's full history across all tasks.

        Args:
            agent_id: Global agent identifier.
            task_type: Filter by task type.
            limit: Max items per section.

        Returns:
            Dict with tasks participated in, observations timeline, facts created.
        """
        # Get all task_agent records for this agent
        stmt = (
            select(TaskAgent)
            .where(TaskAgent.agent_id == agent_id)
            .order_by(TaskAgent.joined_at)
        )
        result = await self._session.execute(stmt)
        task_agents = list(result.scalars().all())

        task_ids = [ta.task_id for ta in task_agents]

        # Get tasks (optionally filtered by type)
        if task_ids:
            task_stmt = select(Task).where(Task.id.in_(task_ids))
            if task_type:
                task_stmt = task_stmt.where(Task.task_type == task_type)
            task_result = await self._session.execute(task_stmt)
            tasks = list(task_result.scalars().all())
        else:
            tasks = []

        # Get observations by this agent across all branches
        obs_result = await self._session.execute(
            select(Observation)
            .where(Observation.agent_id == agent_id)
            .order_by(Observation.created_at.desc())
            .limit(limit)
        )
        observations = [
            {
                "id": o.id,
                "type": o.observation_type,
                "summary": o.summary,
                "tool_name": o.tool_name,
                "task_id": o.task_id,
                "session_id": o.session_id,
                "outcome": o.outcome,
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in obs_result.scalars().all()
        ]

        # Get facts created by this agent
        fact_result = await self._session.execute(
            select(Fact)
            .where(Fact.agent_id == agent_id, Fact.status == "active")
            .order_by(Fact.created_at.desc())
            .limit(limit)
        )
        facts = [
            {
                "id": f.id,
                "fact_text": f.fact_text,
                "category": f.category,
                "task_id": f.task_id,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in fact_result.scalars().all()
        ]

        return {
            "agent_id": agent_id,
            "tasks": [
                {
                    "id": t.id,
                    "name": t.name,
                    "task_type": t.task_type,
                    "status": t.status,
                    "role": next(
                        (ta.role for ta in task_agents if ta.task_id == t.id),
                        None,
                    ),
                    "summary": next(
                        (ta.summary for ta in task_agents if ta.task_id == t.id),
                        None,
                    ),
                }
                for t in tasks
            ],
            "observations": observations,
            "facts": facts,
        }

    async def replay_task_type(
        self,
        task_type: str,
        limit: int = 20,
    ) -> dict:
        """Aggregate analysis of all tasks of a given type.

        Args:
            task_type: Task type to analyze.
            limit: Max tasks to include.

        Returns:
            Dict with task instances, patterns, and statistics.
        """
        result = await self._session.execute(
            select(Task)
            .where(Task.task_type == task_type)
            .order_by(Task.created_at.desc())
            .limit(limit)
        )
        tasks = list(result.scalars().all())

        task_summaries = []
        total_completed = 0
        total_failed = 0

        for task in tasks:
            if task.status == "completed":
                total_completed += 1
            elif task.status == "failed":
                total_failed += 1

            # Count agents per task
            agent_result = await self._session.execute(
                select(TaskAgent).where(TaskAgent.task_id == task.id)
            )
            agents = list(agent_result.scalars().all())

            task_summaries.append(
                {
                    "id": task.id,
                    "name": task.name,
                    "status": task.status,
                    "tags": task.tags,
                    "agent_count": len(agents),
                    "objective_count": len(task.objectives) if task.objectives else 0,
                    "result_summary": task.result_summary,
                    "created_at": (
                        task.created_at.isoformat() if task.created_at else None
                    ),
                    "completed_at": (
                        task.completed_at.isoformat() if task.completed_at else None
                    ),
                }
            )

        return {
            "task_type": task_type,
            "total": len(tasks),
            "completed": total_completed,
            "failed": total_failed,
            "success_rate": total_completed / max(len(tasks), 1),
            "tasks": task_summaries,
        }


def _slugify(text: str) -> str:
    """Convert text to URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")
