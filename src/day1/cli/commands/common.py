"""Shared helpers for CLI commands."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from day1.core.branch_manager import BranchManager
from day1.db.engine import close_db, get_session, init_db

ACTIVE_BRANCH = "main"


@dataclass
class CommandOutput:
    payload: Any
    format: str = "table"


def get_active_branch() -> str:
    return (
        os.environ.get("BM_BRANCH")
        or os.environ.get("BM_DEFAULT_BRANCH")
        or ACTIVE_BRANCH
    )


def set_active_branch(branch_name: str) -> None:
    global ACTIVE_BRANCH
    ACTIVE_BRANCH = branch_name


def run_async(coro: Awaitable[int | None]) -> int:
    async def _runner() -> int | None:
        try:
            return await coro
        finally:
            await close_db()

    return int(asyncio.run(_runner()) or 0)


async def with_session(fn: Callable[[Any], Awaitable[Any]]) -> Any:
    await init_db()
    session_gen = get_session()
    session = await anext(session_gen)
    try:
        await BranchManager(session).ensure_main_branch()
        return await fn(session)
    finally:
        await session_gen.aclose()


def parse_json_arg(value: str | None) -> dict[str, Any] | None:
    if value is None:
        return None
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("metadata/properties must be a JSON object")
    return parsed


def parse_json_list_arg(value: str | None) -> list[Any] | None:
    if value is None:
        return None
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError("value must be a JSON array")
    return parsed


def emit(payload: Any, fmt: str = "table") -> None:
    if fmt == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return
    if fmt == "text":
        _emit_text(payload)
        return

    if isinstance(payload, dict):
        if "branches" in payload and isinstance(payload["branches"], list):
            _print_rows(payload["branches"])
            return
        if "snapshots" in payload and isinstance(payload["snapshots"], list):
            _print_rows(payload["snapshots"])
            return
        if "results" in payload and isinstance(payload["results"], list):
            _print_rows(payload["results"])
            return
        if "timeline" in payload and isinstance(payload["timeline"], list):
            _print_rows(payload["timeline"])
            return
        _print_kv(payload)
        return

    if isinstance(payload, list):
        _print_rows(payload)
        return

    print(payload)


def _print_kv(data: dict[str, Any]) -> None:
    for key, value in data.items():
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, default=str)
        print(f"{key}: {value}")


def _print_rows(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("(empty)")
        return

    keys: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in keys:
                keys.append(key)

    widths = {key: len(key) for key in keys}
    string_rows: list[dict[str, str]] = []
    for row in rows:
        rendered: dict[str, str] = {}
        for key in keys:
            value = row.get(key, "")
            if isinstance(value, (dict, list)):
                text = json.dumps(value, ensure_ascii=False, default=str)
            else:
                text = str(value)
            rendered[key] = text
            widths[key] = max(widths[key], len(text))
        string_rows.append(rendered)

    header = " | ".join(key.ljust(widths[key]) for key in keys)
    sep = "-+-".join("-" * widths[key] for key in keys)
    print(header)
    print(sep)
    for row in string_rows:
        print(" | ".join(row[key].ljust(widths[key]) for key in keys))


def _emit_text(payload: Any) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, list):
                print(f"{key}:")
                for item in value:
                    if isinstance(item, dict):
                        print("- " + ", ".join(f"{k}={item.get(k)}" for k in item))
                    else:
                        print(f"- {item}")
            elif isinstance(value, dict):
                print(f"{key}:")
                for sub_key, sub_value in value.items():
                    print(f"  {sub_key}: {sub_value}")
            else:
                print(f"{key}: {value}")
        return
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                print(", ".join(f"{k}={item.get(k)}" for k in item))
            else:
                print(item)
        return
    print(payload)
