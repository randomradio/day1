#!/usr/bin/env python3
"""Surface + scenario E2E coverage for API / CLI / MCP.

Goals:
- Hit every FastAPI route/method at least once (smoke; 4xx is acceptable, 5xx is not)
- Exercise every CLI leaf command (help smoke)
- Exercise every MCP tool endpoint (call boundary smoke)
- Run one realistic write/read scenario across API, CLI, MCP
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, get_args, get_origin

import httpx
from fastapi.routing import APIRoute
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import BaseModel

from day1.api.app import app as fastapi_app
from day1.cli.main import _build_parser
from day1.mcp.tools import TOOL_DEFINITIONS


DUMMY_UUID = "00000000-0000-0000-0000-000000000001"


# Surface warnings must be explicitly enumerated; unexpected 4xx is a failure.
EXPECTED_API_SURFACE_WARNINGS: dict[str, dict[str, Any]] = {
    "POST /api/v1/branches": {"status": 422, "contains": ["Field required"]},
    "POST /api/v1/branches/curated": {"status": 422, "contains": ["Field required"]},
    "POST /api/v1/branches/validate-name": {"status": 422, "contains": ["Field required"]},
    "DELETE /api/v1/branches/{branch_name:path}": {"status": 404, "contains": ["Branch ", "not found"]},
    "GET /api/v1/branches/{branch_name:path}/diff": {"status": 404, "contains": ["Branch ", "not found"]},
    "GET /api/v1/branches/{branch_name:path}/diff/native": {"status": 404, "contains": ["Branch ", "not found"]},
    "GET /api/v1/branches/{branch_name:path}/diff/native/count": {"status": 404, "contains": ["Branch ", "not found"]},
    "POST /api/v1/branches/{branch_name:path}/enrich": {"status": 404, "contains": ["Branch ", "not found"]},
    "POST /api/v1/branches/{branch_name:path}/merge": {"status": 404, "contains": ["Branch ", "not found"]},
    "GET /api/v1/branches/{branch_name:path}/stats": {"status": 404, "contains": ["Branch ", "not found"]},
    "POST /api/v1/bundles": {"status": 422, "contains": ["Field required"]},
    "GET /api/v1/bundles/{bundle_id}": {"status": 404, "contains": ["Bundle ", "not found"]},
    "GET /api/v1/bundles/{bundle_id}/export": {"status": 404, "contains": ["Bundle ", "not found"]},
    "POST /api/v1/bundles/{bundle_id}/import": {"status": 422, "contains": ["Field required"]},
    "GET /api/v1/conversations/{conv_a}/semantic-diff/{conv_b}": {"status": 404, "contains": ["No messages in conversation"]},
    "GET /api/v1/conversations/{conversation_id}": {"status": 404, "contains": ["Conversation not found"]},
    "POST /api/v1/conversations/{conversation_id}/cherry-pick": {"status": 422, "contains": ["Field required"]},
    "POST /api/v1/conversations/{conversation_id}/complete": {"status": 404, "contains": ["Conversation not found"]},
    "POST /api/v1/conversations/{conversation_id}/evaluate": {"status": 404, "contains": ["Conversation not found"]},
    "POST /api/v1/conversations/{conversation_id}/fork": {"status": 422, "contains": ["Field required"]},
    "POST /api/v1/conversations/{conversation_id}/messages": {"status": 422, "contains": ["Field required"]},
    "POST /api/v1/conversations/{conversation_id}/messages/batch": {"status": 422, "contains": ["Field required"]},
    "POST /api/v1/conversations/{conversation_id}/replay": {"status": 422, "contains": ["Field required"]},
    "POST /api/v1/facts": {"status": 422, "contains": ["Field required"]},
    "POST /api/v1/facts/search": {"status": 422, "contains": ["Field required"]},
    "GET /api/v1/facts/{fact_id}": {"status": 404, "contains": ["Fact ", "not found"]},
    "PATCH /api/v1/facts/{fact_id}": {"status": 404, "contains": ["Fact ", "not found"]},
    "GET /api/v1/facts/{fact_id}/related": {"status": 404, "contains": ["Fact ", "not found"]},
    "GET /api/v1/facts/{fact_id}/verification": {"status": 404, "contains": ["Fact ", "not found"]},
    "POST /api/v1/facts/{fact_id}/verify": {"status": 404, "contains": ["Fact ", "not found"]},
    "POST /api/v1/handoffs": {"status": 422, "contains": ["Field required"]},
    "GET /api/v1/handoffs/{handoff_id}": {"status": 404, "contains": ["Handoff record ", "not found"]},
    "GET /api/v1/messages/{message_id}": {"status": 404, "contains": ["Message not found"]},
    "POST /api/v1/observations": {"status": 422, "contains": ["Field required"]},
    "POST /api/v1/relations": {"status": 422, "contains": ["Field required"]},
    "POST /api/v1/replays/{replay_id}/complete": {"status": 404, "contains": ["Replay not found"]},
    "GET /api/v1/replays/{replay_id}/context": {"status": 404, "contains": ["Replay not found"]},
    "GET /api/v1/replays/{replay_id}/diff": {"status": 404, "contains": ["Replay not found"]},
    "GET /api/v1/replays/{replay_id}/semantic-diff": {"status": 404, "contains": ["Replay not found"]},
    "POST /api/v1/scores": {"status": 422, "contains": ["Field required"]},
    "GET /api/v1/sessions/{session_id}": {"status": 404, "contains": ["Session ", "not found"]},
    "GET /api/v1/sessions/{session_id}/context": {"status": 404, "contains": ["Session ", "not found"]},
    "GET /api/v1/snapshots/{snapshot_id}": {"status": 404, "contains": ["Snapshot not found"]},
    "POST /api/v1/tasks": {"status": 422, "contains": ["Field required"]},
    "GET /api/v1/tasks/{task_id}": {"status": 404, "contains": ["Task ", "not found"]},
    "POST /api/v1/tasks/{task_id}/agents/{agent_id}/complete": {"status": 404, "contains": ["Task ", "not found"]},
    "POST /api/v1/tasks/{task_id}/complete": {"status": 404, "contains": ["Task ", "not found"]},
    "POST /api/v1/tasks/{task_id}/consolidate": {"status": 400, "contains": ["Invalid consolidation level or missing required fields"]},
    "POST /api/v1/tasks/{task_id}/join": {"status": 422, "contains": ["Field required"]},
    "PATCH /api/v1/tasks/{task_id}/objectives/{objective_id}": {"status": 422, "contains": ["Field required"]},
    "POST /api/v1/templates": {"status": 422, "contains": ["Field required"]},
    "GET /api/v1/templates/{name}": {"status": 404, "contains": ["Template ", "not found"]},
    "POST /api/v1/templates/{name}/deprecate": {"status": 404, "contains": ["Template ", "not found"]},
    "POST /api/v1/templates/{name}/instantiate": {"status": 422, "contains": ["Field required"]},
    "POST /api/v1/templates/{name}/update": {"status": 422, "contains": ["Field required"]},
    "POST /api/v1/time-travel": {"status": 422, "contains": ["Field required"]},
    "POST /api/v1/verification/batch": {"status": 422, "contains": ["Field required"]},
    "POST /api/v1/verification/merge-gate": {"status": 422, "contains": ["Field required"]},
}

# Kept as a dict for future explicit MCP surface warns; currently strict MCP surface is 0 warn.
EXPECTED_MCP_SURFACE_WARNINGS: dict[str, dict[str, Any]] = {}


@dataclass
class CaseResult:
    name: str
    ok: bool
    category: str
    detail: str = ""
    status_code: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SectionResult:
    name: str
    total: int = 0
    passed: int = 0
    warnings: int = 0
    failed: int = 0
    cases: list[CaseResult] = field(default_factory=list)

    def add(self, case: CaseResult) -> None:
        self.total += 1
        if case.ok:
            if case.category == "warn":
                self.warnings += 1
            else:
                self.passed += 1
        else:
            self.failed += 1
        self.cases.append(case)


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _env_with_defaults() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("BM_EMBEDDING_PROVIDER", "mock")
    env.setdefault("BM_RATE_LIMIT", "0")
    env.setdefault("BM_LOG_LEVEL", "CRITICAL")
    return env


@asynccontextmanager
async def _mcp_http_session(mcp_url: str):
    async with httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(15.0, read=120.0)) as http_client:
        async with streamable_http_client(mcp_url, http_client=http_client) as (
            read_stream,
            write_stream,
            get_session_id,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session, get_session_id


def _mcp_parse_tool_payload(call_result: Any) -> dict[str, Any]:
    contents = getattr(call_result, "content", None) or []
    if not contents:
        return {"error": "empty_mcp_tool_result", "isError": bool(getattr(call_result, "isError", False))}

    first = contents[0]
    text = getattr(first, "text", None)
    if not isinstance(text, str):
        return {
            "error": "unsupported_mcp_tool_result_content",
            "content_type": type(first).__name__,
            "isError": bool(getattr(call_result, "isError", False)),
        }

    try:
        payload = json.loads(text)
    except Exception:
        payload = {"raw_text": text}

    if isinstance(payload, dict) and getattr(call_result, "isError", False):
        payload.setdefault("mcp_protocol_error", True)
        if "error" not in payload:
            payload["error"] = payload.get("raw_text") or "mcp_protocol_error"
    return payload if isinstance(payload, dict) else {"value": payload}


def _sample_for_name(name: str) -> Any:
    lname = name.lower()
    if lname in {"conv_a", "conv_b", "conversation_a", "conversation_b"}:
        return DUMMY_UUID
    if lname == "objective_id":
        return 1
    if lname in {"branch", "branch_name"}:
        return "e2e-missing-branch"
    if lname == "root_branch":
        return "main"
    if lname in {"parent_branch", "target_branch"}:
        return "main"
    if lname in {"source_branch"}:
        return "e2e-missing-branch"
    if lname.endswith("_id") or lname == "id":
        return DUMMY_UUID
    if "timestamp" in lname or lname in {"after", "before"}:
        return "2099-01-01T00:00:00Z"
    if lname in {"query", "q"}:
        return "e2e query"
    if lname == "granularity":
        return "day"
    if lname == "search_type":
        return "keyword"
    if lname == "role":
        return "user"
    if lname == "strategy":
        return "auto"
    if lname == "conflict":
        return "skip"
    if lname == "scope":
        return "session"
    if lname == "status":
        return "active"
    if lname == "name":
        return "e2e-name"
    if lname == "title":
        return "e2e-title"
    if lname == "description":
        return "e2e-description"
    if lname == "summary":
        return "e2e-summary"
    if lname == "fact_text":
        return "e2e fact"
    if lname in {"source_entity", "target_entity", "entity"}:
        return "e2e-entity"
    if lname == "relation_type":
        return "relates_to"
    if lname == "observation_type":
        return "tool_use"
    if lname == "tool_name":
        return "e2e-tool"
    if lname == "session_id":
        return "e2e-session"
    if lname in {"days", "max_depth", "offset", "inactive_days", "message_limit", "fact_limit"}:
        return 5
    if lname == "limit":
        return 5
    if lname == "depth":
        return 1
    if lname == "confidence":
        return 1.0
    if lname in {"native", "dry_run", "include_archived", "include_messages", "archive_merged", "merge_to_main", "only_unverified", "require_verified"}:
        return False
    if lname in {"items", "tags", "conversation_ids", "fact_ids", "objectives"}:
        return []
    if lname in {"metadata", "properties", "time_range"}:
        return {}
    return None


def _sample_for_type(name: str, annotation: Any) -> Any:
    name_override = _sample_for_name(name)
    if name_override is not None:
        return name_override

    if annotation is None:
        return "e2e"
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is None:
        if annotation in (str, Any):
            return "e2e"
        if annotation is int:
            return 1
        if annotation is float:
            return 1.0
        if annotation is bool:
            return True
        if annotation in (dict, dict[str, Any]):
            return {}
        if annotation in (list, list[str]):
            return []
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return _sample_for_model(annotation)
        return "e2e"

    if origin in (list, tuple, set):
        return []
    if origin is dict:
        return {}
    if origin is type(None):
        return None
    # Optional / Union
    for arg in args:
        if arg is not type(None):
            return _sample_for_type(name, arg)
    return "e2e"


def _sample_for_model(model_cls: type[BaseModel]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for fname, finfo in model_cls.model_fields.items():
        if finfo.is_required():
            out[fname] = _sample_for_type(fname, finfo.annotation)
    return out


def _sample_from_json_schema(schema: dict[str, Any], name: str = "") -> Any:
    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]

    sch_type = schema.get("type")
    if sch_type == "object":
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        out: dict[str, Any] = {}
        for key, sub in props.items():
            if key in required:
                out[key] = _sample_from_json_schema(sub, key)
        return out
    if sch_type == "array":
        return []
    if sch_type == "integer":
        return int(_sample_for_name(name) or 1)
    if sch_type == "number":
        return float(_sample_for_name(name) or 1.0)
    if sch_type == "boolean":
        return bool(_sample_for_name(name) if _sample_for_name(name) is not None else True)
    if sch_type == "string" or sch_type is None:
        return _sample_for_name(name) or "e2e"
    return "e2e"


def _parser_leaves(parser: argparse.ArgumentParser, prefix: list[str] | None = None) -> list[list[str]]:
    prefix = prefix or []
    leaves: list[list[str]] = []
    subparsers_actions = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    if not subparsers_actions:
        leaves.append(prefix)
        return leaves
    for action in subparsers_actions:
        for name, subparser in action.choices.items():
            if prefix and name in prefix:
                continue
            leaves.extend(_parser_leaves(subparser, [*prefix, name]))
    return leaves


def _iter_api_routes() -> list[tuple[str, str, APIRoute]]:
    pairs: list[tuple[str, str, APIRoute]] = []
    for route in fastapi_app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not (route.path == "/health" or route.path.startswith("/api/v1")):
            continue
        for method in sorted(route.methods or set()):
            if method in {"HEAD", "OPTIONS"}:
                continue
            pairs.append((method, route.path, route))
    pairs.sort(key=lambda x: (x[1], x[0]))
    return pairs


def _route_path_pattern(template: str) -> re.Pattern[str]:
    """Convert a FastAPI path template to a regex for route hit attribution."""
    out = ""
    i = 0
    while i < len(template):
        ch = template[i]
        if ch == "{":
            j = template.index("}", i)
            token = template[i + 1 : j]
            _, _, conv = token.partition(":")
            if conv == "path":
                out += ".+"
            else:
                out += "[^/]+"
            i = j + 1
            continue
        out += re.escape(ch)
        i += 1
    return re.compile("^" + out + "$")


_API_ROUTE_MATCHERS: list[tuple[str, str, re.Pattern[str]]] = [
    (method, path, _route_path_pattern(path)) for method, path, _ in _iter_api_routes()
]


def _match_route_key(method: str, actual_path: str) -> str | None:
    for m, path, pattern in _API_ROUTE_MATCHERS:
        if m == method and pattern.fullmatch(actual_path):
            return f"{m} {path}"
    return None


def _build_api_request(route: APIRoute, method: str) -> tuple[str, dict[str, Any], dict[str, Any] | None]:
    path = route.path
    params: dict[str, Any] = {}
    body: dict[str, Any] | None = None

    for p in route.dependant.path_params:
        value = _sample_for_type(getattr(p, "name", "id"), getattr(p, "type_", str))
        path = re.sub(r"\{" + re.escape(p.name) + r"(?::[^}]+)?\}", str(value), path)

    for p in route.dependant.query_params:
        name = getattr(p, "name", "")
        required = bool(getattr(p, "required", False))
        default = getattr(p, "default", None)
        if required or default is not None:
            params[name] = _sample_for_type(name, getattr(p, "type_", str))

    if method in {"POST", "PUT", "PATCH"} and getattr(route, "body_field", None) is not None:
        body_type = getattr(route.body_field, "type_", None)
        # For generic surface smoke, prefer schema validation (422) over mutating data.
        body = {}
        # But use a valid body for a small safe subset to prove real handling.
        if route.path in {
            "/api/v1/facts/search",
            "/api/v1/time-travel",
            "/api/v1/snapshots",
        } and body_type is not None and isinstance(body_type, type) and issubclass(body_type, BaseModel):
            body = _sample_for_model(body_type)
    return path, params, body


def _http_case(name: str, status_code: int, body_text: str) -> CaseResult:
    if status_code >= 500:
        return CaseResult(name=name, ok=False, category="fail", status_code=status_code, detail=body_text[:200])
    if status_code >= 400:
        spec = EXPECTED_API_SURFACE_WARNINGS.get(name)
        if spec and spec.get("status") == status_code and all(
            needle in body_text for needle in spec.get("contains", [])
        ):
            return CaseResult(name=name, ok=True, category="warn", status_code=status_code, detail=body_text[:200])
        expected_desc = ""
        if spec:
            expected_desc = f" expected_warn={spec}"
        return CaseResult(
            name=name,
            ok=False,
            category="fail",
            status_code=status_code,
            detail=f"unexpected_client_error status={status_code}{expected_desc} body={body_text[:200]}",
        )
    return CaseResult(name=name, ok=True, category="pass", status_code=status_code)


def _start_api(base_env: dict[str, str], host: str, port: int) -> tuple[subprocess.Popen[str], Path]:
    log_file = Path(tempfile.mkstemp(prefix="day1-e2e-api-", suffix=".log")[1])
    fh = open(log_file, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "day1.api.app:app", "--host", host, "--port", str(port)],
        cwd=str(_root()),
        env=base_env,
        stdout=fh,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc, log_file


def _stop_api(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _wait_health(base_url: str, timeout_s: float = 20.0) -> None:
    deadline = time.time() + timeout_s
    last_err = ""
    with httpx.Client(timeout=2.0, trust_env=False) as client:
        while time.time() < deadline:
            try:
                r = client.get(base_url + "/health")
                if r.status_code == 200:
                    return
                last_err = f"status={r.status_code}"
            except Exception as exc:  # pragma: no cover - startup race
                last_err = str(exc)
            time.sleep(0.5)
    raise RuntimeError(f"API health did not become ready: {last_err}")


def run_api_surface(base_url: str) -> SectionResult:
    section = SectionResult(name="api_surface")
    headers = {"Content-Type": "application/json"}
    if os.getenv("BM_API_KEY"):
        headers["Authorization"] = f"Bearer {os.environ['BM_API_KEY']}"

    with httpx.Client(base_url=base_url, timeout=5.0, trust_env=False) as client:
        for method, route_path, route in _iter_api_routes():
            name = f"{method} {route_path}"
            try:
                path, params, body = _build_api_request(route, method)
                resp = client.request(method, path, params=params or None, json=body, headers=headers)
                section.add(_http_case(name, resp.status_code, resp.text))
            except Exception as exc:
                section.add(CaseResult(name=name, ok=False, category="fail", detail=str(exc)))
    return section


def run_api_real_scenario(base_url: str) -> SectionResult:
    section = SectionResult(name="api_real")
    suffix = str(int(time.time()))
    branch = f"e2e-api-{suffix}"
    session_id = f"e2e-api-session-{suffix}"
    headers = {}
    if os.getenv("BM_API_KEY"):
        headers["Authorization"] = f"Bearer {os.environ['BM_API_KEY']}"
    route_hits: set[str] = set()

    with httpx.Client(base_url=base_url, timeout=10.0, trust_env=False, headers=headers) as client:
        def step(name: str, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
            r = client.request(method, url, **kwargs)
            route_key = _match_route_key(method, r.request.url.path)
            if route_key:
                route_hits.add(route_key)
            if r.status_code >= 500:
                raise RuntimeError(f"{name}: {r.status_code} {r.text[:200]}")
            if r.status_code >= 400:
                raise RuntimeError(f"{name}: {r.status_code} {r.text[:200]}")
            return r.json()

        try:
            client.get("/health").raise_for_status()
            section.add(CaseResult(name="GET /health", ok=True, category="pass"))
            step("create_branch", "POST", "/api/v1/branches", json={"branch_name": branch, "parent_branch": "main", "description": "e2e api scenario"})
            fact = step("create_fact", "POST", "/api/v1/facts", json={
                "fact_text": "E2E API scenario fact",
                "category": "integration",
                "branch": branch,
                "session_id": session_id,
                "metadata": {"entities": ["E2E", "API"]},
            })
            step("create_observation", "POST", "/api/v1/observations", json={
                "session_id": session_id,
                "observation_type": "tool_use",
                "summary": "E2E API observation",
                "tool_name": "httpx",
                "branch": branch,
            })
            step("create_relation", "POST", "/api/v1/relations", json={
                "source_entity": "E2E", "target_entity": "API", "relation_type": "tests", "branch": branch
            })
            search = step("search", "GET", "/api/v1/facts/search", params={"query": "E2E API scenario", "search_type": "keyword", "branch": branch, "limit": 5})
            if not search.get("count"):
                raise RuntimeError("API real search returned 0")
            step("graph", "GET", "/api/v1/relations/graph", params={"branch": branch})
            step("fact_related", "GET", f"/api/v1/facts/{fact['id']}/related", params={"branch": branch})
            step("snapshot", "POST", "/api/v1/snapshots", json={"branch": branch, "label": "e2e-api"})
            t = step("time_travel", "GET", "/api/v1/time-travel", params={"timestamp": "2099-01-01T00:00:00Z", "branch": branch, "limit": 5})
            if not isinstance(t.get("results"), list):
                raise RuntimeError("API time-travel malformed response")
            section.add(CaseResult(name="api_real_chain", ok=True, category="pass", extra={
                "branch": branch,
                "session_id": session_id,
                "fact_id": fact["id"],
                "route_hits": sorted(route_hits),
            }))
        except Exception as exc:
            section.add(CaseResult(name="api_real_chain", ok=False, category="fail", detail=str(exc)))
    return section


def run_api_agent_real_scenario(base_url: str) -> SectionResult:
    """Deeper API scenario simulating a realistic agent/task/dialogue workflow."""
    section = SectionResult(name="api_agent_real")
    suffix = str(int(time.time()))
    session_id = f"e2e-agent-session-{suffix}"
    agent_id = f"agent-{suffix}"
    base_branch = f"e2e-agent-base-{suffix}"
    target_branch = f"e2e-agent-target-{suffix}"
    curated_branch = f"e2e-agent-curated-{suffix}"
    import_branch = f"e2e-agent-import-{suffix}"
    cherry_branch = f"e2e-agent-cherry-{suffix}"
    template_name = f"E2E Agent Template {suffix}"
    template_inst_branch = f"e2e-agent-template-inst-{suffix}"
    task_name = f"E2E Agent Task {suffix}"
    headers = {}
    if os.getenv("BM_API_KEY"):
        headers["Authorization"] = f"Bearer {os.environ['BM_API_KEY']}"
    route_hits: set[str] = set()

    with httpx.Client(base_url=base_url, timeout=20.0, trust_env=False, headers=headers) as client:
        ids: dict[str, Any] = {}

        def step(name: str, method: str, url: str, *, expect: int | tuple[int, ...] = (200, 201), **kwargs: Any) -> Any:
            allowed = (expect,) if isinstance(expect, int) else expect
            r = client.request(method, url, **kwargs)
            route_key = _match_route_key(method, r.request.url.path)
            if route_key:
                route_hits.add(route_key)
            if r.status_code not in allowed:
                raise RuntimeError(f"{name}: expected {allowed}, got {r.status_code}: {r.text[:300]}")
            try:
                payload = r.json()
            except Exception:
                payload = {"raw": r.text}
            section.add(CaseResult(name=name, ok=True, category="pass", status_code=r.status_code))
            return payload

        def require(cond: bool, msg: str) -> None:
            if not cond:
                raise RuntimeError(msg)

        try:
            step("health", "GET", "/health")

            # Branch setup
            step("branch_create_base", "POST", "/api/v1/branches", json={"branch_name": base_branch, "parent_branch": "main", "description": "e2e agent base"})
            step("branch_create_target", "POST", "/api/v1/branches", json={"branch_name": target_branch, "parent_branch": "main", "description": "e2e agent target"})
            step("branch_create_import", "POST", "/api/v1/branches", json={"branch_name": import_branch, "parent_branch": "main", "description": "e2e agent import"})
            step("branch_create_cherry", "POST", "/api/v1/branches", json={"branch_name": cherry_branch, "parent_branch": "main", "description": "e2e agent cherry"})
            step("branch_validate_name", "POST", "/api/v1/branches/validate-name", json={"branch_name": curated_branch})
            step("branch_list", "GET", "/api/v1/branches")
            step("branch_topology", "GET", "/api/v1/branches/topology", params={"root_branch": "main", "max_depth": 10, "include_archived": False})
            step("branch_expired", "GET", "/api/v1/branches/expired")
            step("branch_auto_archive_dry_run", "POST", "/api/v1/branches/auto-archive", json={"inactive_days": 3650, "archive_merged": True, "dry_run": True})
            step("branch_enrich_base", "POST", f"/api/v1/branches/{base_branch}/enrich", json={"purpose": "e2e agent scenario", "owner": agent_id, "ttl_days": 30, "tags": ["e2e", "agent"]})
            step("branch_stats_base", "GET", f"/api/v1/branches/{base_branch}/stats")

            # Task + agent workflow
            task = step("task_create", "POST", "/api/v1/tasks", json={
                "name": task_name,
                "description": "Simulate a real agent conversation workflow",
                "task_type": "feature",
                "tags": ["e2e", "agent"],
                "objectives": [{"description": "collect facts"}, {"description": "produce replay"}],
                "parent_branch": base_branch,
            })
            ids["task_id"] = task["id"]
            ids["task_branch"] = task["branch_name"]
            step("task_list", "GET", "/api/v1/tasks", params={"task_type": "feature", "limit": 10})
            task_ctx = step("task_get", "GET", f"/api/v1/tasks/{ids['task_id']}")
            require(task_ctx["task"]["id"] == ids["task_id"], "task_get returned wrong task")
            join = step("task_join", "POST", f"/api/v1/tasks/{ids['task_id']}/join", json={"agent_id": agent_id, "role": "implementer", "assigned_objectives": [1]})
            ids["agent_branch"] = join["agent_branch"]
            step("task_objective_update_active", "PATCH", f"/api/v1/tasks/{ids['task_id']}/objectives/1", json={"status": "active", "agent_id": agent_id, "notes": "started"})

            # Conversation + messages on agent branch (real dialogue)
            conv = step("conversation_create", "POST", "/api/v1/conversations", json={
                "session_id": session_id,
                "agent_id": agent_id,
                "task_id": ids["task_id"],
                "branch": ids["agent_branch"],
                "title": "E2E agent dialogue",
                "model": "mock-model",
                "metadata": {"scenario": "e2e-agent"},
            })
            ids["conversation_id"] = conv["id"]
            msg1 = step("message_add_system", "POST", f"/api/v1/conversations/{ids['conversation_id']}/messages", json={
                "conversation_id": ids["conversation_id"],
                "role": "system",
                "content": "You are an implementation agent.",
                "token_count": 5,
                "model": "mock-model",
                "session_id": session_id,
                "agent_id": agent_id,
                "branch": ids["agent_branch"],
                "metadata": {"phase": "setup"},
            })
            msg2 = step("message_add_user", "POST", f"/api/v1/conversations/{ids['conversation_id']}/messages", json={
                "conversation_id": ids["conversation_id"],
                "role": "user",
                "content": "Implement strict E2E coverage and fix warnings.",
                "token_count": 12,
                "session_id": session_id,
                "branch": ids["agent_branch"],
            })
            ids["message_user_id"] = msg2["id"]
            batch = step("message_batch_add", "POST", f"/api/v1/conversations/{ids['conversation_id']}/messages/batch", json={
                "messages": [
                    {
                        "conversation_id": ids["conversation_id"],
                        "role": "assistant",
                        "content": "I will inspect endpoints and run strict coverage.",
                        "thinking": "Start with route enumeration and warn audit.",
                        "tool_calls": [{"name": "search_code", "args": {"pattern": "router.get"}}],
                        "token_count": 20,
                        "model": "mock-model",
                        "session_id": session_id,
                        "agent_id": agent_id,
                        "branch": ids["agent_branch"],
                    },
                    {
                        "conversation_id": ids["conversation_id"],
                        "role": "tool",
                        "content": "Found routes and warning hotspots.",
                        "token_count": 8,
                        "session_id": session_id,
                        "agent_id": agent_id,
                        "branch": ids["agent_branch"],
                    },
                ]
            })
            require(batch["count"] == 2, "batch message ingest count mismatch")
            msgs = step("message_list", "GET", f"/api/v1/conversations/{ids['conversation_id']}/messages", params={"limit": 20, "offset": 0})
            require(msgs["count"] >= 4, "message_list count too small")
            ids["message_assistant_id"] = msgs["messages"][2]["id"]
            step("message_get", "GET", f"/api/v1/messages/{ids['message_assistant_id']}")
            msg_search = step("message_search", "GET", "/api/v1/messages/search", params={"query": "strict coverage", "branch": ids["agent_branch"], "conversation_id": ids["conversation_id"], "session_id": session_id, "limit": 10})
            require(isinstance(msg_search.get("results"), list), "message_search malformed")
            step("conversation_list", "GET", "/api/v1/conversations", params={"session_id": session_id, "branch": ids["agent_branch"], "limit": 10, "offset": 0})
            step("conversation_get", "GET", f"/api/v1/conversations/{ids['conversation_id']}")

            # Facts / observations / relations (knowledge write path)
            fact = step("fact_create", "POST", "/api/v1/facts", json={
                "fact_text": "Strict E2E coverage must execute all API, CLI, and MCP surfaces without bypass.",
                "category": "testing",
                "confidence": 0.98,
                "source_type": "conversation",
                "session_id": session_id,
                "branch": ids["agent_branch"],
                "metadata": {"entities": ["E2E", "API", "CLI", "MCP"], "scenario": "e2e-agent"},
            })
            ids["fact_id"] = fact["id"]
            fact2 = step("fact_create_aux", "POST", "/api/v1/facts", json={
                "fact_text": "Warn classifications must distinguish validation errors from real defects.",
                "category": "testing",
                "confidence": 0.95,
                "session_id": session_id,
                "branch": ids["agent_branch"],
                "metadata": {"entities": ["warn", "defect"]},
            })
            ids["fact2_id"] = fact2["id"]
            step("fact_get", "GET", f"/api/v1/facts/{ids['fact_id']}")
            step("fact_patch", "PATCH", f"/api/v1/facts/{ids['fact_id']}", json={"metadata": {"entities": ["E2E", "API", "CLI", "MCP"], "strict": True}})
            facts_list = step("facts_list", "GET", "/api/v1/facts", params={"branch": ids["agent_branch"], "limit": 20})
            require(any(f["id"] == ids["fact_id"] for f in facts_list["facts"]), "facts_list missing fact")
            step("observation_create", "POST", "/api/v1/observations", json={
                "session_id": session_id,
                "observation_type": "tool_use",
                "summary": "Enumerated and executed API/CLI/MCP surfaces.",
                "tool_name": "e2e_surface.py",
                "raw_input": "strict mode",
                "raw_output": "pass/warn/fail matrix",
                "branch": ids["agent_branch"],
                "metadata": {"agent_id": agent_id},
            })
            step("observations_list", "GET", "/api/v1/observations", params={"branch": ids["agent_branch"], "session_id": session_id, "limit": 20})
            step("observations_timeline", "GET", "/api/v1/observations/timeline", params={"branch": ids["agent_branch"], "session_id": session_id, "limit": 20})
            rel = step("relation_create", "POST", "/api/v1/relations", json={
                "source_entity": "E2E",
                "target_entity": "StrictSurface",
                "relation_type": "validates",
                "properties": {"scope": ["api", "cli", "mcp"]},
                "confidence": 0.99,
                "session_id": session_id,
                "branch": ids["agent_branch"],
            })
            ids["relation_id"] = rel["id"]
            step("relations_list", "GET", "/api/v1/relations", params={"branch": ids["agent_branch"], "limit": 20})
            graph = step("relations_graph_snapshot", "GET", "/api/v1/relations/graph", params={"branch": ids["agent_branch"]})
            require(graph["mode"] in {"snapshot", "entity"}, "relations_graph malformed")
            step("relations_graph_entity", "GET", "/api/v1/relations/graph", params={"entity": "E2E", "branch": ids["agent_branch"], "depth": 1})
            step("fact_related", "GET", f"/api/v1/facts/{ids['fact_id']}/related", params={"branch": ids["agent_branch"], "limit": 10})

            # Search endpoints
            step("search_facts_get", "GET", "/api/v1/facts/search", params={"query": "strict E2E coverage", "search_type": "keyword", "branch": ids["agent_branch"], "limit": 10})
            step("search_facts_post", "POST", "/api/v1/facts/search", json={"query": "warn classifications", "search_type": "keyword", "branch": ids["agent_branch"], "limit": 10})
            step("search_observations", "GET", "/api/v1/observations/search", params={"query": "executed API", "branch": ids["agent_branch"], "session_id": session_id, "limit": 10})

            # Snapshot / time-travel
            snap = step("snapshot_create", "POST", "/api/v1/snapshots", json={"branch": ids["agent_branch"], "label": "e2e-agent"})
            ids["snapshot_id"] = snap["snapshot_id"]
            step("snapshots_list", "GET", "/api/v1/snapshots", params={"branch": ids["agent_branch"]})
            step("snapshot_get", "GET", f"/api/v1/snapshots/{ids['snapshot_id']}")
            step("time_travel_get", "GET", "/api/v1/time-travel", params={"timestamp": "2099-01-01T00:00:00Z", "branch": ids["agent_branch"], "limit": 20})
            step("time_travel_post", "POST", "/api/v1/time-travel", json={"timestamp": "2099-01-01T00:00:00Z", "branch": ids["agent_branch"], "limit": 20})

            # Conversation fork / diff / replay / semantic diff / complete
            fork = step("conversation_fork", "POST", f"/api/v1/conversations/{ids['conversation_id']}/fork", json={"message_id": ids["message_user_id"], "branch": cherry_branch, "title": "Forked dialogue"})
            ids["fork_conversation_id"] = fork["id"]
            step("conversation_diff", "GET", f"/api/v1/conversations/{ids['conversation_id']}/diff/{ids['fork_conversation_id']}")
            step("conversation_semantic_diff", "GET", f"/api/v1/conversations/{ids['conversation_id']}/semantic-diff/{ids['fork_conversation_id']}")
            step("conversation_cherry_pick", "POST", f"/api/v1/conversations/{ids['conversation_id']}/cherry-pick", json={"target_branch": target_branch})
            replay = step("conversation_replay_start", "POST", f"/api/v1/conversations/{ids['conversation_id']}/replay", json={
                "from_message_id": ids["message_user_id"],
                "system_prompt": "Re-evaluate warnings strictly.",
                "model": "mock-model",
                "extra_context": "Focus on distinguishing validation vs defects.",
                "branch": target_branch,
                "title": "Strict replay",
            })
            ids["replay_id"] = replay["replay_id"]
            step("replay_context", "GET", f"/api/v1/replays/{ids['replay_id']}/context")
            step("replay_diff", "GET", f"/api/v1/replays/{ids['replay_id']}/diff")
            step("replay_semantic_diff", "GET", f"/api/v1/replays/{ids['replay_id']}/semantic-diff")
            step("replay_list", "GET", "/api/v1/replays", params={"conversation_id": ids["conversation_id"], "session_id": session_id, "limit": 10})
            step("replay_complete", "POST", f"/api/v1/replays/{ids['replay_id']}/complete")
            step("conversation_complete", "POST", f"/api/v1/conversations/{ids['conversation_id']}/complete")

            # Scoring + verification
            step("score_create", "POST", "/api/v1/scores", json={
                "target_type": "conversation",
                "target_id": ids["conversation_id"],
                "scorer": "human",
                "dimension": "correctness",
                "value": 0.9,
                "explanation": "Good coverage and clear diagnostics.",
                "metadata": {"source": "e2e"},
                "branch": ids["agent_branch"],
                "session_id": session_id,
            })
            step("scores_list", "GET", "/api/v1/scores", params={"target_type": "conversation", "target_id": ids["conversation_id"], "limit": 20})
            step("conversation_evaluate", "POST", f"/api/v1/conversations/{ids['conversation_id']}/evaluate", json={"dimensions": ["correctness", "coherence"]})
            step("score_summary", "GET", f"/api/v1/scores/summary/conversation/{ids['conversation_id']}")
            step("verify_fact", "POST", f"/api/v1/facts/{ids['fact_id']}/verify", json={"dimensions": ["accuracy", "relevance"], "context": "E2E scenario"})
            step("verification_status", "GET", f"/api/v1/facts/{ids['fact_id']}/verification")
            step("verification_batch", "POST", "/api/v1/verification/batch", json={"branch_name": ids["agent_branch"], "limit": 20, "only_unverified": True})
            step("verification_verified", "GET", "/api/v1/verification/verified", params={"branch_name": ids["agent_branch"], "limit": 100})
            step("verification_merge_gate", "POST", "/api/v1/verification/merge-gate", json={"source_branch": ids["agent_branch"], "require_verified": False})
            step("verification_summary", "GET", f"/api/v1/verification/summary/{ids['agent_branch']}")

            # Sessions + analytics
            step("sessions_list", "GET", "/api/v1/sessions", params={"branch": ids["agent_branch"], "limit": 20})
            step("session_get", "GET", f"/api/v1/sessions/{session_id}")
            step("session_context", "GET", f"/api/v1/sessions/{session_id}/context", params={"message_limit": 20, "fact_limit": 20})
            step("analytics_overview", "GET", "/api/v1/analytics/overview", params={"branch": ids["agent_branch"], "days": 30})
            step("analytics_session", "GET", f"/api/v1/analytics/sessions/{session_id}")
            step("analytics_agent", "GET", f"/api/v1/analytics/agents/{agent_id}", params={"days": 30})
            step("analytics_trends", "GET", "/api/v1/analytics/trends", params={"branch": ids["agent_branch"], "days": 30, "granularity": "day"})
            step("analytics_conversation", "GET", f"/api/v1/analytics/conversations/{ids['conversation_id']}")

            # Handoff / bundle / template flows
            handoff = step("handoff_create", "POST", "/api/v1/handoffs", json={
                "source_branch": ids["agent_branch"],
                "target_branch": target_branch,
                "handoff_type": "agent_switch",
                "source_task_id": ids["task_id"],
                "source_agent_id": agent_id,
                "target_agent_id": f"{agent_id}-next",
                "include_unverified": True,
                "fact_ids": [ids["fact_id"], ids["fact2_id"]],
                "conversation_ids": [ids["conversation_id"]],
                "context_summary": "Strict E2E handoff packet.",
            })
            ids["handoff_id"] = handoff["handoff_id"]
            step("handoff_list", "GET", "/api/v1/handoffs", params={"source_branch": ids["agent_branch"], "target_branch": target_branch, "limit": 20})
            step("handoff_get", "GET", f"/api/v1/handoffs/{ids['handoff_id']}", params={"include_messages": True, "message_limit": 20})

            bundle = step("bundle_create", "POST", "/api/v1/bundles", json={
                "name": f"e2e-bundle-{suffix}",
                "source_branch": ids["agent_branch"],
                "description": "E2E agent bundle",
                "source_task_id": ids["task_id"],
                "tags": ["e2e", "agent"],
                "created_by": agent_id,
                "only_verified": False,
                "fact_ids": [ids["fact_id"], ids["fact2_id"]],
                "conversation_ids": [ids["conversation_id"]],
            })
            ids["bundle_id"] = bundle["id"]
            step("bundle_list", "GET", "/api/v1/bundles", params={"status": "active", "limit": 20})
            step("bundle_get", "GET", f"/api/v1/bundles/{ids['bundle_id']}")
            step("bundle_export", "GET", f"/api/v1/bundles/{ids['bundle_id']}/export")
            step("bundle_import", "POST", f"/api/v1/bundles/{ids['bundle_id']}/import", json={"target_branch": import_branch, "import_facts": True, "import_conversations": True, "import_relations": True})

            step("template_create", "POST", "/api/v1/templates", expect=201, json={
                "name": template_name,
                "source_branch": ids["agent_branch"],
                "description": "Reusable strict-e2e template",
                "applicable_task_types": ["feature"],
                "tags": ["e2e", "template"],
                "created_by": agent_id,
            })
            step("template_list", "GET", "/api/v1/templates", params={"task_type": "feature", "status": "active", "limit": 20})
            found = step("template_find", "GET", "/api/v1/templates/find", params={"task_type": "feature", "task_description": "Need strict e2e coverage"})
            require(found.get("template") is not None, "template_find returned none")
            step("template_get", "GET", f"/api/v1/templates/{template_name}")
            step("template_instantiate", "POST", f"/api/v1/templates/{template_name}/instantiate", json={"target_branch_name": template_inst_branch, "task_id": ids["task_id"]})
            step("template_update", "POST", f"/api/v1/templates/{template_name}/update", json={"source_branch": import_branch, "reason": "imported bundle regression pack"})
            step("template_deprecate", "POST", f"/api/v1/templates/{template_name}/deprecate")

            # Curated branch and branch diffs/merge/archive
            step("branch_create_curated", "POST", "/api/v1/branches/curated", expect=201, json={
                "branch_name": curated_branch,
                "parent_branch": "main",
                "conversation_ids": [ids["conversation_id"]],
                "fact_ids": [ids["fact_id"]],
                "description": "Curated branch from agent scenario",
            })
            step("branch_diff", "GET", f"/api/v1/branches/{import_branch}/diff", params={"target_branch": "main"})
            step("branch_diff_native", "GET", f"/api/v1/branches/{import_branch}/diff/native", params={"target_branch": "main"})
            step("branch_diff_native_count", "GET", f"/api/v1/branches/{import_branch}/diff/native/count", params={"target_branch": "main"})
            step("branch_merge", "POST", f"/api/v1/branches/{import_branch}/merge", json={"strategy": "auto", "target_branch": "main", "conflict": "skip"})

            # Task completion + replay/analytics endpoints that depend on task state
            step("task_consolidate_session", "POST", f"/api/v1/tasks/{ids['task_id']}/consolidate", json={"level": "session", "session_id": session_id, "agent_id": agent_id, "branch_name": ids["agent_branch"]})
            step("agent_timeline", "GET", f"/api/v1/agents/{agent_id}/timeline", params={"task_type": "feature", "limit": 20})
            step("task_type_analysis", "GET", "/api/v1/tasks/types/feature/analysis", params={"limit": 10})
            step("task_complete_agent", "POST", f"/api/v1/tasks/{ids['task_id']}/agents/{agent_id}/complete", json={"summary": "Completed strict E2E and real scenario validation."})
            step("task_complete", "POST", f"/api/v1/tasks/{ids['task_id']}/complete", json={"merge_to_main": False, "result_summary": "E2E workflow complete"})

            # Cleanup/archive one temporary branch via API path
            step("branch_archive_cherry", "DELETE", f"/api/v1/branches/{cherry_branch}")

            section.add(CaseResult(
                name="api_agent_real_summary",
                ok=True,
                category="pass",
                extra={
                    "session_id": session_id,
                    "agent_id": agent_id,
                    "base_branch": base_branch,
                    "target_branch": target_branch,
                    "curated_branch": curated_branch,
                    "import_branch": import_branch,
                    "cherry_branch": cherry_branch,
                    "template_name": template_name,
                    "template_inst_branch": template_inst_branch,
                    "task_branch": ids.get("task_branch"),
                    "task_id": ids.get("task_id"),
                    "conversation_id": ids.get("conversation_id"),
                    "fork_conversation_id": ids.get("fork_conversation_id"),
                    "fact_id": ids.get("fact_id"),
                    "fact2_id": ids.get("fact2_id"),
                    "snapshot_id": ids.get("snapshot_id"),
                    "relation_id": ids.get("relation_id"),
                    "handoff_id": ids.get("handoff_id"),
                    "bundle_id": ids.get("bundle_id"),
                    "replay_id": ids.get("replay_id"),
                    "route_hits": sorted(route_hits),
                },
            ))
        except Exception as exc:
            section.add(CaseResult(name="api_agent_real_summary", ok=False, category="fail", detail=str(exc)))
    return section


def run_cli_surface() -> SectionResult:
    section = SectionResult(name="cli_surface")
    parser = _build_parser()
    leaves = sorted(_parser_leaves(parser))
    env = _env_with_defaults()
    for leaf in leaves:
        if not leaf:
            continue
        cmd = ["uv", "run", "day1", *leaf]
        if leaf != ["help"]:
            cmd.append("--help")
        name = " ".join(cmd)
        proc = subprocess.run(cmd, cwd=str(_root()), env=env, capture_output=True, text=True)
        if proc.returncode == 0:
            section.add(CaseResult(name=name, ok=True, category="pass"))
        else:
            section.add(CaseResult(name=name, ok=False, category="fail", detail=(proc.stderr or proc.stdout)[:300]))
    return section


def run_cli_real(base_url: str) -> SectionResult:
    section = SectionResult(name="cli_real")
    env = _env_with_defaults()
    suffix = str(int(time.time()))
    branch = f"e2e-cli-{suffix}"
    session_id = f"e2e-cli-session-{suffix}"
    cmds = [
        ("branch_create", ["uv", "run", "day1", "branch", "create", branch, "--parent", "main", "--description", "e2e cli", "--format", "json"]),
        ("branch_list", ["uv", "run", "day1", "branch", "list", "--format", "json"]),
        ("branch_switch", ["uv", "run", "day1", "branch", "switch", branch, "--format", "json"]),
        ("write_fact", ["uv", "run", "day1", "write-fact", "E2E CLI scenario fact", "--branch", branch, "--category", "integration", "--session-id", session_id, "--format", "json"]),
        ("write_observation", ["uv", "run", "day1", "write-observation", "E2E CLI observation", "--observation-type", "tool_use", "--session-id", session_id, "--tool-name", "day1-cli", "--branch", branch, "--format", "json"]),
        ("search", ["uv", "run", "day1", "search", "E2E CLI scenario", "--search-type", "keyword", "--branch", branch, "--limit", "5", "--format", "json"]),
        ("snapshot_create", ["uv", "run", "day1", "snapshot", "create", "--branch", branch, "--label", "e2e-cli", "--format", "json"]),
        ("snapshot_list", ["uv", "run", "day1", "snapshot", "list", "--branch", branch, "--format", "json"]),
        ("time_travel", ["uv", "run", "day1", "time-travel", "2099-01-01T00:00:00Z", "--branch", branch, "--limit", "5", "--format", "json"]),
        ("health", ["uv", "run", "day1", "health", "--base-url", base_url, "--format", "json"]),
    ]
    manifest: dict[str, Any] = {"branch": branch, "session_id": session_id}
    for step_name, cmd in cmds:
        proc = subprocess.run(cmd, cwd=str(_root()), env=env, capture_output=True, text=True)
        if proc.returncode != 0:
            section.add(CaseResult(name=" ".join(cmd), ok=False, category="fail", detail=(proc.stderr or proc.stdout)[:500]))
            return section
        payload: Any = None
        try:
            payload = json.loads(proc.stdout)
        except Exception:
            payload = None
        if step_name == "write_fact" and isinstance(payload, dict):
            manifest["fact_id"] = payload.get("id")
        elif step_name == "write_observation" and isinstance(payload, dict):
            manifest["observation_id"] = payload.get("id")
        elif step_name == "snapshot_create" and isinstance(payload, dict):
            manifest["snapshot_id"] = payload.get("snapshot_id")
        elif step_name == "search" and isinstance(payload, dict):
            manifest["search_count"] = payload.get("count")
        elif step_name == "time_travel" and isinstance(payload, dict):
            manifest["time_travel_count"] = payload.get("count")
        elif step_name == "health" and isinstance(payload, dict):
            manifest["health_status"] = payload.get("status")
        section.add(CaseResult(name=" ".join(cmd), ok=True, category="pass"))
    section.add(CaseResult(name="cli_real_summary", ok=True, category="pass", extra=manifest))
    return section


def _mcp_schema_args(tool_name: str, schema: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    args = _sample_from_json_schema(schema)
    if not isinstance(args, dict):
        args = {}

    # Make common generated requests safer and more realistic.
    if "branch" in args:
        args["branch"] = ctx["branch"]
    if "session_id" in args and ctx.get("session_id"):
        args["session_id"] = ctx["session_id"]
    if "conversation_id" in args and ctx.get("conversation_id"):
        args["conversation_id"] = ctx["conversation_id"]
    if "message_id" in args and ctx.get("message_id"):
        args["message_id"] = ctx["message_id"]
    if "from_message_id" in args and ctx.get("message_id"):
        args["from_message_id"] = ctx["message_id"]
    if "fact_id" in args and ctx.get("fact_id"):
        args["fact_id"] = ctx["fact_id"]
    if "handoff_id" in args and ctx.get("handoff_id"):
        args["handoff_id"] = ctx["handoff_id"]
    if "bundle_id" in args and ctx.get("bundle_id"):
        args["bundle_id"] = ctx["bundle_id"]
    if "replay_id" in args and ctx.get("replay_id"):
        args["replay_id"] = ctx["replay_id"]
    if "conversation_a" in args and ctx.get("conversation_id"):
        args["conversation_a"] = ctx["conversation_id"]
    if "conversation_b" in args and ctx.get("fork_conversation_id"):
        args["conversation_b"] = ctx["fork_conversation_id"]
    if tool_name == "memory_branch_create":
        args["branch_name"] = f"{ctx['branch']}-secondary"
        args.setdefault("parent_branch", "main")
    if tool_name == "memory_branch_switch":
        args["branch_name"] = ctx["branch"]
    if tool_name == "memory_branch_diff":
        args["source_branch"] = ctx["branch"]
        args["target_branch"] = "main"
    if tool_name == "memory_branch_merge":
        args["source_branch"] = ctx["branch"]
        args.setdefault("target_branch", "main")
        args.setdefault("strategy", "auto")
    if tool_name == "memory_task_create":
        args["name"] = f"e2e-task-{int(time.time())}"
        args.setdefault("parent_branch", "main")
        args.setdefault("objectives", [{"description": "surface smoke objective"}])
    if tool_name in {"memory_task_join", "memory_task_status", "memory_task_update"} and ctx.get("task_id"):
        args["task_id"] = ctx["task_id"]
    if tool_name == "memory_task_join":
        args["agent_id"] = ctx.get("agent_id", "e2e-agent")
        args.setdefault("objectives", [1])
    if tool_name == "memory_task_update":
        args["objective_id"] = 1
        args["objective_status"] = "done"
        args.setdefault("agent_id", ctx.get("agent_id", "e2e-agent"))
    if tool_name == "memory_search":
        args["search_type"] = "keyword"
        args["query"] = "e2e"
        args["branch"] = ctx["branch"]
    if tool_name == "memory_graph_query":
        args["entity"] = "e2e-entity"
        args["branch"] = ctx["branch"]
    if tool_name == "memory_branch_enrich":
        args["branch_name"] = ctx["branch"]
        args.setdefault("owner", ctx.get("agent_id", "e2e-mcp-agent"))
    if tool_name == "memory_log_message":
        args["session_id"] = ctx.setdefault("session_id", f"e2e-mcp-session-{int(time.time())}")
        args["role"] = "user"
        args["content"] = "MCP surface seeded message for downstream tools."
    if tool_name == "memory_fork_conversation" and ctx.get("conversation_id") and ctx.get("message_id"):
        args["conversation_id"] = ctx["conversation_id"]
        args["message_id"] = ctx["message_id"]
        args.setdefault("branch", ctx["branch"])
    if tool_name == "memory_cherry_pick_conversation" and ctx.get("conversation_id"):
        args["conversation_id"] = ctx["conversation_id"]
        args["target_branch"] = ctx["branch"]
    if tool_name == "memory_branch_create_curated":
        args["branch_name"] = f"e2e-curated-{int(time.time())}"
        args.setdefault("parent_branch", "main")
        if ctx.get("conversation_id"):
            args["conversation_ids"] = [ctx["conversation_id"]]
        if ctx.get("fact_id"):
            args["fact_ids"] = [ctx["fact_id"]]
    if tool_name == "memory_snapshot_list":
        args["branch"] = ctx["branch"]
    if tool_name == "memory_time_travel":
        args["timestamp"] = "2099-01-01T00:00:00Z"
        args["branch"] = ctx["branch"]
        args.setdefault("query", "e2e")
    if tool_name == "replay_conversation" and ctx.get("conversation_id") and ctx.get("message_id"):
        args["conversation_id"] = ctx["conversation_id"]
        args["from_message_id"] = ctx["message_id"]
        args.setdefault("title", "e2e replay")
    if tool_name == "replay_diff" and ctx.get("replay_id"):
        args["replay_id"] = ctx["replay_id"]
    if tool_name == "semantic_diff":
        if ctx.get("conversation_id"):
            args["conversation_a"] = ctx["conversation_id"]
        if ctx.get("fork_conversation_id"):
            args["conversation_b"] = ctx["fork_conversation_id"]
    if tool_name == "analytics_session" and ctx.get("session_id"):
        args["session_id"] = ctx["session_id"]
    if tool_name == "score_conversation" and ctx.get("conversation_id"):
        args["conversation_id"] = ctx["conversation_id"]
    if tool_name == "memory_template_create":
        args["name"] = f"E2E MCP Template {int(time.time())}"
        args["source_branch"] = ctx["branch"]
        args.setdefault("applicable_task_types", ["feature"])
    if tool_name == "memory_template_instantiate" and ctx.get("template_name"):
        args["template_name"] = ctx["template_name"]
        args["target_branch_name"] = f"e2e-mcp-template-inst-{int(time.time())}"
    if tool_name == "verify_fact" and ctx.get("fact_id"):
        args["fact_id"] = ctx["fact_id"]
    if tool_name == "memory_handoff_create":
        args["source_branch"] = ctx["branch"]
        args["target_branch"] = "main"
    if tool_name == "memory_handoff_get" and ctx.get("handoff_id"):
        args["handoff_id"] = ctx["handoff_id"]
    if tool_name == "knowledge_bundle_create":
        args["name"] = f"e2e-mcp-bundle-{int(time.time())}"
        args["source_branch"] = ctx["branch"]
        args.setdefault("only_verified", False)
    if tool_name == "knowledge_bundle_import" and ctx.get("bundle_id"):
        args["bundle_id"] = ctx["bundle_id"]
        args["target_branch"] = "main"
    return args


async def run_mcp_surface(mcp_url: str) -> SectionResult:
    section = SectionResult(name="mcp_surface")
    ctx = {"branch": f"e2e-mcp-{int(time.time())}", "agent_id": "e2e-mcp-agent"}
    async with _mcp_http_session(mcp_url) as (mcp, get_mcp_session_id):
        listed = await mcp.list_tools()
        if len(listed.tools) != len(TOOL_DEFINITIONS):
            section.add(
                CaseResult(
                    name="mcp_list_tools_count",
                    ok=False,
                    category="fail",
                    detail=f"listed={len(listed.tools)} expected={len(TOOL_DEFINITIONS)}",
                )
            )
            return section

        # Pre-create/switch one branch for downstream tool smoke.
        await mcp.call_tool("memory_branch_create", {"branch_name": ctx["branch"], "parent_branch": "main", "description": "e2e mcp"})
        await mcp.call_tool("memory_branch_switch", {"branch_name": ctx["branch"]})
        # Seed one fact + one conversation message so downstream tools can use real IDs.
        fact_seed = _mcp_parse_tool_payload(
            await mcp.call_tool(
                "memory_write_fact",
                {"fact_text": "e2e mcp seeded fact", "category": "testing", "branch": ctx["branch"]},
            )
        )
        if "id" in fact_seed:
            ctx["fact_id"] = fact_seed["id"]
        ctx["session_id"] = f"e2e-mcp-session-{int(time.time())}"
        msg_seed = _mcp_parse_tool_payload(
            await mcp.call_tool(
                "memory_log_message",
                {"role": "user", "content": "seed", "session_id": ctx["session_id"]},
            )
        )
        if isinstance(msg_seed, dict):
            ctx["conversation_id"] = msg_seed.get("conversation_id")
            ctx["message_id"] = msg_seed.get("id")

        for tool in listed.tools:
            tool_name = tool.name
            args = _mcp_schema_args(tool_name, tool.inputSchema or {}, ctx)
            try:
                res = await mcp.call_tool(tool_name, args)
                payload = _mcp_parse_tool_payload(res)
                if isinstance(payload, dict):
                    if tool_name == "memory_task_create":
                        if "task_id" in payload:
                            ctx["task_id"] = payload["task_id"]
                        elif "id" in payload:
                            ctx["task_id"] = payload["id"]
                    if tool_name == "memory_task_join" and "agent_branch" in payload:
                        ctx["agent_branch"] = payload["agent_branch"]
                    if tool_name == "memory_fork_conversation" and "conversation_id" in payload:
                        ctx["fork_conversation_id"] = payload["conversation_id"]
                    if tool_name == "replay_conversation" and "replay_id" in payload:
                        ctx["replay_id"] = payload["replay_id"]
                    if tool_name == "memory_template_create" and "name" in payload:
                        ctx["template_name"] = payload["name"]
                    if tool_name == "memory_handoff_create" and "handoff_id" in payload:
                        ctx["handoff_id"] = payload["handoff_id"]
                    if tool_name == "knowledge_bundle_create" and "id" in payload:
                        ctx["bundle_id"] = payload["id"]
                # MCP boundary smoke: any structured JSON response counts as endpoint reachable.
                if isinstance(payload, dict) and "error" in payload:
                    err_text = str(payload["error"])
                    spec = EXPECTED_MCP_SURFACE_WARNINGS.get(tool_name)
                    if spec and all(needle in err_text for needle in spec.get("contains", [])):
                        section.add(CaseResult(name=tool_name, ok=True, category="warn", detail=err_text[:200]))
                    else:
                        section.add(CaseResult(name=tool_name, ok=False, category="fail", detail=f"unexpected_mcp_error: {err_text[:200]}"))
                else:
                    section.add(CaseResult(name=tool_name, ok=True, category="pass"))
            except Exception as exc:
                section.add(CaseResult(name=tool_name, ok=False, category="fail", detail=str(exc)))

        section.add(
            CaseResult(
                name="mcp_surface_summary",
                ok=True,
                category="pass",
                extra={
                    "transport": "streamable_http",
                    "mcp_url": mcp_url,
                    "mcp_session_id": get_mcp_session_id(),
                    "listed_tools": len(listed.tools),
                    "ctx": {
                        k: v
                        for k, v in ctx.items()
                        if k
                        in {
                            "branch",
                            "session_id",
                            "conversation_id",
                            "message_id",
                            "fork_conversation_id",
                            "fact_id",
                            "task_id",
                            "handoff_id",
                            "bundle_id",
                            "replay_id",
                            "template_name",
                        }
                    },
                },
            )
        )
    return section


async def run_mcp_real(mcp_url: str) -> SectionResult:
    section = SectionResult(name="mcp_real")
    suffix = str(int(time.time()))
    branch = f"e2e-mcp-real-{suffix}"
    manifest: dict[str, Any] = {"branch": branch, "transport": "streamable_http", "mcp_url": mcp_url}
    try:
        async with _mcp_http_session(mcp_url) as (mcp, get_mcp_session_id):
            for name, args in [
                ("memory_branch_create", {"branch_name": branch, "parent_branch": "main", "description": "e2e mcp real"}),
                ("memory_branch_switch", {"branch_name": branch}),
                ("memory_write_fact", {"fact_text": "E2E MCP scenario fact", "category": "integration"}),
                ("memory_write_observation", {"observation_type": "tool_use", "summary": "E2E MCP observation", "tool_name": "mcp", "session_id": f"mcp-{suffix}"}),
                ("memory_write_relation", {"source_entity": "E2E", "target_entity": "MCP", "relation_type": "tests"}),
                ("memory_search", {"query": "E2E MCP scenario", "search_type": "keyword", "branch": branch, "limit": 5}),
                ("memory_graph_query", {"entity": "E2E", "branch": branch, "depth": 1}),
                ("memory_snapshot", {"branch": branch, "label": "e2e-mcp"}),
                ("memory_snapshot_list", {"branch": branch}),
                (
                    "memory_time_travel",
                    {
                        "branch": branch,
                        "timestamp": "2099-01-01T00:00:00Z",
                        "query": "E2E MCP",
                    },
                ),
            ]:
                payload = _mcp_parse_tool_payload(await mcp.call_tool(name, args))
                if "error" in payload:
                    raise RuntimeError(f"{name}: {payload['error']}")
                if name == "memory_write_fact":
                    manifest["fact_id"] = payload.get("id")
                elif name == "memory_snapshot":
                    manifest["snapshot_id"] = payload.get("snapshot_id")
                section.add(CaseResult(name=name, ok=True, category="pass"))
            manifest["mcp_session_id"] = get_mcp_session_id()
            section.add(CaseResult(name="mcp_real_summary", ok=True, category="pass", extra=manifest))
    except Exception as exc:
        section.add(CaseResult(name="mcp_real_chain", ok=False, category="fail", detail=str(exc)))
    return section


def _section_to_summary(sec: SectionResult) -> dict[str, Any]:
    return {
        "name": sec.name,
        "total": sec.total,
        "passed": sec.passed,
        "warnings": sec.warnings,
        "failed": sec.failed,
        "failures": [asdict(c) for c in sec.cases if not c.ok],
        "warnings_detail": [asdict(c) for c in sec.cases if c.ok and c.category == "warn"],
    }


def _collect_real_dataset(report_sections: list[SectionResult]) -> dict[str, Any]:
    dataset: dict[str, Any] = {}
    for sec in report_sections:
        sec_data: dict[str, Any] = {}
        for case in sec.cases:
            if case.ok and case.extra:
                sec_data[case.name] = case.extra
        if sec_data:
            dataset[sec.name] = sec_data
    return dataset


def _compute_api_real_route_coverage(report_sections: list[SectionResult]) -> dict[str, Any]:
    hit_set: set[str] = set()
    for sec in report_sections:
        if sec.name not in {"api_real", "api_agent_real"}:
            continue
        for case in sec.cases:
            if case.ok and isinstance(case.extra, dict):
                for route_key in case.extra.get("route_hits", []) or []:
                    hit_set.add(route_key)
    all_keys = {f"{m} {p}" for m, p, _ in _iter_api_routes()}
    missing = sorted(all_keys - hit_set)
    return {
        "covered": len(hit_set),
        "total": len(all_keys),
        "all_covered": not missing,
        "missing": missing,
        "covered_routes": sorted(hit_set),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Day1 API/CLI/MCP E2E surface coverage")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--json", action="store_true", help="Print full JSON report")
    parser.add_argument("--output", help="Write full JSON report to a file")
    parser.add_argument(
        "--real-only",
        action="store_true",
        help="Run only valid-input real scenarios / exhaustive valid MCP tools (skip negative surface API/CLI help smoke)",
    )
    args = parser.parse_args()

    env = _env_with_defaults()
    base_url = f"http://{args.host}:{args.port}"

    mcp_url = f"{base_url}/mcp"
    report: dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_url": base_url,
        "mcp_url": mcp_url,
        "mcp_transport": "streamable_http",
    }
    api_proc, api_log = _start_api(env, args.host, args.port)
    try:
        _wait_health(base_url)
        api_real = run_api_real_scenario(base_url)
        api_agent_real = run_api_agent_real_scenario(base_url)
        cli_real = run_cli_real(base_url)
        mcp_surface = asyncio.run(run_mcp_surface(mcp_url))
        mcp_real = asyncio.run(run_mcp_real(mcp_url))
        sections: list[SectionResult] = []
        if not args.real_only:
            sections.append(run_api_surface(base_url))
        sections.extend([api_real, api_agent_real])
        if not args.real_only:
            sections.append(run_cli_surface())
        sections.extend([cli_real, mcp_surface, mcp_real])
    finally:
        _stop_api(api_proc)
        report["api_log_path"] = str(api_log)

    report["sections"] = [_section_to_summary(s) for s in sections]
    report["totals"] = {
        "total": sum(s.total for s in sections),
        "passed": sum(s.passed for s in sections),
        "warnings": sum(s.warnings for s in sections),
        "failed": sum(s.failed for s in sections),
    }
    report["real_dataset"] = _collect_real_dataset(sections)
    report["api_real_route_coverage"] = _compute_api_real_route_coverage(sections)
    if args.real_only and not report["api_real_route_coverage"]["all_covered"]:
        report["totals"]["failed"] += 1
        report.setdefault("meta_failures", []).append({
            "name": "api_real_route_coverage",
            "detail": f"Missing valid-input coverage for {len(report['api_real_route_coverage']['missing'])} routes",
        })

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for sec in report["sections"]:
            print(f"{sec['name']}: total={sec['total']} passed={sec['passed']} warn={sec['warnings']} failed={sec['failed']}")
        print("totals:", report["totals"])
        print("api_log_path:", report["api_log_path"])
        if "api_real_route_coverage" in report:
            cov = report["api_real_route_coverage"]
            print("api_real_route_coverage:", f"{cov['covered']}/{cov['total']}", "all_covered=", cov["all_covered"])
        if report["totals"]["failed"]:
            for sec in report["sections"]:
                for fail in sec["failures"]:
                    print(f"FAIL {sec['name']} :: {fail['name']} :: {fail['detail']}")
            for meta_fail in report.get("meta_failures", []):
                print(f"FAIL meta :: {meta_fail['name']} :: {meta_fail['detail']}")

    return 1 if report["totals"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
