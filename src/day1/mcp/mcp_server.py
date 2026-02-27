"""MCP Server for Day1 exposed over Streamable HTTP (mounted into FastAPI)."""

from __future__ import annotations

import json
import logging
from http import HTTPStatus
from typing import Any

from day1.logging_config import setup_logging

setup_logging()

from mcp.server import Server
from mcp.server.streamable_http import MCP_SESSION_ID_HEADER
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import TextContent, Tool

from day1.db.engine import get_session
from day1.mcp.tools import TOOL_DEFINITIONS, handle_tool_call

logger = logging.getLogger("day1.mcp")

app = Server("day1-memory")

# Track current active branch per MCP HTTP session
_default_branch: str = "main"
_active_branches_by_session: dict[str, str] = {}
_http_session_manager: StreamableHTTPSessionManager | None = None


def _scope_header(scope: dict[str, Any], name: str) -> str | None:
    header_key = name.lower().encode()
    for key, value in scope.get("headers", []):
        if key.lower() == header_key:
            return value.decode()
    return None


def _request_session_id() -> str | None:
    try:
        req = app.request_context.request
    except LookupError:
        return None
    if req is None:
        return None
    return req.headers.get(MCP_SESSION_ID_HEADER)


def get_active_branch() -> str:
    session_id = _request_session_id()
    if not session_id:
        return _default_branch
    return _active_branches_by_session.get(session_id, _default_branch)


def set_active_branch(branch: str) -> None:
    session_id = _request_session_id()
    if not session_id:
        return
    _active_branches_by_session[session_id] = branch


def get_active_branch_for_session(session_id: str | None) -> str:
    if not session_id:
        return _default_branch
    return _active_branches_by_session.get(session_id, _default_branch)


def set_active_branch_for_session(session_id: str | None, branch: str) -> None:
    if not session_id:
        return
    _active_branches_by_session[session_id] = branch


def clear_active_branch(session_id: str | None) -> None:
    if session_id:
        _active_branches_by_session.pop(session_id, None)


def reset_mcp_http_state() -> None:
    _active_branches_by_session.clear()


def create_http_session_manager() -> StreamableHTTPSessionManager:
    # DNS rebinding protection can be enabled later with explicit host/origin config.
    security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    return StreamableHTTPSessionManager(
        app=app,
        stateless=False,
        json_response=False,
        security_settings=security,
    )


def set_http_session_manager(manager: StreamableHTTPSessionManager | None) -> None:
    global _http_session_manager
    _http_session_manager = manager


class MCPHTTPASGIApp:
    """ASGI wrapper for the MCP Streamable HTTP session manager."""

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await send(
                {
                    "type": "http.response.start",
                    "status": int(HTTPStatus.NOT_FOUND),
                    "headers": [],
                }
            )
            await send({"type": "http.response.body", "body": b""})
            return

        manager = _http_session_manager
        if manager is None:
            body = json.dumps({"error": "MCP HTTP not initialized"}).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": int(HTTPStatus.SERVICE_UNAVAILABLE),
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        method = scope.get("method", "").upper()
        session_id = _scope_header(scope, MCP_SESSION_ID_HEADER)
        try:
            await manager.handle_request(scope, receive, send)
        finally:
            if method == "DELETE":
                clear_active_branch(session_id)


mcp_http_asgi_app = MCPHTTPASGIApp()


async def dispatch_tool_call(
    name: str,
    arguments: dict[str, Any],
    *,
    session_id: str | None = None,
) -> Any:
    """Dispatch a Day1 MCP tool call without MCP protocol wrapping.

    Used by the MCP HTTP transport and the REST curl-friendly wrapper so they
    share the same implementation and branch-session behavior.
    """
    session_gen = get_session()
    session = await anext(session_gen)
    try:
        return await handle_tool_call(
            name,
            arguments,
            session,
            lambda: get_active_branch_for_session(session_id),
            lambda branch: set_active_branch_for_session(session_id, branch),
        )
    finally:
        await session_gen.aclose()


@app.list_tools()
async def list_tools() -> list[Tool]:
    """Return all available memory tools."""
    return TOOL_DEFINITIONS


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Dispatch tool calls to handlers."""
    try:
        result = await dispatch_tool_call(
            name,
            arguments,
            session_id=_request_session_id(),
        )
        return [TextContent(type="text", text=json.dumps(result, default=str))]
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
