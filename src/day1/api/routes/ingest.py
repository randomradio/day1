"""REST ingest and curl-friendly MCP tool wrapper routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from day1.core.exceptions import (
    BranchExistsError,
    BranchNotFoundError,
    Day1Error,
)
from day1.mcp import mcp_server
from day1.mcp.tools import TOOL_DEFINITIONS

router = APIRouter()


class ToolInvokeRequest(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None


class ToolInvokeByPathRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None


def _tool_exists(name: str) -> bool:
    return any(t.name == name for t in TOOL_DEFINITIONS)


def _map_tool_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, BranchNotFoundError):
        return HTTPException(status_code=404, detail=str(exc) or exc.__class__.__name__)
    if isinstance(exc, BranchExistsError):
        return HTTPException(status_code=409, detail=str(exc) or exc.__class__.__name__)
    if isinstance(exc, Day1Error):
        return HTTPException(status_code=400, detail=str(exc) or exc.__class__.__name__)
    return HTTPException(status_code=500, detail="Tool dispatch failed")


def _extract_text(payload: Any) -> str | None:
    if isinstance(payload, str):
        text = payload.strip()
        return text or None
    if isinstance(payload, list):
        parts = []
        for item in payload:
            text = _extract_text(item)
            if text:
                parts.append(text)
        joined = "\n".join(parts).strip()
        return joined or None
    if isinstance(payload, dict):
        for key in (
            "prompt",
            "last_assistant_message",
            "content",
            "text",
            "message",
            "response",
            "assistant_response",
            "user_message",
            "transcript",
            "tool_input",
            "tool_response",
        ):
            if key in payload:
                text = _extract_text(payload[key])
                if text:
                    return text
    return None


def _truncate(value: str, limit: int = 2000) -> str:
    return value if len(value) <= limit else value[: limit - 3] + "..."


def _event_metadata(event: str) -> dict:
    """Map hook event names to category/source_type/confidence for enrichment."""
    event_lower = event.lower()
    mapping = {
        "sessionstart": ("session", "session_start", 0.5),
        "userpromptsubmit": ("conversation", "user_input", 0.6),
        "pretooluse": ("tool", "tool_call", 0.6),
        "posttooluse": ("tool", "tool_observation", 0.6),
        "stop": ("conversation", "assistant_response", 0.7),
        "assistantresponse": ("conversation", "assistant_response", 0.7),
        "precompact": ("insight", "compaction", 0.85),
        "sessionend": ("session", "session_end", 0.5),
    }
    for key, (category, source_type, confidence) in mapping.items():
        if key in event_lower:
            return {"category": category, "source_type": source_type, "confidence": confidence}
    return {"category": "unknown", "source_type": "hook", "confidence": 0.5}


def _extract_hook_message_content(event: str, payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return _extract_text(payload)
    event_lower = event.lower()
    if "userprompt" in event_lower and payload.get("prompt"):
        return _extract_text(payload.get("prompt"))
    if event_lower in {"stop", "assistantresponse"} and payload.get(
        "last_assistant_message"
    ):
        return _extract_text(payload.get("last_assistant_message"))
    if "tool" in event_lower:
        # Prefer actual tool response payload for post-tool, input for pre-tool.
        if "post" in event_lower and payload.get("tool_response"):
            return _extract_text(payload.get("tool_response"))
        if payload.get("tool_input"):
            return _extract_text(payload.get("tool_input"))
    return _extract_text(payload)


def _hook_tool_fields(payload: Any) -> tuple[str | None, str | None, str | None]:
    if not isinstance(payload, dict):
        return None, None, None
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    tool_response = payload.get("tool_response")
    return (
        str(tool_name) if tool_name is not None else None,
        _extract_text(tool_input),
        _extract_text(tool_response),
    )


def _tool_summary(
    event: str,
    tool_name: str | None,
    tool_input: str | None,
    tool_output: str | None,
) -> str:
    if not tool_name:
        return f"Claude hook {event}"
    event_lower = event.lower()
    if "post" in event_lower:
        return (
            f"Tool {tool_name} completed. Input: {_truncate(tool_input or '', 180)} "
            f"Output: {_truncate(tool_output or '', 180)}"
        ).strip()
    return f"Tool {tool_name} called. Input: {_truncate(tool_input or '', 220)}".strip()


@router.get("/memories/timeline")
async def memory_timeline(
    branch: str = "main",
    limit: int = 20,
    category: str | None = None,
    source_type: str | None = None,
    session_id: str | None = None,
):
    """Get chronological memory timeline for a branch."""
    result = await mcp_server.dispatch_tool_call(
        "memory_timeline",
        {
            "branch": branch,
            "limit": limit,
            **({"category": category} if category else {}),
            **({"source_type": source_type} if source_type else {}),
            **({"session_id": session_id} if session_id else {}),
        },
    )
    return result


@router.get("/memories/count")
async def memory_count(branch: str = "main"):
    """Get memory count for a branch."""
    return await mcp_server.dispatch_tool_call("memory_count", {"branch": branch})


@router.get("/ingest/mcp-tools")
async def list_mcp_tools():
    """List all MCP tools with schemas for curl-friendly integrations."""
    return {
        "count": len(TOOL_DEFINITIONS),
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.inputSchema,
            }
            for t in TOOL_DEFINITIONS
        ],
    }


@router.post("/ingest/mcp")
async def invoke_mcp_tool(body: ToolInvokeRequest):
    """Call any MCP tool via plain JSON over REST (curl-friendly wrapper)."""
    if not _tool_exists(body.tool):
        raise HTTPException(status_code=404, detail=f"Unknown tool: {body.tool}")
    try:
        result = await mcp_server.dispatch_tool_call(
            body.tool,
            body.arguments,
            session_id=body.session_id,
        )
    except Exception as exc:
        raise _map_tool_exception(exc) from exc
    return {"tool": body.tool, "session_id": body.session_id, "result": result}


@router.post("/ingest/mcp-tools/{tool_name}")
async def invoke_mcp_tool_by_path(
    tool_name: str,
    body: ToolInvokeByPathRequest,
):
    """Path-based variant of MCP tool wrapper: one endpoint covers all tools."""
    if not _tool_exists(tool_name):
        raise HTTPException(status_code=404, detail=f"Unknown tool: {tool_name}")
    try:
        result = await mcp_server.dispatch_tool_call(
            tool_name,
            body.arguments,
            session_id=body.session_id,
        )
    except Exception as exc:
        raise _map_tool_exception(exc) from exc
    return {"tool": tool_name, "session_id": body.session_id, "result": result}


@router.post("/ingest/claude-hook")
async def ingest_claude_hook(
    request: Request,
    x_day1_hook_event: str | None = Header(default=None, alias="X-Day1-Hook-Event"),
    x_day1_project_path: str | None = Header(
        default=None, alias="X-Day1-Project-Path"
    ),
    x_day1_session_id: str | None = Header(default=None, alias="X-Day1-Session-Id"),
):
    """Receive raw Claude hook payloads (curl-friendly, minimal client logic).

    This endpoint is intentionally tolerant. It stores a lightweight observation
    for every hook event and, when a message-like text can be extracted, also
    stores a conversation message via the existing MCP tool implementation.
    """
    raw_bytes = await request.body()
    payload: Any
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    event = x_day1_hook_event or (
        payload.get("event") if isinstance(payload, dict) else None
    ) or "unknown"
    session_id = x_day1_session_id or (
        (payload.get("session_id") or payload.get("sessionId"))
        if isinstance(payload, dict)
        else None
    ) or "claude-hook"

    raw_text = raw_bytes.decode("utf-8", errors="replace")
    content = _extract_hook_message_content(event, payload)
    tool_name, tool_input, tool_output = _hook_tool_fields(payload)
    if "tool" in event.lower():
        summary = _tool_summary(event, tool_name, tool_input, tool_output)
    else:
        summary = f"Claude hook {event}"
        if content:
            summary = f"{summary}: {_truncate(content, 160)}"

    raw_context = _truncate(tool_input or raw_text or "{}", 2000)
    if tool_output:
        raw_context += f"\nOutput: {_truncate(tool_output, 2000)}"

    meta = _event_metadata(event)
    obs_result = await mcp_server.dispatch_tool_call(
        "memory_write",
        {
            "text": summary,
            "context": raw_context,
            "session_id": session_id,
            "category": meta["category"],
            "confidence": meta["confidence"],
            "source_type": meta["source_type"],
        },
        session_id=session_id,
    )

    # Best-effort: store message content as a second memory entry
    message_result = None
    message_error = None
    if content:
        event_lower = event.lower()
        role = None
        if "userprompt" in event_lower:
            role = "user"
        elif event_lower in {"stop", "assistantresponse"} or "assistant" in event_lower:
            role = "assistant"
        elif "tool" in event_lower:
            role = "tool_result" if "post" in event_lower else "tool_call"

        if role is not None:
            try:
                msg_text = content if role not in {"tool_call", "tool_result"} else summary
                message_result = await mcp_server.dispatch_tool_call(
                    "memory_write",
                    {
                        "text": msg_text,
                        "context": f"role:{role}",
                        "session_id": session_id,
                        "category": meta["category"],
                        "confidence": meta["confidence"],
                        "source_type": meta["source_type"],
                    },
                    session_id=session_id,
                )
            except Exception as exc:
                message_error = str(exc)
                message_result = None

    response = {
        "status": "ok",
        "event": event,
        "session_id": session_id,
        "observation": obs_result,
        "message": message_result,
    }
    if message_error:
        response["message_error"] = message_error
    return response
