"""Generate Claude Code hooks configuration for integration.

Hooks use curl to POST to the Day1 HTTP API — no Python hook modules needed.
MCP uses HTTP streamable transport at /mcp.
"""

from __future__ import annotations

import json
import os


_DEFAULT_API_BASE = "http://localhost:8000"
_HOOK_EVENTS = [
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "Stop",
    "PreCompact",
    "SessionEnd",
]


def _curl_command(api_base_url: str, api_key: str | None = None) -> str:
    """Build the curl command for a hook event."""
    auth = ""
    if api_key:
        auth = f" -H 'Authorization: Bearer {api_key}'"
    return (
        f"curl -sS -m 3 -X POST {api_base_url}/api/v1/ingest/claude-hook"
        f" -H 'Content-Type: application/json'"
        f" -H 'X-Day1-Hook-Event: $CLAUDE_HOOK_EVENT'"
        f"{auth}"
        f" --data-binary @-"
    )


def generate_hooks_config(
    api_base_url: str | None = None,
    api_key: str | None = None,
) -> dict:
    """Generate Claude Code hooks configuration (curl-based).

    Args:
        api_base_url: Day1 server URL (default: http://localhost:8000).
        api_key: Optional API key for authenticated access.

    Returns:
        Dict to merge into .claude/settings.json
    """
    base = api_base_url or os.environ.get("DAY1_API_BASE_URL", _DEFAULT_API_BASE)
    key = api_key or os.environ.get("DAY1_API_KEY")
    cmd = _curl_command(base, key)

    hooks: dict = {}
    for event in _HOOK_EVENTS:
        hooks[event] = [
            {
                "matcher": "*",
                "hooks": [{"type": "command", "command": cmd}],
            }
        ]

    return {"hooks": hooks}


def generate_mcp_config(
    api_base_url: str | None = None,
) -> dict:
    """Generate MCP server configuration for Claude Code (HTTP transport).

    Args:
        api_base_url: Day1 server URL (default: http://localhost:8000).

    Returns:
        Dict to merge into .claude/settings.json or claude_desktop_config.json
    """
    base = api_base_url or os.environ.get("DAY1_API_BASE_URL", _DEFAULT_API_BASE)

    return {
        "mcpServers": {
            "day1": {
                "type": "http",
                "url": f"{base}/mcp",
            }
        }
    }


def main() -> None:
    """Print full Claude Code integration config."""
    base = os.environ.get("DAY1_API_BASE_URL", _DEFAULT_API_BASE)
    key = os.environ.get("DAY1_API_KEY")
    config = {
        **generate_hooks_config(api_base_url=base, api_key=key),
        **generate_mcp_config(api_base_url=base),
    }
    print(json.dumps(config, indent=2))
    print(
        "\n# Add the above to .claude/settings.json "
        "or use 'claude mcp add' for MCP only"
    )


if __name__ == "__main__":
    main()
