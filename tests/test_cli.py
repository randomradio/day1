"""Tests for CLI command registration and parsing."""

from __future__ import annotations

from day1.cli.main import _build_parser


def test_parser_has_all_commands():
    parser = _build_parser()
    # Get all registered subcommand names
    choices = list(parser._subparsers._actions[1].choices.keys())
    expected = [
        "help", "test", "api", "dashboard", "migrate", "init", "health",
        "write", "search", "timeline", "branch", "merge", "snapshot", "count",
    ]
    for cmd in expected:
        assert cmd in choices, f"Missing CLI command: {cmd}"


def test_write_command_args():
    parser = _build_parser()
    args = parser.parse_args(["write", "test memory", "--category", "decision", "--confidence", "0.9"])
    assert args.text == "test memory"
    assert args.category == "decision"
    assert args.confidence == 0.9


def test_search_command_args():
    parser = _build_parser()
    args = parser.parse_args(["search", "how to fix", "--limit", "5", "--category", "bug_fix"])
    assert args.query == "how to fix"
    assert args.limit == 5
    assert args.category == "bug_fix"


def test_timeline_command_args():
    parser = _build_parser()
    args = parser.parse_args(["timeline", "--branch", "main", "--limit", "10", "--category", "decision"])
    assert args.branch == "main"
    assert args.limit == 10
    assert args.category == "decision"


def test_branch_subcommands():
    parser = _build_parser()
    args = parser.parse_args(["branch", "list"])
    assert args.branch_action == "list"

    args = parser.parse_args(["branch", "create", "my-branch", "--parent", "main"])
    assert args.branch_action == "create"
    assert args.name == "my-branch"
    assert args.parent == "main"

    args = parser.parse_args(["branch", "switch", "feature-x"])
    assert args.branch_action == "switch"
    assert args.name == "feature-x"


def test_merge_command_args():
    parser = _build_parser()
    args = parser.parse_args(["merge", "feature-branch", "--into", "main"])
    assert args.source == "feature-branch"
    assert args.into == "main"


def test_snapshot_subcommands():
    parser = _build_parser()
    args = parser.parse_args(["snapshot", "create", "--label", "before-refactor"])
    assert args.snap_action == "create"
    assert args.label == "before-refactor"

    args = parser.parse_args(["snapshot", "list", "--branch", "main"])
    assert args.snap_action == "list"

    args = parser.parse_args(["snapshot", "restore", "abc-123"])
    assert args.snap_action == "restore"
    assert args.snapshot_id == "abc-123"


def test_count_command_args():
    parser = _build_parser()
    args = parser.parse_args(["count", "--branch", "feature"])
    assert args.branch == "feature"
