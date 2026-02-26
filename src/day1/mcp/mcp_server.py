"""MCP Server for Day1: exposes memory tools via stdio/SSE."""

from __future__ import annotations

import asyncio
import json
import logging

from day1.logging_config import setup_logging

setup_logging()

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from day1.db.engine import close_db, get_session, init_db
from day1.mcp.tools import TOOL_DEFINITIONS, handle_tool_call

logger = logging.getLogger("day1.mcp")

app = Server("day1-memory")

# Track current active branch per server instance
_active_branch: str = "main"


def get_active_branch() -> str:
    return _active_branch


def set_active_branch(branch: str) -> None:
    global _active_branch
    _active_branch = branch


@app.list_tools()
async def list_tools() -> list[Tool]:
    """Return all available memory tools."""
    return TOOL_DEFINITIONS


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Dispatch tool calls to handlers."""
    try:
        session_gen = get_session()
        session = await anext(session_gen)
        try:
            result = await handle_tool_call(
                name, arguments, session, get_active_branch, set_active_branch
            )
            return [TextContent(type="text", text=json.dumps(result, default=str))]
        finally:
            await session_gen.aclose()
    except Exception as e:  # Intentional catch-all: MCP protocol boundary
        logger.exception("Tool %s failed", name)
        return [
            TextContent(
                type="text",
                text=json.dumps({"error": str(e), "tool": name}),
            )
        ]
    return [
        TextContent(type="text", text=json.dumps({"error": "No session available"}))
    ]


async def main() -> None:
    """Run MCP server in stdio mode."""
    await init_db()

    # Ensure main branch exists
    session_gen = get_session()
    session = await anext(session_gen)
    try:
        from day1.core.branch_manager import BranchManager

        mgr = BranchManager(session)
        await mgr.ensure_main_branch()
    finally:
        await session_gen.aclose()

    logger.info("Day1 MCP server starting (stdio)")
    try:
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
