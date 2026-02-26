"""Memory write/search/snapshot CLI commands."""

from __future__ import annotations

import argparse
from typing import Any

from day1.cli.commands.common import (
    emit,
    get_active_branch,
    parse_json_arg,
    run_async,
    with_session,
)
from day1.core.consolidation_engine import ConsolidationEngine
from day1.core.embedding import get_embedding_provider
from day1.core.fact_engine import FactEngine
from day1.core.observation_engine import ObservationEngine
from day1.core.relation_engine import RelationEngine
from day1.core.search_engine import SearchEngine
from day1.core.snapshot_manager import SnapshotManager


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    write_fact = subparsers.add_parser("write-fact", help="Write a fact")
    write_fact.add_argument("fact_text")
    write_fact.add_argument("--category")
    write_fact.add_argument("--confidence", type=float, default=1.0)
    write_fact.add_argument("--branch")
    write_fact.add_argument("--session-id")
    write_fact.add_argument("--metadata", help="JSON object")
    write_fact.add_argument(
        "--format", choices=["table", "json", "text"], default="table"
    )
    write_fact.set_defaults(_handler=cmd_write_fact)

    write_obs = subparsers.add_parser("write-observation", help="Write an observation")
    write_obs.add_argument("summary")
    write_obs.add_argument("--observation-type", default="tool_use")
    write_obs.add_argument("--session-id", default="cli-session")
    write_obs.add_argument("--tool-name")
    write_obs.add_argument("--branch")
    write_obs.add_argument("--metadata", help="JSON object")
    write_obs.add_argument(
        "--format", choices=["table", "json", "text"], default="table"
    )
    write_obs.set_defaults(_handler=cmd_write_observation)

    write_rel = subparsers.add_parser("write-relation", help="Write a relation edge")
    write_rel.add_argument("source_entity")
    write_rel.add_argument("relation_type")
    write_rel.add_argument("target_entity")
    write_rel.add_argument("--branch")
    write_rel.add_argument("--session-id")
    write_rel.add_argument("--confidence", type=float, default=1.0)
    write_rel.add_argument("--properties", help="JSON object")
    write_rel.add_argument(
        "--format", choices=["table", "json", "text"], default="table"
    )
    write_rel.set_defaults(_handler=cmd_write_relation)

    search = subparsers.add_parser("search", help="Search facts")
    search.add_argument("query")
    search.add_argument("--branch")
    search.add_argument(
        "--search-type",
        default="keyword",
        choices=["keyword", "hybrid", "vector"],
    )
    search.add_argument("--category")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--format", choices=["table", "json", "text"], default="table")
    search.set_defaults(_handler=cmd_search)

    graph = subparsers.add_parser("graph-query", help="Query relation graph")
    graph.add_argument("entity")
    graph.add_argument("--relation-type")
    graph.add_argument("--depth", type=int, default=1)
    graph.add_argument("--branch")
    graph.add_argument("--format", choices=["table", "json", "text"], default="table")
    graph.set_defaults(_handler=cmd_graph_query)

    timeline = subparsers.add_parser("timeline", help="Show fact/observation timeline")
    timeline.add_argument("--session-id")
    timeline.add_argument("--branch")
    timeline.add_argument("--after")
    timeline.add_argument("--before")
    timeline.add_argument("--limit", type=int, default=50)
    timeline.add_argument(
        "--format", choices=["table", "json", "text"], default="table"
    )
    timeline.set_defaults(_handler=cmd_timeline)

    snapshot = subparsers.add_parser("snapshot", help="Create or list snapshots")
    snapshot_sub = snapshot.add_subparsers(dest="snapshot_command")

    snapshot_create = snapshot_sub.add_parser("create", help="Create snapshot")
    snapshot_create.add_argument("--branch")
    snapshot_create.add_argument("--label")
    snapshot_create.add_argument("--native", action="store_true")
    snapshot_create.add_argument(
        "--format", choices=["table", "json", "text"], default="table"
    )
    snapshot_create.set_defaults(_handler=cmd_snapshot_create, command="snapshot")

    snapshot_list = snapshot_sub.add_parser("list", help="List snapshots")
    snapshot_list.add_argument("--branch")
    snapshot_list.add_argument(
        "--format", choices=["table", "json", "text"], default="table"
    )
    snapshot_list.set_defaults(_handler=cmd_snapshot_list, command="snapshot")

    time_travel = subparsers.add_parser(
        "time-travel",
        help="Query facts at a timestamp",
    )
    time_travel.add_argument("timestamp")
    time_travel.add_argument("--branch")
    time_travel.add_argument("--query")
    time_travel.add_argument("--category")
    time_travel.add_argument("--limit", type=int, default=20)
    time_travel.add_argument(
        "--format", choices=["table", "json", "text"], default="table"
    )
    time_travel.set_defaults(_handler=cmd_time_travel)

    consolidate = subparsers.add_parser("consolidate", help="Consolidate memory")
    consolidate.add_argument(
        "--scope",
        required=True,
        choices=["session", "agent", "task"],
    )
    consolidate.add_argument("--session-id")
    consolidate.add_argument("--task-id")
    consolidate.add_argument("--agent-id")
    consolidate.add_argument("--branch")
    consolidate.add_argument(
        "--format", choices=["table", "json", "text"], default="table"
    )
    consolidate.set_defaults(_handler=cmd_consolidate)


def cmd_write_fact(args: argparse.Namespace) -> int:
    return run_async(_cmd_write_fact(args))


async def _cmd_write_fact(args: argparse.Namespace) -> int:
    metadata = parse_json_arg(args.metadata)

    async def _run(session: Any) -> dict[str, Any]:
        engine = FactEngine(session, get_embedding_provider())
        fact = await engine.write_fact(
            fact_text=args.fact_text,
            category=args.category,
            confidence=args.confidence,
            session_id=args.session_id,
            branch_name=args.branch or get_active_branch(),
            metadata=metadata,
        )
        return {
            "id": fact.id,
            "fact_text": fact.fact_text,
            "category": fact.category,
            "confidence": fact.confidence,
            "branch_name": fact.branch_name,
            "created_at": fact.created_at.isoformat() if fact.created_at else None,
        }

    emit(await with_session(_run), args.format)
    return 0


def cmd_write_observation(args: argparse.Namespace) -> int:
    return run_async(_cmd_write_observation(args))


async def _cmd_write_observation(args: argparse.Namespace) -> int:
    metadata = parse_json_arg(args.metadata)

    async def _run(session: Any) -> dict[str, Any]:
        engine = ObservationEngine(session, get_embedding_provider())
        obs = await engine.write_observation(
            session_id=args.session_id,
            observation_type=args.observation_type,
            summary=args.summary,
            tool_name=args.tool_name,
            branch_name=args.branch or get_active_branch(),
            metadata=metadata,
        )
        return {
            "id": obs.id,
            "session_id": obs.session_id,
            "observation_type": obs.observation_type,
            "tool_name": obs.tool_name,
            "summary": obs.summary,
            "branch_name": obs.branch_name,
            "created_at": obs.created_at.isoformat() if obs.created_at else None,
        }

    emit(await with_session(_run), args.format)
    return 0


def cmd_write_relation(args: argparse.Namespace) -> int:
    return run_async(_cmd_write_relation(args))


async def _cmd_write_relation(args: argparse.Namespace) -> int:
    properties = parse_json_arg(args.properties)

    async def _run(session: Any) -> dict[str, Any]:
        engine = RelationEngine(session)
        rel = await engine.write_relation(
            source_entity=args.source_entity,
            target_entity=args.target_entity,
            relation_type=args.relation_type,
            properties=properties,
            confidence=args.confidence,
            session_id=args.session_id,
            branch_name=args.branch or get_active_branch(),
        )
        return {
            "id": rel.id,
            "source_entity": rel.source_entity,
            "target_entity": rel.target_entity,
            "relation_type": rel.relation_type,
            "confidence": rel.confidence,
            "branch_name": rel.branch_name,
            "created_at": rel.created_at.isoformat() if rel.created_at else None,
        }

    emit(await with_session(_run), args.format)
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    return run_async(_cmd_search(args))


async def _cmd_search(args: argparse.Namespace) -> int:
    async def _run(session: Any) -> dict[str, Any]:
        engine = SearchEngine(session, get_embedding_provider())
        results = await engine.search(
            query=args.query,
            search_type=args.search_type,
            branch_name=args.branch or get_active_branch(),
            category=args.category,
            limit=args.limit,
        )
        return {"results": results, "count": len(results)}

    emit(await with_session(_run), args.format)
    return 0


def cmd_graph_query(args: argparse.Namespace) -> int:
    return run_async(_cmd_graph_query(args))


async def _cmd_graph_query(args: argparse.Namespace) -> int:
    async def _run(session: Any) -> dict[str, Any]:
        engine = RelationEngine(session)
        relations = await engine.graph_query(
            entity=args.entity,
            relation_type=args.relation_type,
            depth=args.depth,
            branch_name=args.branch or get_active_branch(),
        )
        return {"entity": args.entity, "relations": relations, "count": len(relations)}

    emit(await with_session(_run), args.format)
    return 0


def cmd_timeline(args: argparse.Namespace) -> int:
    return run_async(_cmd_timeline(args))


async def _cmd_timeline(args: argparse.Namespace) -> int:
    async def _run(session: Any) -> dict[str, Any]:
        embedder = get_embedding_provider()
        fact_engine = FactEngine(session, embedder)
        obs_engine = ObservationEngine(session, embedder)
        branch = args.branch or get_active_branch()

        facts = await fact_engine.list_facts(branch_name=branch, limit=args.limit)
        observations = await obs_engine.timeline(
            branch_name=branch,
            session_id=args.session_id,
            after=args.after,
            before=args.before,
            limit=args.limit,
        )

        timeline_items: list[dict[str, Any]] = []
        for fact in facts:
            timeline_items.append(
                {
                    "type": "fact",
                    "id": fact.id,
                    "content": fact.fact_text,
                    "category": fact.category,
                    "timestamp": (
                        fact.created_at.isoformat() if fact.created_at else None
                    ),
                }
            )
        for obs in observations:
            timeline_items.append(
                {
                    "type": "observation",
                    "id": obs.id,
                    "content": obs.summary,
                    "observation_type": obs.observation_type,
                    "tool_name": obs.tool_name,
                    "timestamp": (
                        obs.created_at.isoformat() if obs.created_at else None
                    ),
                }
            )
        timeline_items.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
        return {
            "timeline": timeline_items[: args.limit],
            "count": len(timeline_items[: args.limit]),
        }

    emit(await with_session(_run), args.format)
    return 0


def cmd_snapshot_create(args: argparse.Namespace) -> int:
    return run_async(_cmd_snapshot_create(args))


async def _cmd_snapshot_create(args: argparse.Namespace) -> int:
    async def _run(session: Any) -> dict[str, Any]:
        mgr = SnapshotManager(session)
        branch = args.branch or get_active_branch()
        if args.native:
            return await mgr.create_snapshot_native(
                branch_name=branch,
                label=args.label,
            )
        snapshot = await mgr.create_snapshot(branch_name=branch, label=args.label)
        return {
            "snapshot_id": snapshot.id,
            "label": snapshot.label,
            "branch_name": snapshot.branch_name,
            "created_at": (
                snapshot.created_at.isoformat() if snapshot.created_at else None
            ),
        }

    emit(await with_session(_run), args.format)
    return 0


def cmd_snapshot_list(args: argparse.Namespace) -> int:
    return run_async(_cmd_snapshot_list(args))


async def _cmd_snapshot_list(args: argparse.Namespace) -> int:
    async def _run(session: Any) -> dict[str, Any]:
        mgr = SnapshotManager(session)
        snapshots = await mgr.list_snapshots(
            branch_name=args.branch or get_active_branch()
        )
        return {
            "snapshots": [
                {
                    "id": s.id,
                    "label": s.label,
                    "branch_name": s.branch_name,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                }
                for s in snapshots
            ]
        }

    emit(await with_session(_run), args.format)
    return 0


def cmd_time_travel(args: argparse.Namespace) -> int:
    return run_async(_cmd_time_travel(args))


async def _cmd_time_travel(args: argparse.Namespace) -> int:
    async def _run(session: Any) -> dict[str, Any]:
        mgr = SnapshotManager(session)
        results = await mgr.time_travel_query(
            timestamp=args.timestamp,
            branch_name=args.branch or get_active_branch(),
            category=args.category,
            limit=args.limit,
        )
        if args.query:
            q = args.query.lower()
            results = [r for r in results if q in str(r.get("fact_text", "")).lower()]
        return {"timestamp": args.timestamp, "results": results, "count": len(results)}

    emit(await with_session(_run), args.format)
    return 0


def cmd_consolidate(args: argparse.Namespace) -> int:
    return run_async(_cmd_consolidate(args))


async def _cmd_consolidate(args: argparse.Namespace) -> int:
    async def _run(session: Any) -> dict[str, Any]:
        engine = ConsolidationEngine(session)
        branch = args.branch or get_active_branch()
        if args.scope == "session":
            if not args.session_id:
                raise ValueError("--session-id is required for --scope session")
            return await engine.consolidate_session(
                session_id=args.session_id,
                branch_name=branch,
                task_id=args.task_id,
                agent_id=args.agent_id,
            )
        if args.scope == "agent":
            if not args.task_id or not args.agent_id:
                raise ValueError(
                    "--task-id and --agent-id are required for --scope agent"
                )
            return await engine.consolidate_agent(
                task_id=args.task_id, agent_id=args.agent_id
            )
        if args.scope == "task":
            if not args.task_id:
                raise ValueError("--task-id is required for --scope task")
            return await engine.consolidate_task(task_id=args.task_id)
        raise ValueError(f"Unsupported scope: {args.scope}")

    emit(await with_session(_run), args.format)
    return 0
