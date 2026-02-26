"""Argument-based CLI entrypoint for Day1."""

from __future__ import annotations

import argparse

from day1.cli.commands import branches, memory, system
from day1.logging_config import setup_logging


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="day1",
        description=(
            "Day1 CLI (MVP): memory write/search, branch ops, "
            "snapshots, health."
        ),
    )
    subparsers = parser.add_subparsers(dest="command")

    memory.register(subparsers)
    branches.register(subparsers)
    system.register(subparsers)
    return parser


def main() -> None:
    setup_logging()
    parser = _build_parser()
    args = parser.parse_args()
    if not getattr(args, "command", None):
        parser.print_help()
        raise SystemExit(0)
    if args.command == "help":
        parser.print_help()
        raise SystemExit(0)

    handler = getattr(args, "_handler", None)
    if handler is None:
        parser.print_help()
        raise SystemExit(1)

    code = int(handler(args) or 0)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
