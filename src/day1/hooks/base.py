"""Base utilities for Claude Code hooks.

Hooks are invoked as shell commands by Claude Code.
They read input from environment variables and stdin,
and write output to stdout as JSON.

CRITICAL: Hooks must NEVER crash (exit non-zero blocks Claude Code).
All exceptions are caught and {} is returned as a safe fallback.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import json
import logging
import os
import sys

logger = logging.getLogger(__name__)

# Simple debug log file for hooks (controlled by BM_HOOKS_DEBUG env var)
_DEBUG_LOG_PATH = os.path.expanduser("~/day1_hooks_debug.log")


def _debug_log(message: str) -> None:
    """Write to debug log file if debug mode is enabled."""
    try:
        from day1.config import settings

        if not settings.hooks_debug:
            return
    except Exception:
        return  # Fail silently if config can't be loaded

    try:
        with open(_DEBUG_LOG_PATH, "a") as f:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass  # Don't fail if logging fails


@asynccontextmanager
async def get_db_session() -> AsyncGenerator:
    """Context manager for getting a database session in hooks.

    Yields a session or None if database is unreachable.
    The session is automatically closed when exiting the context.

    Usage:
        async with get_db_session() as session:
            if session:
                ... use session ...
        # Session automatically closed here
    """
    try:
        from day1.db.engine import get_session, init_db

        await init_db()

        # get_session() is an async generator that yields exactly one session
        async for session in get_session():
            try:
                yield session
            finally:
                await session.close()
            return  # Exit after first (and only) iteration
    except Exception as exc:
        _debug_log(f"[get_db_session] ERROR: {type(exc).__name__}: {exc}")
        logger.debug("Hook DB connection failed (non-fatal): %s", exc)
        yield None


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

    hook_name = handler_fn.__name__ if hasattr(handler_fn, '__name__') else 'unknown'
    _debug_log(f"=== Hook START: {hook_name} ===")

    try:
        input_data = read_hook_input()
        _debug_log(f"  input_data keys: {list(input_data.keys()) if input_data else 'None'}")

        if takes_input:
            result = asyncio.run(handler_fn(input_data))
        else:
            result = asyncio.run(handler_fn())
        write_hook_output(result or {})
    except Exception as exc:
        logger.debug("Hook failed (non-fatal): %s", exc)
        _debug_log(f"  ERROR: {type(exc).__name__}: {exc}")
        write_hook_output({})

    _debug_log(f"=== Hook END: {hook_name} ===\n")


def get_session_id() -> str:
    """Get current session ID from env or generate one.

    Workaround: Claude Code doesn't pass CLAUDE_SESSION_ID to hooks yet.
    We use project_path + start_time to separate different sessions.

    The start_time is stored in a project-local .day1_session file when
    the first hook runs, and reused for subsequent hooks in the same session.
    """
    # First try explicit session IDs
    sid = os.environ.get("CLAUDE_SESSION_ID") or os.environ.get("SESSION_ID")
    if sid:
        return sid

    # Get project path
    project_path = os.environ.get("CLAUDE_PROJECT_PATH")
    if not project_path:
        project_path = os.getcwd()

    # Path to store session start time
    session_file = os.path.join(project_path, ".day1_session")
    import hashlib

    # Try to get existing session start time
    if os.path.exists(session_file):
        try:
            with open(session_file, "r") as f:
                start_time = f.read().strip()
            if start_time:
                path_hash = hashlib.md5(project_path.encode()).hexdigest()[:12]
                return f"project-{path_hash}-{start_time}"
        except Exception:
            pass

    # Create new session start time
    from datetime import datetime
    start_time = datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        with open(session_file, "w") as f:
            f.write(start_time)
    except Exception:
        pass  # Fail silently if we can't write the session file

    path_hash = hashlib.md5(project_path.encode()).hexdigest()[:12]
    return f"project-{path_hash}-{start_time}"


def get_project_path() -> str:
    """Get current project path."""
    return os.environ.get("CLAUDE_PROJECT_PATH", os.getcwd())
