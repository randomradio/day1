"""Base utilities for Claude Code hooks.

Hooks are invoked as shell commands by Claude Code.
They read input from environment variables and stdin,
and write output to stdout as JSON.

CRITICAL: Hooks must NEVER crash (exit non-zero blocks Claude Code).
All exceptions are caught and {} is returned as a safe fallback.
"""

from __future__ import annotations

import json
import logging
import os
import sys

logger = logging.getLogger(__name__)


async def get_db_session():
    """Get a database session for hook use.

    Returns None (never raises) if the database is unreachable.
    """
    try:
        from day1.db.engine import get_session, init_db

        await init_db()
        async for session in get_session():
            return session
    except Exception as exc:
        logger.debug("Hook DB connection failed (non-fatal): %s", exc)
    return None


def read_hook_input() -> dict:
    """Read hook input from stdin (Claude Code sends JSON)."""
    try:
        if not sys.stdin.isatty():
            data = sys.stdin.read()
            if data.strip():
                return json.loads(data)
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def write_hook_output(output: dict) -> None:
    """Write hook output to stdout as JSON."""
    json.dump(output, sys.stdout)
    sys.stdout.write("\n")
    sys.stdout.flush()


def run_hook(handler_fn, *, takes_input: bool = True) -> None:
    """Standard hook entry point with crash protection.

    Wraps the async handler in try/except so hooks never crash.
    Always outputs valid JSON to stdout (at minimum ``{}``).

    Args:
        handler_fn: Async handler coroutine.
        takes_input: If True, reads stdin and passes to handler.
                     If False (e.g. SessionStart), calls handler with no args.
    """
    import asyncio

    try:
        input_data = read_hook_input()
        if takes_input:
            result = asyncio.run(handler_fn(input_data))
        else:
            result = asyncio.run(handler_fn())
        write_hook_output(result or {})
    except Exception as exc:
        logger.debug("Hook failed (non-fatal): %s", exc)
        write_hook_output({})


def get_session_id() -> str:
    """Get current session ID from env or generate one."""
    return os.environ.get("CLAUDE_SESSION_ID", os.environ.get("SESSION_ID", "unknown"))


def get_project_path() -> str:
    """Get current project path."""
    return os.environ.get("CLAUDE_PROJECT_PATH", os.getcwd())
