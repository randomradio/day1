#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Install Claude Code project config for Day1 (HTTP MCP + curl-based hooks).

Usage:
  scripts/install_claude_project.sh --api-base-url http://HOST:9903 [options]

Options:
  --api-base-url URL     Base URL of Day1 API (required), e.g. http://127.0.0.1:9903
  --mcp-url URL          MCP URL (default: <api-base-url>/mcp)
  --hook-url URL         Hook ingest URL (default: <api-base-url>/api/v1/ingest/claude-hook)
  --api-key KEY          Optional Day1 API key (used as Bearer for MCP + hooks)
  --mcp-name NAME        Claude MCP server name (default: day1)
  --scope SCOPE          Claude MCP scope: project|local|user (default: project)
  --project-dir DIR      Claude project directory (default: current working directory)
  --settings-file PATH   Claude settings file to write (default: .claude/settings.local.json)
  --hooks-only           Only write hooks settings, skip 'claude mcp add'
  --mcp-only             Only install MCP config, skip hooks settings file generation
  --dry-run              Print actions and generated settings JSON, do not modify files
  -h, --help             Show this help

Notes:
  - Hooks are configured as lightweight curl forwarders (stdin JSON -> POST hook-url).
  - This script does not require a local Day1 Python env on the client machine.
  - Recommended for testing hooks first: enable your ingest endpoint or point --hook-url
    to a request bin/webhook endpoint.
EOF
}

API_BASE_URL=""
MCP_URL=""
HOOK_URL=""
API_KEY=""
MCP_NAME="day1"
SCOPE="project"
PROJECT_DIR="$(pwd)"
SETTINGS_FILE=".claude/settings.local.json"
DRY_RUN=0
DO_HOOKS=1
DO_MCP=1
CLEANUP_LEGACY=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-base-url)
      API_BASE_URL="${2:-}"; shift 2 ;;
    --mcp-url)
      MCP_URL="${2:-}"; shift 2 ;;
    --hook-url)
      HOOK_URL="${2:-}"; shift 2 ;;
    --api-key)
      API_KEY="${2:-}"; shift 2 ;;
    --mcp-name)
      MCP_NAME="${2:-}"; shift 2 ;;
    --scope)
      SCOPE="${2:-}"; shift 2 ;;
    --project-dir)
      PROJECT_DIR="${2:-}"; shift 2 ;;
    --settings-file)
      SETTINGS_FILE="${2:-}"; shift 2 ;;
    --hooks-only)
      DO_MCP=0; shift ;;
    --mcp-only)
      DO_HOOKS=0; shift ;;
    --dry-run)
      DRY_RUN=1; shift ;;
    --no-cleanup-legacy)
      CLEANUP_LEGACY=0; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2 ;;
  esac
done

if [[ -z "$API_BASE_URL" ]]; then
  echo "--api-base-url is required" >&2
  usage >&2
  exit 2
fi

case "$SCOPE" in
  project|local|user) ;;
  *)
    echo "--scope must be one of: project, local, user" >&2
    exit 2 ;;
esac

if [[ ! -d "$PROJECT_DIR" ]]; then
  echo "Project dir not found: $PROJECT_DIR" >&2
  exit 1
fi

API_BASE_URL="${API_BASE_URL%/}"
MCP_URL="${MCP_URL:-$API_BASE_URL/mcp}"
HOOK_URL="${HOOK_URL:-$API_BASE_URL/api/v1/ingest/claude-hook}"

SETTINGS_ABS="$PROJECT_DIR/$SETTINGS_FILE"
CLAUDE_DIR="$(dirname "$SETTINGS_ABS")"

if [[ "$DO_MCP" -eq 1 ]] && ! command -v claude >/dev/null 2>&1; then
  echo "'claude' CLI not found in PATH (required for MCP install). Use --hooks-only to skip MCP install." >&2
  exit 1
fi

export DAY1_INSTALL_PROJECT_DIR="$PROJECT_DIR"
export DAY1_INSTALL_SETTINGS_ABS="$SETTINGS_ABS"
export DAY1_INSTALL_HOOK_URL="$HOOK_URL"
export DAY1_INSTALL_API_KEY="$API_KEY"
export DAY1_INSTALL_MCP_NAME="$MCP_NAME"

GEN_JSON="$(
python3 - <<'PY'
import json
import os
import shlex

project_dir = os.environ["DAY1_INSTALL_PROJECT_DIR"]
settings_abs = os.environ["DAY1_INSTALL_SETTINGS_ABS"]
hook_url = os.environ["DAY1_INSTALL_HOOK_URL"]
api_key = os.environ.get("DAY1_INSTALL_API_KEY", "")

events = [
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "Stop",
    "PreCompact",
    "SessionEnd",
]

def hook_command(event: str) -> str:
    parts = [
        "curl", "-sS", "-m", "3",
        "-X", "POST",
        hook_url,
        "-H", "Content-Type: application/json",
        "-H", f"X-Day1-Hook-Event: {event}",
        "-H", f"X-Day1-Project-Path: {project_dir}",
    ]
    if api_key:
        parts.extend(["-H", f"Authorization: Bearer {api_key}"])
    parts.extend(["--data-binary", "@-"])
    curl_cmd = " ".join(shlex.quote(p) for p in parts)
    # Use bash wrapper to handle empty stdin safely and never block Claude.
    return (
        "/bin/bash -lc "
        + shlex.quote(
            "tmp=$(mktemp); "
            "cat >\"$tmp\" || true; "
            "[ -s \"$tmp\" ] || printf '{}' >\"$tmp\"; "
            f"{curl_cmd} <\"$tmp\" >/dev/null 2>&1 || true; "
            "rm -f \"$tmp\""
        )
    )

hooks = {}
for event in events:
    hooks[event] = [
        {
            "matcher": "*",
            "hooks": [
                {
                    "type": "command",
                    "command": hook_command(event),
                }
            ],
        }
    ]

config = {
    "permissions": {
        "allow": [
            "mcp__day1__*",
            "Bash(curl:*)",
            "Bash(/bin/bash:*)",
            "Bash(cat:*)",
        ]
    },
    "hooks": hooks,
}

print(json.dumps(config, indent=2, ensure_ascii=False))
PY
)"

echo "Project dir:   $PROJECT_DIR"
echo "API base URL:  $API_BASE_URL"
echo "MCP URL:       $MCP_URL"
echo "Hook URL:      $HOOK_URL"
echo "Scope:         $SCOPE"
echo "MCP name:      $MCP_NAME"
if [[ -n "$API_KEY" ]]; then
  echo "API key:       provided (Bearer)"
else
  echo "API key:       not provided"
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo
  echo "--- Generated $SETTINGS_FILE ---"
  echo "$GEN_JSON"
  echo
  if [[ "$DO_MCP" -eq 1 ]]; then
    echo "--- MCP install command ---"
    if [[ -n "$API_KEY" ]]; then
      echo "cd $(printf '%q' "$PROJECT_DIR") && claude mcp remove $MCP_NAME -s $SCOPE >/dev/null 2>&1 || true && claude mcp add --scope $SCOPE --transport http --header \"Authorization: Bearer ***\" $MCP_NAME $MCP_URL"
    else
      echo "cd $(printf '%q' "$PROJECT_DIR") && claude mcp remove $MCP_NAME -s $SCOPE >/dev/null 2>&1 || true && claude mcp add --scope $SCOPE --transport http $MCP_NAME $MCP_URL"
    fi
  fi
  exit 0
fi

if [[ "$DO_HOOKS" -eq 1 ]]; then
  mkdir -p "$CLAUDE_DIR"
  if [[ -f "$SETTINGS_ABS" ]]; then
    cp -f "$SETTINGS_ABS" "$SETTINGS_ABS.bak.$(date +%Y%m%d-%H%M%S)"
  fi
  printf '%s\n' "$GEN_JSON" >"$SETTINGS_ABS"
  echo "Wrote hooks config: $SETTINGS_ABS"
fi

if [[ "$CLEANUP_LEGACY" -eq 1 ]]; then
  LEGACY_SETTINGS="$PROJECT_DIR/.claude/settings.json"
  if [[ -f "$LEGACY_SETTINGS" ]]; then
    export DAY1_LEGACY_SETTINGS="$LEGACY_SETTINGS"
    CLEANUP_OUT="$(
      python3 - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["DAY1_LEGACY_SETTINGS"])
mcp_name = os.environ.get("DAY1_INSTALL_MCP_NAME", "day1")
text = path.read_text()
try:
    data = json.loads(text)
except Exception:
    print("legacy_cleanup=skip invalid_json")
    raise SystemExit(0)

changed = False
removed_hooks = 0

hooks = data.get("hooks")
if isinstance(hooks, dict):
    new_hooks = {}
    for event, entries in hooks.items():
        if not isinstance(entries, list):
            new_hooks[event] = entries
            continue
        kept_entries = []
        for entry in entries:
            if not isinstance(entry, dict):
                kept_entries.append(entry)
                continue
            hook_items = entry.get("hooks")
            if not isinstance(hook_items, list):
                kept_entries.append(entry)
                continue
            kept_hook_items = []
            for hook in hook_items:
                if not isinstance(hook, dict):
                    kept_hook_items.append(hook)
                    continue
                cmd = str(hook.get("command", ""))
                is_legacy_day1_hook = ("day1.hooks." in cmd) or (
                    "/Users/randomradio/src/day1/" in cmd
                )
                if is_legacy_day1_hook:
                    removed_hooks += 1
                    changed = True
                    continue
                kept_hook_items.append(hook)
            if kept_hook_items:
                if len(kept_hook_items) != len(hook_items):
                    changed = True
                new_entry = dict(entry)
                new_entry["hooks"] = kept_hook_items
                kept_entries.append(new_entry)
            else:
                changed = True
        if kept_entries:
            new_hooks[event] = kept_entries
    if new_hooks:
        data["hooks"] = new_hooks
    elif "hooks" in data:
        del data["hooks"]
        changed = True

mcp_servers = data.get("mcpServers")
removed_mcp = False
if isinstance(mcp_servers, dict):
    server = mcp_servers.get(mcp_name)
    if isinstance(server, dict):
        cmd = str(server.get("command", ""))
        args = server.get("args", [])
        args_s = " ".join(str(x) for x in args) if isinstance(args, list) else str(args)
        is_legacy_day1_mcp = ("day1.mcp.mcp_server" in args_s) or (
            "/Users/randomradio/src/day1/" in cmd
        )
        if is_legacy_day1_mcp:
            del mcp_servers[mcp_name]
            removed_mcp = True
            changed = True
    if not mcp_servers and "mcpServers" in data:
        del data["mcpServers"]
        changed = True

if changed:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(
        f"legacy_cleanup=ok hooks_removed={removed_hooks} "
        f"mcp_removed={str(removed_mcp).lower()} file={path}"
    )
else:
    print(f"legacy_cleanup=noop file={path}")
PY
    )"
    echo "$CLEANUP_OUT"
  fi
fi

if [[ "$DO_MCP" -eq 1 ]]; then
  (
    cd "$PROJECT_DIR"
    claude mcp remove "$MCP_NAME" -s "$SCOPE" >/dev/null 2>&1 || true
    if [[ -n "$API_KEY" ]]; then
      claude mcp add --scope "$SCOPE" --transport http --header "Authorization: Bearer $API_KEY" "$MCP_NAME" "$MCP_URL"
    else
      claude mcp add --scope "$SCOPE" --transport http "$MCP_NAME" "$MCP_URL"
    fi
    echo "MCP installed. Current status:"
    claude mcp get "$MCP_NAME" || true
  )
fi

echo
echo "Next steps:"
echo "1. Trigger a Claude event (prompt/tool call) in this project."
echo "2. Check your ingest endpoint logs (or request bin) for POSTs with header X-Day1-Hook-Event."
echo "3. In Claude Code, run '/mcp' to confirm MCP server '$MCP_NAME' is connected."
