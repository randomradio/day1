"""CLI commands for memory operations: write, search, branch, snapshot, timeline, merge."""

from __future__ import annotations

import argparse

from day1.cli.commands.common import emit, get_active_branch, run_async, with_session


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    # ── write ─────────────────────────────────────────────────────────────
    write_cmd = subparsers.add_parser("write", help="Store a memory")
    write_cmd.add_argument("text", help="What happened (natural language)")
    write_cmd.add_argument("--context", help="Why / how / outcome")
    write_cmd.add_argument("--file", dest="file_context", help="Relevant file path")
    write_cmd.add_argument("--session-id", help="Session identifier")
    write_cmd.add_argument("--branch", help="Target branch (default: active)")
    write_cmd.add_argument("--category", help="Category (decision, pattern, bug_fix, ...)")
    write_cmd.add_argument("--confidence", type=float, default=0.7, help="Confidence 0-1")
    write_cmd.add_argument("--source-type", help="Source type")
    write_cmd.add_argument("--format", choices=["table", "json", "text"], default="table")
    write_cmd.set_defaults(_handler=cmd_write)

    # ── search ────────────────────────────────────────────────────────────
    search_cmd = subparsers.add_parser("search", help="Search memories")
    search_cmd.add_argument("query", help="Natural language search query")
    search_cmd.add_argument("--branch", help="Branch to search (default: active)")
    search_cmd.add_argument("--file", dest="file_context", help="Filter by file path")
    search_cmd.add_argument("--category", help="Filter by category")
    search_cmd.add_argument("--source-type", help="Filter by source type")
    search_cmd.add_argument("--status", help="Filter by status")
    search_cmd.add_argument("--limit", type=int, default=10, help="Max results")
    search_cmd.add_argument("--format", choices=["table", "json", "text"], default="table")
    search_cmd.set_defaults(_handler=cmd_search)

    # ── timeline ──────────────────────────────────────────────────────────
    timeline_cmd = subparsers.add_parser("timeline", help="Chronological memory history")
    timeline_cmd.add_argument("--branch", help="Branch (default: active)")
    timeline_cmd.add_argument("--category", help="Filter by category")
    timeline_cmd.add_argument("--source-type", help="Filter by source type")
    timeline_cmd.add_argument("--session-id", help="Filter by session")
    timeline_cmd.add_argument("--limit", type=int, default=20, help="Max results")
    timeline_cmd.add_argument("--format", choices=["table", "json", "text"], default="table")
    timeline_cmd.set_defaults(_handler=cmd_timeline)

    # ── branch ────────────────────────────────────────────────────────────
    branch_cmd = subparsers.add_parser("branch", help="Branch operations")
    branch_sub = branch_cmd.add_subparsers(dest="branch_action")

    branch_list = branch_sub.add_parser("list", help="List branches")
    branch_list.add_argument("--status", help="Filter by status")
    branch_list.add_argument("--format", choices=["table", "json", "text"], default="table")
    branch_list.set_defaults(_handler=cmd_branch_list)

    branch_create = branch_sub.add_parser("create", help="Create a branch")
    branch_create.add_argument("name", help="Branch name")
    branch_create.add_argument("--parent", default="main", help="Parent branch")
    branch_create.add_argument("--description", help="Branch description")
    branch_create.add_argument("--format", choices=["table", "json", "text"], default="table")
    branch_create.set_defaults(_handler=cmd_branch_create)

    branch_switch = branch_sub.add_parser("switch", help="Switch active branch")
    branch_switch.add_argument("name", help="Branch to switch to")
    branch_switch.set_defaults(_handler=cmd_branch_switch)

    branch_cmd.set_defaults(_handler=lambda a: cmd_branch_list(a))

    # ── merge ─────────────────────────────────────────────────────────────
    merge_cmd = subparsers.add_parser("merge", help="Merge branch into target")
    merge_cmd.add_argument("source", help="Source branch name")
    merge_cmd.add_argument("--into", default="main", help="Target branch (default: main)")
    merge_cmd.add_argument("--format", choices=["table", "json", "text"], default="table")
    merge_cmd.set_defaults(_handler=cmd_merge)

    # ── snapshot ──────────────────────────────────────────────────────────
    snap_cmd = subparsers.add_parser("snapshot", help="Snapshot operations")
    snap_sub = snap_cmd.add_subparsers(dest="snap_action")

    snap_create = snap_sub.add_parser("create", help="Create a snapshot")
    snap_create.add_argument("--label", help="Snapshot label")
    snap_create.add_argument("--branch", help="Branch to snapshot (default: active)")
    snap_create.add_argument("--format", choices=["table", "json", "text"], default="table")
    snap_create.set_defaults(_handler=cmd_snapshot_create)

    snap_list = snap_sub.add_parser("list", help="List snapshots")
    snap_list.add_argument("--branch", help="Filter by branch")
    snap_list.add_argument("--format", choices=["table", "json", "text"], default="table")
    snap_list.set_defaults(_handler=cmd_snapshot_list)

    snap_restore = snap_sub.add_parser("restore", help="View memories at snapshot time")
    snap_restore.add_argument("snapshot_id", help="Snapshot ID")
    snap_restore.add_argument("--format", choices=["table", "json", "text"], default="table")
    snap_restore.set_defaults(_handler=cmd_snapshot_restore)

    snap_cmd.set_defaults(_handler=lambda a: cmd_snapshot_list(a))

    # ── count ─────────────────────────────────────────────────────────────
    count_cmd = subparsers.add_parser("count", help="Count memories on a branch")
    count_cmd.add_argument("--branch", help="Branch (default: active)")
    count_cmd.add_argument("--format", choices=["table", "json", "text"], default="table")
    count_cmd.set_defaults(_handler=cmd_count)


# ── Command handlers ──────────────────────────────────────────────────────


def cmd_write(args: argparse.Namespace) -> int:
    async def _run(session):
        from day1.core.memory_engine import MemoryEngine

        engine = MemoryEngine(session)
        branch = args.branch or get_active_branch()
        mem = await engine.write(
            text=args.text,
            context=args.context,
            file_context=args.file_context,
            session_id=args.session_id,
            branch_name=branch,
            category=args.category,
            confidence=args.confidence,
            source_type=args.source_type,
        )
        emit(
            {
                "id": mem.id,
                "text": mem.text,
                "branch": mem.branch_name,
                "category": mem.category,
                "created_at": mem.created_at.isoformat() if mem.created_at else None,
            },
            getattr(args, "format", "table"),
        )

    return run_async(with_session(_run))


def cmd_search(args: argparse.Namespace) -> int:
    async def _run(session):
        from day1.core.memory_engine import MemoryEngine

        engine = MemoryEngine(session)
        branch = args.branch or get_active_branch()
        results = await engine.search(
            query=args.query,
            file_context=args.file_context,
            branch_name=branch,
            limit=args.limit,
            category=args.category,
            source_type=args.source_type,
            status=args.status,
        )
        emit({"results": results, "count": len(results)}, getattr(args, "format", "table"))

    return run_async(with_session(_run))


def cmd_timeline(args: argparse.Namespace) -> int:
    async def _run(session):
        from day1.core.memory_engine import MemoryEngine

        engine = MemoryEngine(session)
        branch = args.branch or get_active_branch()
        entries = await engine.timeline(
            branch_name=branch,
            limit=args.limit,
            category=args.category,
            source_type=args.source_type,
            session_id=args.session_id,
        )
        emit({"timeline": entries, "count": len(entries)}, getattr(args, "format", "table"))

    return run_async(with_session(_run))


def cmd_branch_list(args: argparse.Namespace) -> int:
    async def _run(session):
        from day1.core.memory_engine import MemoryEngine

        engine = MemoryEngine(session)
        branches = await engine.list_branches(status=getattr(args, "status", None))
        emit(
            {
                "branches": [
                    {
                        "branch_name": b.branch_name,
                        "parent_branch": b.parent_branch,
                        "status": b.status,
                        "description": b.description or "",
                    }
                    for b in branches
                ]
            },
            getattr(args, "format", "table"),
        )

    return run_async(with_session(_run))


def cmd_branch_create(args: argparse.Namespace) -> int:
    async def _run(session):
        from day1.core.memory_engine import MemoryEngine

        engine = MemoryEngine(session)
        branch = await engine.create_branch(
            branch_name=args.name,
            parent_branch=args.parent,
            description=args.description,
        )
        emit(
            {
                "branch_name": branch.branch_name,
                "parent_branch": branch.parent_branch,
                "status": branch.status,
            },
            getattr(args, "format", "table"),
        )

    return run_async(with_session(_run))


def cmd_branch_switch(args: argparse.Namespace) -> int:
    from day1.cli.commands.common import set_active_branch

    async def _run(session):
        from day1.core.memory_engine import MemoryEngine

        engine = MemoryEngine(session)
        await engine.get_branch(args.name)
        set_active_branch(args.name)
        print(f"Switched to branch: {args.name}")

    return run_async(with_session(_run))


def cmd_merge(args: argparse.Namespace) -> int:
    async def _run(session):
        from day1.core.memory_engine import MemoryEngine

        engine = MemoryEngine(session)
        result = await engine.merge_branch(
            source_branch=args.source,
            target_branch=args.into,
        )
        emit(result, getattr(args, "format", "table"))

    return run_async(with_session(_run))


def cmd_snapshot_create(args: argparse.Namespace) -> int:
    async def _run(session):
        from day1.core.memory_engine import MemoryEngine

        engine = MemoryEngine(session)
        branch = args.branch or get_active_branch()
        snap = await engine.create_snapshot(branch_name=branch, label=args.label)
        emit(
            {
                "snapshot_id": snap.id,
                "label": snap.label,
                "branch_name": snap.branch_name,
                "created_at": snap.created_at.isoformat() if snap.created_at else None,
            },
            getattr(args, "format", "table"),
        )

    return run_async(with_session(_run))


def cmd_snapshot_list(args: argparse.Namespace) -> int:
    async def _run(session):
        from day1.core.memory_engine import MemoryEngine

        engine = MemoryEngine(session)
        snaps = await engine.list_snapshots(branch_name=getattr(args, "branch", None))
        emit(
            {
                "snapshots": [
                    {
                        "id": s.id,
                        "label": s.label,
                        "branch_name": s.branch_name,
                        "created_at": s.created_at.isoformat() if s.created_at else None,
                    }
                    for s in snaps
                ]
            },
            getattr(args, "format", "table"),
        )

    return run_async(with_session(_run))


def cmd_snapshot_restore(args: argparse.Namespace) -> int:
    async def _run(session):
        from day1.core.memory_engine import MemoryEngine

        engine = MemoryEngine(session)
        result = await engine.restore_snapshot(args.snapshot_id)
        emit(result, getattr(args, "format", "table"))

    return run_async(with_session(_run))


def cmd_count(args: argparse.Namespace) -> int:
    async def _run(session):
        from day1.core.memory_engine import MemoryEngine

        engine = MemoryEngine(session)
        branch = args.branch or get_active_branch()
        cnt = await engine.count(branch_name=branch)
        emit({"branch": branch, "count": cnt}, getattr(args, "format", "table"))

    return run_async(with_session(_run))
