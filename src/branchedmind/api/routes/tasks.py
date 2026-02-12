"""REST API routes for tasks and multi-agent coordination."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from branchedmind.core.consolidation_engine import ConsolidationEngine
from branchedmind.core.exceptions import TaskNotFoundError, TaskAgentError
from branchedmind.core.task_engine import TaskEngine
from branchedmind.db.engine import get_session

router = APIRouter()


# --- Request/Response models ---


class TaskCreate(BaseModel):
    name: str
    description: str | None = None
    task_type: str | None = None
    tags: list[str] | None = None
    objectives: list[dict] | None = None
    parent_branch: str = "main"


class TaskJoin(BaseModel):
    agent_id: str
    role: str | None = None
    assigned_objectives: list[int] | None = None


class ObjectiveUpdate(BaseModel):
    status: str
    agent_id: str | None = None
    notes: str | None = None


class TaskComplete(BaseModel):
    merge_to_main: bool = True
    result_summary: str | None = None


class AgentComplete(BaseModel):
    summary: str | None = None


class ConsolidateRequest(BaseModel):
    level: str = "session"  # session, agent, task
    session_id: str | None = None
    agent_id: str | None = None
    branch_name: str | None = None


class TaskResponse(BaseModel):
    id: str
    name: str
    description: str | None
    branch_name: str
    parent_branch: str
    status: str
    task_type: str | None
    tags: list | None
    objectives: list | None
    created_at: str | None

    model_config = {"from_attributes": True}


# --- Task CRUD ---


@router.post("/tasks", response_model=TaskResponse)
async def create_task(
    body: TaskCreate,
    session: AsyncSession = Depends(get_session),
):
    engine = TaskEngine(session)
    task = await engine.create_task(
        name=body.name,
        description=body.description,
        task_type=body.task_type,
        tags=body.tags,
        objectives=body.objectives,
        parent_branch=body.parent_branch,
    )
    return TaskResponse(
        id=task.id,
        name=task.name,
        description=task.description,
        branch_name=task.branch_name,
        parent_branch=task.parent_branch,
        status=task.status,
        task_type=task.task_type,
        tags=task.tags,
        objectives=task.objectives,
        created_at=task.created_at.isoformat() if task.created_at else None,
    )


@router.get("/tasks")
async def list_tasks(
    status: str | None = None,
    task_type: str | None = None,
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
):
    engine = TaskEngine(session)
    tasks = await engine.list_tasks(
        status=status, task_type=task_type, limit=limit
    )
    return {
        "tasks": [
            TaskResponse(
                id=t.id,
                name=t.name,
                description=t.description,
                branch_name=t.branch_name,
                parent_branch=t.parent_branch,
                status=t.status,
                task_type=t.task_type,
                tags=t.tags,
                objectives=t.objectives,
                created_at=t.created_at.isoformat() if t.created_at else None,
            ).model_dump()
            for t in tasks
        ]
    }


@router.get("/tasks/{task_id}")
async def get_task(
    task_id: str,
    session: AsyncSession = Depends(get_session),
):
    engine = TaskEngine(session)
    try:
        context = await engine.get_task_context(task_id)
    except TaskNotFoundError:
        raise HTTPException(status_code=404, detail="Task not found")
    return context


# --- Agent operations ---


@router.post("/tasks/{task_id}/join")
async def join_task(
    task_id: str,
    body: TaskJoin,
    session: AsyncSession = Depends(get_session),
):
    engine = TaskEngine(session)
    try:
        result = await engine.join_task(
            task_id=task_id,
            agent_id=body.agent_id,
            role=body.role,
            assigned_objectives=body.assigned_objectives,
        )
    except TaskNotFoundError:
        raise HTTPException(status_code=404, detail="Task not found")
    except TaskAgentError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return result


@router.post("/tasks/{task_id}/agents/{agent_id}/complete")
async def complete_agent(
    task_id: str,
    agent_id: str,
    body: AgentComplete,
    session: AsyncSession = Depends(get_session),
):
    engine = TaskEngine(session)
    try:
        result = await engine.complete_agent(
            task_id=task_id,
            agent_id=agent_id,
            summary=body.summary,
        )
    except (TaskNotFoundError, TaskAgentError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result


# --- Objective management ---


@router.patch("/tasks/{task_id}/objectives/{objective_id}")
async def update_objective(
    task_id: str,
    objective_id: int,
    body: ObjectiveUpdate,
    session: AsyncSession = Depends(get_session),
):
    engine = TaskEngine(session)
    try:
        task = await engine.update_objective(
            task_id=task_id,
            objective_id=objective_id,
            status=body.status,
            agent_id=body.agent_id,
            notes=body.notes,
        )
    except TaskNotFoundError:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "task_id": task.id,
        "objectives": task.objectives,
    }


# --- Task completion ---


@router.post("/tasks/{task_id}/complete")
async def complete_task(
    task_id: str,
    body: TaskComplete,
    session: AsyncSession = Depends(get_session),
):
    engine = TaskEngine(session)
    try:
        result = await engine.complete_task(
            task_id=task_id,
            merge_to_main=body.merge_to_main,
            result_summary=body.result_summary,
        )
    except TaskNotFoundError:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


# --- Consolidation ---


@router.post("/tasks/{task_id}/consolidate")
async def consolidate(
    task_id: str,
    body: ConsolidateRequest,
    session: AsyncSession = Depends(get_session),
):
    consolidator = ConsolidationEngine(session)
    try:
        if body.level == "session" and body.session_id:
            result = await consolidator.consolidate_session(
                session_id=body.session_id,
                branch_name=body.branch_name or "main",
                task_id=task_id,
                agent_id=body.agent_id,
            )
        elif body.level == "agent" and body.agent_id:
            result = await consolidator.consolidate_agent(
                task_id=task_id,
                agent_id=body.agent_id,
            )
        elif body.level == "task":
            result = await consolidator.consolidate_task(task_id=task_id)
        else:
            raise HTTPException(
                status_code=400,
                detail="Invalid consolidation level or missing required fields",
            )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


# --- Replay & Analysis ---


@router.get("/agents/{agent_id}/timeline")
async def agent_timeline(
    agent_id: str,
    task_type: str | None = None,
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
):
    engine = TaskEngine(session)
    result = await engine.replay_agent(
        agent_id=agent_id,
        task_type=task_type,
        limit=limit,
    )
    return result


@router.get("/tasks/types/{task_type}/analysis")
async def task_type_analysis(
    task_type: str,
    limit: int = 10,
    session: AsyncSession = Depends(get_session),
):
    engine = TaskEngine(session)
    result = await engine.replay_task_type(
        task_type=task_type,
        limit=limit,
    )
    return result
