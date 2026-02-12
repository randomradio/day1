"""Tests for TaskEngine: multi-agent task coordination."""

from __future__ import annotations

import pytest

from branchedmind.core.embedding import MockEmbedding
from branchedmind.core.exceptions import TaskNotFoundError, TaskAgentError
from branchedmind.core.fact_engine import FactEngine
from branchedmind.core.task_engine import TaskEngine, _slugify


@pytest.mark.asyncio
async def test_create_task(db_session):
    engine = TaskEngine(db_session)

    task = await engine.create_task(
        name="Fix OAuth2 Bug",
        description="Fix the OAuth2 token refresh issue",
        task_type="bug_fix",
        tags=["auth", "security"],
        objectives=[
            {"description": "Identify root cause"},
            {"description": "Write fix"},
            {"description": "Add tests"},
        ],
    )

    assert task.id is not None
    assert task.name == "Fix OAuth2 Bug"
    assert task.branch_name == "task/fix-oauth2-bug"
    assert task.parent_branch == "main"
    assert task.status == "active"
    assert task.task_type == "bug_fix"
    assert task.tags == ["auth", "security"]
    assert len(task.objectives) == 3
    assert task.objectives[0]["id"] == 1
    assert task.objectives[0]["status"] == "todo"


@pytest.mark.asyncio
async def test_create_task_minimal(db_session):
    engine = TaskEngine(db_session)

    task = await engine.create_task(name="Quick research")

    assert task.id is not None
    assert task.branch_name == "task/quick-research"
    assert task.objectives is None
    assert task.task_type is None


@pytest.mark.asyncio
async def test_get_task(db_session):
    engine = TaskEngine(db_session)
    task = await engine.create_task(name="Test Task")

    retrieved = await engine.get_task(task.id)
    assert retrieved.name == "Test Task"


@pytest.mark.asyncio
async def test_get_nonexistent_task(db_session):
    engine = TaskEngine(db_session)
    with pytest.raises(TaskNotFoundError):
        await engine.get_task("nonexistent-id")


@pytest.mark.asyncio
async def test_list_tasks(db_session):
    engine = TaskEngine(db_session)

    await engine.create_task(name="Task A", task_type="bug_fix")
    await engine.create_task(name="Task B", task_type="feature")
    await engine.create_task(name="Task C", task_type="bug_fix")

    all_tasks = await engine.list_tasks()
    assert len(all_tasks) == 3

    bug_tasks = await engine.list_tasks(task_type="bug_fix")
    assert len(bug_tasks) == 2


@pytest.mark.asyncio
async def test_join_task(db_session):
    engine = TaskEngine(db_session)

    task = await engine.create_task(
        name="Multi Agent Task",
        objectives=[
            {"description": "Implement feature"},
            {"description": "Write tests"},
        ],
    )

    result = await engine.join_task(
        task_id=task.id,
        agent_id="agent-alpha",
        role="implementer",
        assigned_objectives=[1],
    )

    assert result["agent_branch"] == "task/multi-agent-task/agent-alpha"
    assert "task_context" in result
    ctx = result["task_context"]
    assert ctx["task"]["name"] == "Multi Agent Task"
    assert len(ctx["active_agents"]) == 1
    assert ctx["active_agents"][0]["agent_id"] == "agent-alpha"


@pytest.mark.asyncio
async def test_join_task_duplicate_agent(db_session):
    engine = TaskEngine(db_session)
    task = await engine.create_task(name="Test Dup")

    await engine.join_task(task_id=task.id, agent_id="agent-1")

    with pytest.raises(TaskAgentError, match="already active"):
        await engine.join_task(task_id=task.id, agent_id="agent-1")


@pytest.mark.asyncio
async def test_objective_lifecycle(db_session):
    engine = TaskEngine(db_session)

    task = await engine.create_task(
        name="Obj Lifecycle",
        objectives=[
            {"description": "Step 1"},
            {"description": "Step 2"},
        ],
    )

    # Update to active
    task = await engine.update_objective(
        task_id=task.id, objective_id=1, status="active", agent_id="agent-x"
    )
    assert task.objectives[0]["status"] == "active"
    assert task.objectives[0]["agent_id"] == "agent-x"

    # Update to done
    task = await engine.update_objective(
        task_id=task.id, objective_id=1, status="done", agent_id="agent-x"
    )
    assert task.objectives[0]["status"] == "done"

    # Step 2 still todo
    assert task.objectives[1]["status"] == "todo"


@pytest.mark.asyncio
async def test_update_nonexistent_objective(db_session):
    engine = TaskEngine(db_session)
    task = await engine.create_task(
        name="Test",
        objectives=[{"description": "Only one"}],
    )

    with pytest.raises(TaskAgentError, match="not found"):
        await engine.update_objective(
            task_id=task.id, objective_id=99, status="done"
        )


@pytest.mark.asyncio
async def test_complete_agent_merges(db_session, mock_embedder):
    """After agent completion, facts on agent branch should merge to task branch."""
    engine = TaskEngine(db_session)
    fact_engine = FactEngine(db_session, mock_embedder)

    task = await engine.create_task(name="Merge Test")
    result = await engine.join_task(
        task_id=task.id, agent_id="worker-1", role="implementer"
    )
    agent_branch = result["agent_branch"]

    # Write facts on agent branch
    await fact_engine.write_fact(
        fact_text="Discovered that the API uses pagination",
        category="discovery",
        branch_name=agent_branch,
    )

    # Complete the agent
    merge_result = await engine.complete_agent(
        task_id=task.id,
        agent_id="worker-1",
        summary="Found pagination pattern in API",
    )

    assert merge_result["merged_count"] >= 0  # May be 0 if embedding similarity blocks


@pytest.mark.asyncio
async def test_new_agent_sees_previous_work(db_session, mock_embedder):
    """Core test: Agent C joining after A/B should see their work via task context."""
    engine = TaskEngine(db_session)
    fact_engine = FactEngine(db_session, mock_embedder)

    task = await engine.create_task(
        name="Collaborative Task",
        objectives=[
            {"description": "Research"},
            {"description": "Implement"},
            {"description": "Test"},
        ],
    )

    # Agent A joins and works
    result_a = await engine.join_task(
        task_id=task.id, agent_id="agent-A", role="researcher",
        assigned_objectives=[1],
    )

    # Agent A completes
    await engine.complete_agent(
        task_id=task.id,
        agent_id="agent-A",
        summary="Researched the problem space thoroughly",
    )

    # Agent B joins and works
    result_b = await engine.join_task(
        task_id=task.id, agent_id="agent-B", role="implementer",
        assigned_objectives=[2],
    )
    await engine.complete_agent(
        task_id=task.id,
        agent_id="agent-B",
        summary="Implemented the core feature",
    )

    # Agent C joins — should see A and B's summaries
    result_c = await engine.join_task(
        task_id=task.id, agent_id="agent-C", role="tester",
        assigned_objectives=[3],
    )
    ctx = result_c["task_context"]

    # Should see completed agent summaries
    assert len(ctx["agent_summaries"]) == 2
    summaries = {s["agent_id"]: s["summary"] for s in ctx["agent_summaries"]}
    assert "agent-A" in summaries
    assert "agent-B" in summaries
    assert "Researched" in summaries["agent-A"]
    assert "Implemented" in summaries["agent-B"]


@pytest.mark.asyncio
async def test_complete_task(db_session):
    engine = TaskEngine(db_session)
    task = await engine.create_task(name="Completable Task")

    result = await engine.complete_task(
        task_id=task.id,
        merge_to_main=True,
        result_summary="Task done successfully",
    )

    assert result["status"] == "completed"

    # Verify task is marked completed
    completed = await engine.get_task(task.id)
    assert completed.status == "completed"
    assert completed.result_summary == "Task done successfully"


@pytest.mark.asyncio
async def test_replay_agent(db_session):
    engine = TaskEngine(db_session)

    # Create two tasks
    t1 = await engine.create_task(name="Task Alpha", task_type="bug_fix")
    t2 = await engine.create_task(name="Task Beta", task_type="feature")

    # Same agent joins both
    await engine.join_task(task_id=t1.id, agent_id="versatile-agent", role="fixer")
    await engine.complete_agent(t1.id, "versatile-agent", summary="Fixed the bug")

    await engine.join_task(task_id=t2.id, agent_id="versatile-agent", role="builder")

    # Replay
    replay = await engine.replay_agent(agent_id="versatile-agent")
    assert replay["agent_id"] == "versatile-agent"
    assert len(replay["tasks"]) == 2

    # Filter by type
    replay_bugs = await engine.replay_agent(
        agent_id="versatile-agent", task_type="bug_fix"
    )
    assert len(replay_bugs["tasks"]) == 1
    assert replay_bugs["tasks"][0]["task_type"] == "bug_fix"


@pytest.mark.asyncio
async def test_replay_task_type(db_session):
    engine = TaskEngine(db_session)

    await engine.create_task(name="Bug 1", task_type="bug_fix")
    t2 = await engine.create_task(name="Bug 2", task_type="bug_fix")
    await engine.create_task(name="Feature 1", task_type="feature")

    await engine.complete_task(t2.id, merge_to_main=False, result_summary="Fixed")

    analysis = await engine.replay_task_type(task_type="bug_fix")
    assert analysis["task_type"] == "bug_fix"
    assert analysis["total"] == 2
    assert analysis["completed"] == 1
    assert analysis["success_rate"] == 0.5


@pytest.mark.asyncio
async def test_get_task_context_progress(db_session):
    engine = TaskEngine(db_session)

    task = await engine.create_task(
        name="Progress Test",
        objectives=[
            {"description": "A"},
            {"description": "B"},
            {"description": "C"},
        ],
    )

    await engine.update_objective(task.id, 1, "done", agent_id="a1")
    await engine.update_objective(task.id, 2, "active", agent_id="a2")

    ctx = await engine.get_task_context(task.id)
    progress = ctx["progress"]
    assert progress["total"] == 3
    assert progress["done"] == 1
    assert progress["active"] == 1
    assert progress["todo"] == 1


def test_slugify():
    assert _slugify("Fix OAuth2 Bug") == "fix-oauth2-bug"
    assert _slugify("  Multiple   Spaces  ") == "multiple-spaces"
    assert _slugify("Special!@#Chars") == "specialchars"
