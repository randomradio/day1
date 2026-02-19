"""Base utilities for Claude Code hooks.

Hooks are invoked as shell commands by Claude Code.
They read input from environment variables and stdin,
and write output to stdout as JSON.
"""

from __future__ import annotations

import json
import os
import sys

from day1.db.engine import get_session, init_db


async def get_db_session():
    """Get a database session for hook use."""
    await init_db()
    async for session in get_session():
        return session
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


def get_session_id() -> str:
    """Get current session ID from env or generate one."""
    return os.environ.get("CLAUDE_SESSION_ID", os.environ.get("SESSION_ID", "unknown"))


def get_project_path() -> str:
    """Get current project path."""
    return os.environ.get("CLAUDE_PROJECT_PATH", os.getcwd())
