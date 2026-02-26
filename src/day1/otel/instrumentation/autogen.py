"""AutoGen trace adapter placeholder."""

from __future__ import annotations

from typing import Any


def to_day1_events(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize AutoGen turns to Day1 collector events."""
    events: list[dict[str, Any]] = []
    for turn in turns:
        speaker = str(turn.get("speaker", "agent"))
        content = str(turn.get("content", ""))
        role = "user" if speaker.lower() in {"user", "human"} else "assistant"
        events.append(
            {
                "kind": "message",
                "role": role,
                "content": content,
                "speaker": speaker,
                "tool": turn.get("tool"),
            }
        )
        if turn.get("tool"):
            events.append(
                {
                    "kind": "tool_use",
                    "summary": f"{speaker} used tool {turn['tool']}",
                    "content": content,
                }
            )
    return events


def build_ingest_payload(
    trace_id: str,
    turns: list[dict[str, Any]],
    session_id: str | None = None,
    branch_name: str = "main",
) -> dict[str, Any]:
    return {
        "source": "autogen",
        "trace_id": trace_id,
        "session_id": session_id,
        "branch_name": branch_name,
        "events": to_day1_events(turns),
        "metadata": {"adapter": "autogen"},
    }

