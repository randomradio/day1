"""Generate Claude Code hooks configuration for integration.

This module generates the hooks configuration that should be added to
.claude/settings.json for automatic memory capture.
"""

from __future__ import annotations

import json
import pathlib


def _get_project_root() -> pathlib.Path:
    """Get the project root directory (day1/)."""
    return pathlib.Path(__file__).parent.parent.parent.parent


def _get_venv_python() -> str:
    """Get absolute path to venv Python executable."""
    root = _get_project_root()
    return str(root / ".venv" / "bin" / "python")


def _get_src_path() -> str:
    """Get absolute path to src directory for PYTHONPATH."""
    root = _get_project_root()
    return str(root / "src")


def generate_hooks_config(project_root: str | None = None) -> dict:
    """Generate Claude Code hooks configuration.

    Args:
        project_root: Override project root path. If None, auto-detected.

    Returns:
        Dict to merge into .claude/settings.json

    Note: Uses new format with matcher + hooks array.
    Matcher "*" means hook runs for all events.
    """
    if project_root:
        root = pathlib.Path(project_root)
        python_path = str(root / ".venv" / "bin" / "python")
        src_dir = str(root / "src")
    else:
        python_path = _get_venv_python()
        src_dir = _get_src_path()

    # Common environment for all hooks
    common_env = {
        "PYTHONPATH": src_dir,
        "BM_DATABASE_URL": "mysql+aiomysql://root:111@localhost:6001/mo_catalog",
    }

    def make_hook(module: str) -> dict:
        return {
            "type": "command",
            "command": f"{python_path} -m {module}",
            "env": common_env,
        }

    return {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "*",
                    "hooks": [make_hook("day1.hooks.session_start")],
                }
            ],
            "UserPromptSubmit": [
                {
                    "matcher": "*",
                    "hooks": [make_hook("day1.hooks.user_prompt")],
                }
            ],
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [make_hook("day1.hooks.pre_tool_use")],
                }
            ],
            "PostToolUse": [
                {
                    "matcher": "*",
                    "hooks": [make_hook("day1.hooks.post_tool_use")],
                }
            ],
            "Stop": [
                {
                    "matcher": "*",
                    "hooks": [make_hook("day1.hooks.assistant_response")],
                }
            ],
            "PreCompact": [
                {
                    "matcher": "*",
                    "hooks": [make_hook("day1.hooks.pre_compact")],
                }
            ],
            "SessionEnd": [
                {
                    "matcher": "*",
                    "hooks": [make_hook("day1.hooks.session_end")],
                }
            ],
        }
    }


def generate_mcp_config(project_root: str | None = None) -> dict:
    """Generate MCP server configuration for Claude Code.

    Args:
        project_root: Override project root path. If None, auto-detected.

    Returns:
        Dict to merge into .claude/settings.json or claude_desktop_config.json
    """
    if project_root:
        root = pathlib.Path(project_root)
        python_path = str(root / ".venv" / "bin" / "python")
        src_dir = str(root / "src")
    else:
        python_path = _get_venv_python()
        src_dir = _get_src_path()

    return {
        "mcpServers": {
            "day1": {
                "command": python_path,
                "args": ["-m", "day1.mcp.mcp_server"],
                "cwd": str(root if project_root else _get_project_root()),
                "env": {
                    "BM_DATABASE_URL": "mysql+aiomysql://root:111@localhost:6001/mo_catalog",
                    "PYTHONPATH": src_dir,
                },
            }
        }
    }


def main() -> None:
    """Print full Claude Code integration config."""
    project_root = str(_get_project_root())
    config = {
        **generate_hooks_config(project_root),
        **generate_mcp_config(project_root),
    }
    print(json.dumps(config, indent=2))
    print(
        "\n# Add the above to .claude/settings.json "
        "or use 'claude mcp add' for MCP only"
    )


if __name__ == "__main__":
    main()
