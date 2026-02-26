"""Branch lifecycle CLI commands."""

from __future__ import annotations

import argparse
from typing import Any

from day1.cli.commands.common import emit, run_async, set_active_branch, with_session
from day1.core.branch_manager import BranchManager
from day1.core.merge_engine import MergeEngine


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    branch = subparsers.add_parser("branch", help="Branch operations")
    branch_sub = branch.add_subparsers(dest="branch_command")

    create = branch_sub.add_parser("create", help="Create a branch")
    create.add_argument("branch_name")
    create.add_argument("--parent", default="main")
    create.add_argument("--description")
    create.add_argument("--format", choices=["table", "json", "text"], default="table")
    create.set_defaults(_handler=cmd_branch_create, command="branch")

    list_cmd = branch_sub.add_parser("list", help="List branches")
    list_cmd.add_argument("--status")
    list_cmd.add_argument(
        "--format", choices=["table", "json", "text"], default="table"
    )
    list_cmd.set_defaults(_handler=cmd_branch_list, command="branch")

    switch = branch_sub.add_parser(
        "switch",
        help="Switch active branch for this CLI process",
    )
    switch.add_argument("branch_name")
    switch.add_argument(
        "--print-export",
        action="store_true",
        help="Print shell export command for manual persistence",
    )
    switch.add_argument("--format", choices=["table", "json", "text"], default="table")
    switch.set_defaults(_handler=cmd_branch_switch, command="branch")

    diff_cmd = branch_sub.add_parser("diff", help="Diff two branches")
    diff_cmd.add_argument("source_branch")
    diff_cmd.add_argument("target_branch")
    diff_cmd.add_argument("--category")
    diff_cmd.add_argument(
        "--format", choices=["table", "json", "text"], default="table"
    )
    diff_cmd.set_defaults(_handler=cmd_branch_diff, command="branch")

    merge_cmd = branch_sub.add_parser("merge", help="Merge branches")
    merge_cmd.add_argument("source_branch")
    merge_cmd.add_argument(
        "--into", "--target-branch", dest="target_branch", default="main"
    )
    merge_cmd.add_argument(
        "--strategy",
        choices=["auto", "cherry_pick", "squash", "native"],
        default="auto",
    )
    merge_cmd.add_argument("--item", dest="items", action="append", default=[])
    merge_cmd.add_argument("--conflict", choices=["skip", "accept"], default="skip")
    merge_cmd.add_argument(
        "--format", choices=["table", "json", "text"], default="table"
    )
    merge_cmd.set_defaults(_handler=cmd_branch_merge, command="branch")


def cmd_branch_create(args: argparse.Namespace) -> int:
    return run_async(_cmd_branch_create(args))


async def _cmd_branch_create(args: argparse.Namespace) -> int:
    async def _run(session: Any) -> dict[str, Any]:
        mgr = BranchManager(session)
        branch = await mgr.create_branch(
            branch_name=args.branch_name,
            parent_branch=args.parent,
            description=args.description,
        )
        return {
            "branch_name": branch.branch_name,
            "parent_branch": branch.parent_branch,
            "status": branch.status,
            "forked_at": branch.forked_at.isoformat() if branch.forked_at else None,
        }

    emit(await with_session(_run), args.format)
    return 0


def cmd_branch_list(args: argparse.Namespace) -> int:
    return run_async(_cmd_branch_list(args))


async def _cmd_branch_list(args: argparse.Namespace) -> int:
    async def _run(session: Any) -> dict[str, Any]:
        mgr = BranchManager(session)
        branches = await mgr.list_branches(status=args.status)
        return {
            "branches": [
                {
                    "branch_name": b.branch_name,
                    "parent_branch": b.parent_branch,
                    "status": b.status,
                    "description": b.description,
                    "forked_at": b.forked_at.isoformat() if b.forked_at else None,
                }
                for b in branches
            ]
        }

    emit(await with_session(_run), args.format)
    return 0


def cmd_branch_switch(args: argparse.Namespace) -> int:
    return run_async(_cmd_branch_switch(args))


async def _cmd_branch_switch(args: argparse.Namespace) -> int:
    async def _run(session: Any) -> dict[str, Any]:
        mgr = BranchManager(session)
        await mgr.get_branch(args.branch_name)
        set_active_branch(args.branch_name)
        payload = {
            "active_branch": args.branch_name,
            "persist_hint": (
                f"export BM_BRANCH={args.branch_name}"
                if args.print_export
                else "Use --print-export to print a shell export command."
            ),
        }
        return payload

    result = await with_session(_run)
    emit(result, args.format)
    if args.print_export:
        print(f"export BM_BRANCH={args.branch_name}")
    return 0


def cmd_branch_diff(args: argparse.Namespace) -> int:
    return run_async(_cmd_branch_diff(args))


async def _cmd_branch_diff(args: argparse.Namespace) -> int:
    async def _run(session: Any) -> dict[str, Any]:
        diff = await MergeEngine(session).diff(
            source_branch=args.source_branch,
            target_branch=args.target_branch,
            category=args.category,
        )
        return {
            "source_branch": args.source_branch,
            "target_branch": args.target_branch,
            **diff.to_dict(),
        }

    emit(await with_session(_run), args.format)
    return 0


def cmd_branch_merge(args: argparse.Namespace) -> int:
    return run_async(_cmd_branch_merge(args))


async def _cmd_branch_merge(args: argparse.Namespace) -> int:
    async def _run(session: Any) -> dict[str, Any]:
        return await MergeEngine(session).merge(
            source_branch=args.source_branch,
            target_branch=args.target_branch,
            strategy=args.strategy,
            items=args.items or None,
            conflict=args.conflict,
        )

    emit(await with_session(_run), args.format)
    return 0
