"""System / process wrapper CLI commands."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import httpx

from day1.cli.commands.common import run_async
from day1.config import settings


def _project_root() -> Path:
    here = Path(__file__).resolve()
    for ancestor in (here.parent, *here.parents):
        if (ancestor / "pyproject.toml").exists():
            return ancestor
    return Path.cwd()


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    help_cmd = subparsers.add_parser("help", help="Show help")
    help_cmd.set_defaults(_handler=lambda _args: 0)

    test_cmd = subparsers.add_parser("test", help="Run MatrixOne feature tests")
    test_cmd.set_defaults(_handler=cmd_test)

    api_cmd = subparsers.add_parser("api", help="Start FastAPI server")
    api_cmd.add_argument("--host", default=settings.host)
    api_cmd.add_argument("--port", type=int, default=settings.port)
    api_cmd.add_argument("--reload", action="store_true")
    api_cmd.set_defaults(_handler=cmd_api)

    dashboard_cmd = subparsers.add_parser(
        "dashboard",
        help="Start dashboard dev server",
    )
    dashboard_cmd.set_defaults(_handler=cmd_dashboard)

    migrate_cmd = subparsers.add_parser("migrate", help="Run database migrations")
    migrate_cmd.set_defaults(_handler=cmd_migrate)

    init_cmd = subparsers.add_parser("init", help="Initialize database and main branch")
    init_cmd.set_defaults(_handler=cmd_init)

    health_cmd = subparsers.add_parser("health", help="Check API health")
    health_cmd.add_argument(
        "--base-url", default=f"http://{settings.host}:{settings.port}"
    )
    health_cmd.add_argument(
        "--format", choices=["table", "json", "text"], default="table"
    )
    health_cmd.set_defaults(_handler=cmd_health)


def cmd_test(_args: argparse.Namespace) -> int:
    return subprocess.call(
        [sys.executable, str(_project_root() / "scripts" / "test_mo_features.py")]
    )


def cmd_api(args: argparse.Namespace) -> int:
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "day1.api.app:app",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if args.reload:
        cmd.append("--reload")
    return subprocess.call(cmd)


def cmd_dashboard(_args: argparse.Namespace) -> int:
    dashboard_dir = _project_root() / "dashboard"
    if not (dashboard_dir / "node_modules").exists():
        subprocess.call(["npm", "install"], cwd=str(dashboard_dir))
    return subprocess.call(["npm", "run", "dev"], cwd=str(dashboard_dir))


def cmd_migrate(_args: argparse.Namespace) -> int:
    return subprocess.call(
        [sys.executable, str(_project_root() / "scripts" / "migrate.py")]
    )


def cmd_init(_args: argparse.Namespace) -> int:
    return run_async(_cmd_init())


async def _cmd_init() -> int:
    from day1.core.branch_manager import BranchManager
    from day1.db.engine import get_session, init_db

    await init_db()
    session_gen = get_session()
    session = await anext(session_gen)
    try:
        await BranchManager(session).ensure_main_branch()
    finally:
        await session_gen.aclose()
    print("initialized: ok")
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    url = args.base_url.rstrip("/") + "/health"
    try:
        with httpx.Client(timeout=3.0, trust_env=False) as client:
            resp = client.get(url)
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:  # pragma: no cover - simple process wrapper
        if args.format == "json":
            print(f'{{"status":"error","detail":"{str(exc)}"}}')
        else:
            print(f"status: error\nurl: {url}\ndetail: {exc}")
        return 1

    if args.format == "json":
        import json

        print(json.dumps({"url": url, **payload}, ensure_ascii=False, indent=2))
    else:
        print(f"status: {payload.get('status')}")
        print(f"url: {url}")
        if "version" in payload:
            print(f"version: {payload['version']}")
    return 0
