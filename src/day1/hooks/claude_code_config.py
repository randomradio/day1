"""Generate Claude Code hooks configuration for integration.

This module generates the hooks configuration that should be added to
.claude/settings.json for automatic memory capture.
"""

from __future__ import annotations

import json


def generate_hooks_config() -> dict:
    """Generate Claude Code hooks configuration.

    Returns:
        Dict to merge into .claude/settings.json

    Note: Uses new format with matcher + hooks array.
    Matcher "*" means hook runs for all events.
    """
    return {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python -m day1.hooks.session_start",
                        }
                    ],
                }
            ],
            "UserPromptSubmit": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python -m day1.hooks.user_prompt",
                        }
                    ],
                }
            ],
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python -m day1.hooks.pre_tool_use",
                        }
                    ],
                }
            ],
            "PostToolUse": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python -m day1.hooks.post_tool_use",
                        }
                    ],
                }
            ],
            "Stop": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python -m day1.hooks.assistant_response",
                        }
                    ],
                }
            ],
            "PreCompact": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python -m day1.hooks.pre_compact",
                        }
                    ],
                }
            ],
            "SessionEnd": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python -m day1.hooks.session_end",
                        }
                    ],
                }
            ],
        }
    }


def generate_mcp_config() -> dict:
    """Generate MCP server configuration for Claude Code.

    Returns:
        Dict to merge into .claude/settings.json or claude_desktop_config.json
    """
    return {
        "mcpServers": {
            "day1": {
                "command": "python",
                "args": ["-m", "day1.mcp.mcp_server"],
                "env": {
                    "BM_DATABASE_URL": "sqlite+aiosqlite:///day1.db",
                    "BM_EMBEDDING_PROVIDER": "mock",
                },
            }
        }
    }


def main() -> None:
    """Print full Claude Code integration config."""
    config = {
        **generate_hooks_config(),
        **generate_mcp_config(),
    }
    print(json.dumps(config, indent=2))
    print(
        "\n# Add the above to .claude/settings.json "
        "or use 'claude mcp add' for MCP only"
    )


if __name__ == "__main__":
    main()
