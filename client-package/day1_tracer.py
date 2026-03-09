"""Day1 Client — lightweight wrapper for Day1 memory + skill evolution REST API.

Works with any agent framework: LangChain, LiteLLM, CrewAI, AutoGen, etc.
No Day1 dependency required — pure httpx calls.

Covers: memory write/search/graph, trace capture, skill evolution.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import httpx


class Day1Tracer:
    """Capture agent execution traces and send them to Day1 for analysis.

    Usage:
        tracer = Day1Tracer("http://localhost:8000")
        tracer.start("Solve math problem")

        tracer.add_user_message("What is 2+2?")
        tracer.add_tool_use("calculator", {"expr": "2+2"}, "4")
        tracer.add_assistant_message("The answer is 4")

        trace = tracer.finish()  # stores in Day1
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        branch: str = "main",
        session_id: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.branch = branch
        self.session_id = session_id or f"agent-{int(time.time())}"
        self._client = httpx.Client(base_url=self.base_url, timeout=30.0)
        self._steps: list[dict[str, Any]] = []
        self._task_description: str | None = None
        self._metadata: dict[str, Any] = {}
        self._start_time: float | None = None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Day1Tracer:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ── Recording ────────────────────────────────────────────────────────

    def start(self, task_description: str, **metadata: Any) -> None:
        """Start recording a trace."""
        self._task_description = task_description
        self._metadata = metadata
        self._start_time = time.time()
        self._steps = []
        self._add_step("session_start")

    def add_user_message(self, content: str, **kwargs: Any) -> None:
        self._add_step("user_message", content=content, **kwargs)

    def add_assistant_message(self, content: str, **kwargs: Any) -> None:
        self._add_step("assistant_message", content=content, **kwargs)

    def add_tool_use(
        self,
        tool_name: str,
        tool_input: Any,
        tool_output: Any,
        duration_ms: int | None = None,
        **kwargs: Any,
    ) -> None:
        self._add_step(
            "tool_use",
            tool_name=tool_name,
            tool_input=_to_str(tool_input),
            tool_output=_to_str(tool_output),
            duration_ms=duration_ms,
            **kwargs,
        )

    def add_error(self, error: str, **kwargs: Any) -> None:
        self._add_step("tool_use", tool_output=f"error: {error}", **kwargs)

    def finish(
        self,
        trace_type: str = "external",
        parent_trace_id: str | None = None,
        skill_id: str | None = None,
    ) -> dict[str, Any]:
        """Stop recording and store the trace in Day1."""
        self._add_step("session_end")
        return self.store_trace(
            steps=self._steps,
            trace_type=trace_type,
            parent_trace_id=parent_trace_id,
            skill_id=skill_id,
        )

    # ── Day1 API calls ───────────────────────────────────────────────────

    def store_trace(
        self,
        steps: list[dict[str, Any]],
        trace_type: str = "external",
        parent_trace_id: str | None = None,
        skill_id: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/v1/traces — store a trace."""
        payload: dict[str, Any] = {
            "steps": steps,
            "trace_type": trace_type,
            "session_id": self.session_id,
            "branch": self.branch,
        }
        if self._task_description:
            payload["task_description"] = self._task_description
        if self._metadata:
            payload["metadata"] = self._metadata
        if parent_trace_id:
            payload["parent_trace_id"] = parent_trace_id
        if skill_id:
            payload["skill_id"] = skill_id
        return self._post("/api/v1/traces", payload)

    def extract_trace(self, hook_session_id: str) -> dict[str, Any]:
        """POST /api/v1/traces/extract — extract trace from Claude Code hook_logs."""
        return self._post(
            "/api/v1/traces/extract",
            {"session_id": hook_session_id, "branch": self.branch},
        )

    def compare(
        self,
        trace_a_id: str,
        trace_b_id: str,
        skill_id: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/v1/traces/{a}/compare/{b}"""
        payload: dict[str, Any] = {}
        if skill_id:
            payload["skill_id"] = skill_id
        return self._post(
            f"/api/v1/traces/{trace_a_id}/compare/{trace_b_id}", payload
        )

    def register_skill(
        self,
        skill_name: str,
        content: str,
        source: str = "manual",
    ) -> dict[str, Any]:
        """POST /api/v1/skills"""
        return self._post(
            "/api/v1/skills",
            {
                "skill_name": skill_name,
                "content": content,
                "branch": self.branch,
                "source": source,
            },
        )

    def list_skills(self, status: str | None = None) -> dict[str, Any]:
        """GET /api/v1/skills"""
        params: dict[str, Any] = {}
        if status:
            params["status"] = status
        return self._get("/api/v1/skills", params)

    def evolve_skill(
        self,
        skill_name: str,
        strategy: str = "single_mutation",
        comparison_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """POST /api/v1/skills/{name}/evolve"""
        payload: dict[str, Any] = {"strategy": strategy}
        if comparison_ids:
            payload["comparison_ids"] = comparison_ids
        return self._post(f"/api/v1/skills/{skill_name}/evolve", payload)

    def promote_skill(self, skill_id: str) -> dict[str, Any]:
        """POST /api/v1/skills/{id}/promote"""
        return self._post(f"/api/v1/skills/{skill_id}/promote", {})

    def get_evolution_history(self, skill_name: str) -> dict[str, Any]:
        """GET /api/v1/skills/{name}/history"""
        return self._get(f"/api/v1/skills/{skill_name}/history")

    # ── Memory Operations ──────────────────────────────────────────────

    def memory_write(
        self,
        text: str,
        context: str | None = None,
        file_context: str | None = None,
        category: str | None = None,
        confidence: float = 0.7,
        source_type: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/v1/ingest/mcp — write a memory."""
        args: dict[str, Any] = {
            "text": text,
            "session_id": self.session_id,
            "branch": self.branch,
            "confidence": confidence,
        }
        if context:
            args["context"] = context
        if file_context:
            args["file_context"] = file_context
        if category:
            args["category"] = category
        if source_type:
            args["source_type"] = source_type
        return self._post("/api/v1/ingest/mcp", {"tool": "memory_write", "arguments": args})

    def memory_search(
        self,
        query: str,
        limit: int = 10,
        category: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/v1/ingest/mcp — search memories."""
        args: dict[str, Any] = {"query": query, "branch": self.branch, "limit": limit}
        if category:
            args["category"] = category
        return self._post("/api/v1/ingest/mcp", {"tool": "memory_search", "arguments": args})

    def memory_relate(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/v1/memories/{source_id}/relations — create relation."""
        payload: dict[str, Any] = {
            "target_id": target_id,
            "relation_type": relation_type,
            "branch": self.branch,
        }
        if description:
            payload["description"] = description
        return self._post(f"/api/v1/memories/{source_id}/relations", payload)

    def memory_graph(
        self,
        memory_id: str,
        depth: int = 1,
        limit: int = 50,
    ) -> dict[str, Any]:
        """GET /api/v1/memories/{id}/graph — graph traversal."""
        return self._get(
            f"/api/v1/memories/{memory_id}/graph",
            {"depth": depth, "limit": limit, "branch": self.branch},
        )

    def health(self) -> dict[str, Any]:
        return self._get("/health")

    # ── Internal ─────────────────────────────────────────────────────────

    def _add_step(self, event_type: str, **fields: Any) -> None:
        step: dict[str, Any] = {
            "seq": len(self._steps),
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "content": fields.pop("content", None),
            "tool_name": fields.pop("tool_name", None),
            "tool_input": fields.pop("tool_input", None),
            "tool_output": fields.pop("tool_output", None),
            "token_count": fields.pop("token_count", None),
            "duration_ms": fields.pop("duration_ms", None),
        }
        self._steps.append(step)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        resp = self._client.post(path, json=payload)
        resp.raise_for_status()
        return resp.json()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    import json
    try:
        return json.dumps(value, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)
