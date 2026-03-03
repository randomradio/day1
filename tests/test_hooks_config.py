"""Tests for hooks/claude_code_config.py — curl-based hooks + HTTP MCP."""

from __future__ import annotations

from day1.hooks.claude_code_config import generate_hooks_config, generate_mcp_config


def test_generates_7_hook_events():
    config = generate_hooks_config()
    hooks = config["hooks"]
    assert len(hooks) == 7
    expected = {
        "SessionStart",
        "UserPromptSubmit",
        "PreToolUse",
        "PostToolUse",
        "Stop",
        "PreCompact",
        "SessionEnd",
    }
    assert set(hooks.keys()) == expected


def test_hooks_use_curl():
    config = generate_hooks_config()
    for event, entries in config["hooks"].items():
        for entry in entries:
            for hook in entry["hooks"]:
                assert "curl" in hook["command"], f"{event} hook missing curl"


def test_custom_url():
    config = generate_hooks_config(api_base_url="https://day1.example.com")
    for entries in config["hooks"].values():
        for entry in entries:
            for hook in entry["hooks"]:
                assert "https://day1.example.com" in hook["command"]


def test_api_key_in_header():
    config = generate_hooks_config(api_key="sk-test-123")
    for entries in config["hooks"].values():
        for entry in entries:
            for hook in entry["hooks"]:
                assert "Authorization: Bearer sk-test-123" in hook["command"]


def test_no_api_key_no_auth_header():
    config = generate_hooks_config()
    for entries in config["hooks"].values():
        for entry in entries:
            for hook in entry["hooks"]:
                assert "Authorization" not in hook["command"]


def test_mcp_config_http_transport():
    config = generate_mcp_config()
    day1 = config["mcpServers"]["day1"]
    assert day1["type"] == "http"
    assert "/mcp" in day1["url"]


def test_mcp_config_custom_url():
    config = generate_mcp_config(api_base_url="https://day1.example.com")
    day1 = config["mcpServers"]["day1"]
    assert day1["url"] == "https://day1.example.com/mcp"
