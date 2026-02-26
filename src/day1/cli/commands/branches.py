"""Branch lifecycle CLI commands."""

from __future__ import annotations

import argparse
from typing import Any

from day1.cli.commands.common import emit, run_async, set_active_branch, with_session
from day1.core.branch_manager import BranchManager


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    branch = subparsers.add_parser("branch", help="Branch operations")
    branch_sub = branch.add_subparsers(dest="branch_command")

    create = branch_sub.add_parser("create", help="Create a branch")
    create.add_argument("branch_name")
    create.add_argument("--parent", default="main")
    create.add_argument("--description")
    create.add_argument("--format", choices=["table", "json"], default="table")
    create.set_defaults(_handler=cmd_branch_create, command="branch")

    list_cmd = branch_sub.add_parser("list", help="List branches")
    list_cmd.add_argument("--status")
    list_cmd.add_argument("--format", choices=["table", "json"], default="table")
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
    switch.add_argument("--format", choices=["table", "json"], default="table")
    switch.set_defaults(_handler=cmd_branch_switch, command="branch")


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
                f"export BM_DEFAULT_BRANCH={args.branch_name}"
                if args.print_export
                else "Use --print-export to print a shell export command."
            ),
        }
        return payload

    result = await with_session(_run)
    emit(result, args.format)
    if args.print_export:
        print(f"export BM_DEFAULT_BRANCH={args.branch_name}")
    return 0
