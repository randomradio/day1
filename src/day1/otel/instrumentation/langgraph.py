"""LangGraph trace adapter placeholder."""

from __future__ import annotations

from typing import Any


def to_day1_events(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize LangGraph step payloads to Day1 collector events."""
    events: list[dict[str, Any]] = []
    for step in steps:
        step_type = str(step.get("type", "step"))
        if step_type in {"user", "assistant", "message"}:
            events.append(
                {
                    "kind": "message",
                    "role": step.get("role", "assistant"),
                    "content": step.get("content", ""),
                    "node": step.get("node"),
                }
            )
            continue
        events.append(
            {
                "kind": step_type,
                "summary": step.get("summary") or step.get("content") or step_type,
                "node": step.get("node"),
                "metadata": step.get("metadata", {}),
            }
        )
    return events


def build_ingest_payload(
    trace_id: str,
    steps: list[dict[str, Any]],
    session_id: str | None = None,
    branch_name: str = "main",
) -> dict[str, Any]:
    return {
        "source": "langgraph",
        "trace_id": trace_id,
        "session_id": session_id,
        "branch_name": branch_name,
        "events": to_day1_events(steps),
        "metadata": {"adapter": "langgraph"},
    }

