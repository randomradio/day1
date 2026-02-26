"""Task management CLI commands."""

from __future__ import annotations

import argparse
from typing import Any

from day1.cli.commands.common import emit, parse_json_list_arg, run_async, with_session
from day1.core.task_engine import TaskEngine


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    create = subparsers.add_parser("create-task", help="Create a task")
    create.add_argument("name")
    create.add_argument("--description")
    create.add_argument("--type", dest="task_type")
    create.add_argument("--tag", dest="tags", action="append", default=[])
    create.add_argument("--tags-json", help="JSON array of strings")
    create.add_argument("--objective", dest="objectives", action="append", default=[])
    create.add_argument(
        "--objectives-json",
        help='JSON array of strings or [{"description":"..."}]',
    )
    create.add_argument("--parent-branch", default="main")
    create.add_argument("--format", choices=["table", "json", "text"], default="table")
    create.set_defaults(_handler=cmd_create_task)

    join = subparsers.add_parser("join-task", help="Join an agent to a task")
    join.add_argument("task_id")
    join.add_argument("--agent-id", required=True)
    join.add_argument("--role")
    join.add_argument(
        "--objective-id", dest="objective_ids", action="append", type=int, default=[]
    )
    join.add_argument("--objectives-json", help="JSON array of integers")
    join.add_argument("--format", choices=["table", "json", "text"], default="table")
    join.set_defaults(_handler=cmd_join_task)

    status = subparsers.add_parser("task-status", help="Show task status/context")
    status.add_argument("task_id")
    status.add_argument("--format", choices=["table", "json", "text"], default="table")
    status.set_defaults(_handler=cmd_task_status)

    update = subparsers.add_parser("task-update", help="Update a task objective")
    update.add_argument("task_id")
    update.add_argument("--objective-id", type=int)
    update.add_argument(
        "--objective-status",
        choices=["done", "active", "todo", "blocked"],
    )
    update.add_argument("--agent-id")
    update.add_argument("--notes")
    update.add_argument("--format", choices=["table", "json", "text"], default="table")
    update.set_defaults(_handler=cmd_task_update)


def _build_objectives(args: argparse.Namespace) -> list[dict[str, Any]] | None:
    if args.objectives_json:
        parsed = parse_json_list_arg(args.objectives_json) or []
        result: list[dict[str, Any]] = []
        for item in parsed:
            if isinstance(item, dict):
                result.append(item)
            else:
                result.append({"description": str(item)})
        return result
    if args.objectives:
        return [{"description": text} for text in args.objectives]
    return None


def _build_tags(args: argparse.Namespace) -> list[str] | None:
    if args.tags_json:
        parsed = parse_json_list_arg(args.tags_json) or []
        return [str(x) for x in parsed]
    if args.tags:
        return [str(x) for x in args.tags]
    return None


def cmd_create_task(args: argparse.Namespace) -> int:
    return run_async(_cmd_create_task(args))


async def _cmd_create_task(args: argparse.Namespace) -> int:
    objectives = _build_objectives(args)
    tags = _build_tags(args)

    async def _run(session: Any) -> dict[str, Any]:
        engine = TaskEngine(session)
        task = await engine.create_task(
            name=args.name,
            description=args.description,
            task_type=args.task_type,
            tags=tags,
            objectives=objectives,
            parent_branch=args.parent_branch,
        )
        return {
            "task_id": task.id,
            "name": task.name,
            "task_type": task.task_type,
            "status": task.status,
            "branch_name": task.branch_name,
            "parent_branch": task.parent_branch,
            "objectives": task.objectives or [],
            "created_at": task.created_at.isoformat() if task.created_at else None,
        }

    emit(await with_session(_run), args.format)
    return 0


def cmd_join_task(args: argparse.Namespace) -> int:
    return run_async(_cmd_join_task(args))


async def _cmd_join_task(args: argparse.Namespace) -> int:
    objective_ids = args.objective_ids or []
    if args.objectives_json:
        objective_ids = [
            int(x) for x in (parse_json_list_arg(args.objectives_json) or [])
        ]

    async def _run(session: Any) -> dict[str, Any]:
        engine = TaskEngine(session)
        return await engine.join_task(
            task_id=args.task_id,
            agent_id=args.agent_id,
            role=args.role,
            assigned_objectives=objective_ids or None,
        )

    emit(await with_session(_run), args.format)
    return 0


def cmd_task_status(args: argparse.Namespace) -> int:
    return run_async(_cmd_task_status(args))


async def _cmd_task_status(args: argparse.Namespace) -> int:
    async def _run(session: Any) -> dict[str, Any]:
        return await TaskEngine(session).get_task_context(args.task_id)

    emit(await with_session(_run), args.format)
    return 0


def cmd_task_update(args: argparse.Namespace) -> int:
    return run_async(_cmd_task_update(args))


async def _cmd_task_update(args: argparse.Namespace) -> int:
    if not args.objective_id or not args.objective_status:
        raise ValueError("--objective-id and --objective-status are required")

    async def _run(session: Any) -> dict[str, Any]:
        task = await TaskEngine(session).update_objective(
            task_id=args.task_id,
            objective_id=args.objective_id,
            status=args.objective_status,
            agent_id=args.agent_id,
            notes=args.notes,
        )
        return {"task_id": task.id, "objectives": task.objectives or []}

    emit(await with_session(_run), args.format)
    return 0
