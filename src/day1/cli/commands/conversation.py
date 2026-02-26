"""Conversation and message CLI commands."""

from __future__ import annotations

import argparse
from typing import Any

from day1.cli.commands.common import (
    emit,
    get_active_branch,
    parse_json_arg,
    parse_json_list_arg,
    run_async,
    with_session,
)
from day1.core.conversation_engine import ConversationEngine
from day1.core.embedding import get_embedding_provider
from day1.core.message_engine import MessageEngine


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    create = subparsers.add_parser("create-conversation", help="Create a conversation")
    create.add_argument("title", nargs="?")
    create.add_argument("--session-id")
    create.add_argument("--agent-id")
    create.add_argument("--task-id")
    create.add_argument("--branch")
    create.add_argument("--model")
    create.add_argument("--metadata", help="JSON object")
    create.add_argument("--format", choices=["table", "json", "text"], default="table")
    create.set_defaults(_handler=cmd_create_conversation)

    add = subparsers.add_parser("add-message", help="Add a message to a conversation")
    add.add_argument("conversation_id")
    add.add_argument("--role", required=True)
    add.add_argument("--content")
    add.add_argument("--thinking")
    add.add_argument("--tool-calls", help="JSON array")
    add.add_argument("--token-count", type=int, default=0)
    add.add_argument("--model")
    add.add_argument("--session-id")
    add.add_argument("--agent-id")
    add.add_argument("--branch")
    add.add_argument("--metadata", help="JSON object")
    add.add_argument("--format", choices=["table", "json", "text"], default="table")
    add.set_defaults(_handler=cmd_add_message)

    list_cmd = subparsers.add_parser("list-conversations", help="List conversations")
    list_cmd.add_argument("--session-id")
    list_cmd.add_argument("--agent-id")
    list_cmd.add_argument("--task-id")
    list_cmd.add_argument("--branch")
    list_cmd.add_argument("--status")
    list_cmd.add_argument("--limit", type=int, default=50)
    list_cmd.add_argument("--offset", type=int, default=0)
    list_cmd.add_argument(
        "--format", choices=["table", "json", "text"], default="table"
    )
    list_cmd.set_defaults(_handler=cmd_list_conversations)


def cmd_create_conversation(args: argparse.Namespace) -> int:
    return run_async(_cmd_create_conversation(args))


async def _cmd_create_conversation(args: argparse.Namespace) -> int:
    metadata = parse_json_arg(args.metadata)

    async def _run(session: Any) -> dict[str, Any]:
        engine = ConversationEngine(session)
        conv = await engine.create_conversation(
            session_id=args.session_id,
            agent_id=args.agent_id,
            task_id=args.task_id,
            branch_name=args.branch or get_active_branch(),
            title=args.title,
            model=args.model,
            metadata=metadata,
        )
        return {
            "conversation_id": conv.id,
            "session_id": conv.session_id,
            "agent_id": conv.agent_id,
            "task_id": conv.task_id,
            "branch_name": conv.branch_name,
            "title": conv.title,
            "status": conv.status,
            "created_at": conv.created_at.isoformat() if conv.created_at else None,
        }

    emit(await with_session(_run), args.format)
    return 0


def cmd_add_message(args: argparse.Namespace) -> int:
    return run_async(_cmd_add_message(args))


async def _cmd_add_message(args: argparse.Namespace) -> int:
    tool_calls = parse_json_list_arg(args.tool_calls)
    metadata = parse_json_arg(args.metadata)

    async def _run(session: Any) -> dict[str, Any]:
        engine = MessageEngine(session, get_embedding_provider())
        msg = await engine.write_message(
            conversation_id=args.conversation_id,
            role=args.role,
            content=args.content,
            thinking=args.thinking,
            tool_calls=tool_calls,
            token_count=args.token_count,
            model=args.model,
            session_id=args.session_id,
            agent_id=args.agent_id,
            branch_name=args.branch or get_active_branch(),
            metadata=metadata,
        )
        return {
            "message_id": msg.id,
            "conversation_id": msg.conversation_id,
            "role": msg.role,
            "sequence_num": msg.sequence_num,
            "branch_name": msg.branch_name,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        }

    emit(await with_session(_run), args.format)
    return 0


def cmd_list_conversations(args: argparse.Namespace) -> int:
    return run_async(_cmd_list_conversations(args))


async def _cmd_list_conversations(args: argparse.Namespace) -> int:
    async def _run(session: Any) -> dict[str, Any]:
        engine = ConversationEngine(session)
        conversations = await engine.list_conversations(
            session_id=args.session_id,
            agent_id=args.agent_id,
            task_id=args.task_id,
            branch_name=args.branch or None,
            status=args.status,
            limit=args.limit,
            offset=args.offset,
        )
        return {
            "conversations": [
                {
                    "id": c.id,
                    "session_id": c.session_id,
                    "agent_id": c.agent_id,
                    "task_id": c.task_id,
                    "title": c.title,
                    "status": c.status,
                    "message_count": c.message_count,
                    "total_tokens": c.total_tokens,
                    "branch_name": c.branch_name,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
                for c in conversations
            ],
            "count": len(conversations),
        }

    emit(await with_session(_run), args.format)
    return 0
