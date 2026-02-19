"""CLI entry point for Day1.

Usage:
    uv run day1 <command>

Commands:
    test        Run MatrixOne feature tests
    api         Start the FastAPI server
    dashboard   Start the React dashboard
    migrate     Run database migrations
    help        Show this help message
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    """Locate the project root (directory containing pyproject.toml)."""
    here = Path(__file__).resolve().parent
    for ancestor in (here, *here.parents):
        if (ancestor / "pyproject.toml").exists():
            return ancestor
    return Path.cwd()


def cmd_test() -> int:
    """Run MatrixOne feature verification tests."""
    return subprocess.call(
        [sys.executable, str(_project_root() / "scripts" / "test_mo_features.py")]
    )


def cmd_api() -> int:
    """Start the FastAPI server."""
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "day1.api.app:app",
            "--reload",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ]
    )


def cmd_dashboard() -> int:
    """Start the React dashboard dev server."""
    dashboard_dir = _project_root() / "dashboard"
    if not (dashboard_dir / "node_modules").exists():
        subprocess.call(["npm", "install"], cwd=str(dashboard_dir))
    return subprocess.call(["npm", "run", "dev"], cwd=str(dashboard_dir))


def cmd_migrate() -> int:
    """Run database migrations."""
    return subprocess.call(
        [sys.executable, str(_project_root() / "scripts" / "migrate.py")]
    )


_COMMANDS = {
    "test": cmd_test,
    "api": cmd_api,
    "dashboard": cmd_dashboard,
    "migrate": cmd_migrate,
}

_HELP = """\
Day1 - Git-like memory layer for AI agents

Usage: day1 <command>

Commands:
  test        Verify MatrixOne connection & features
  api         Start FastAPI server (:8000)
  dashboard   Start React dashboard (:5173)
  migrate     Run database migrations
  help        Show this help message

Environment:
  BM_DATABASE_URL   MatrixOne connection string (see .env.example)
"""


def main() -> None:
    """CLI entry point dispatching to sub-commands."""
    args = sys.argv[1:]
    command = args[0] if args else "help"

    if command in ("help", "--help", "-h"):
        print(_HELP)
        sys.exit(0)

    handler = _COMMANDS.get(command)
    if handler is None:
        print(f"Unknown command: {command}", file=sys.stderr)
        print(_HELP, file=sys.stderr)
        sys.exit(1)

    sys.exit(handler())


if __name__ == "__main__":
    main()
